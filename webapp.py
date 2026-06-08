# -*- coding: utf-8 -*-
"""
webapp.py
=========
Giao diện WEB nhẹ để chạy hệ thống ngay trong trình duyệt — KHÔNG dùng thư viện
ngoài (chỉ http.server của stdlib + Jinja2 đã có sẵn).

QUY TRÌNH (đúng cách sản phẩm phối hợp với Claude):

  ┌── BƯỚC 1 · TẢI LÊN 2 FILE ─────────────────────────────────────────┐
  │ Người dùng TỰ TẢI LÊN 2 file CSV raw (Chi tiết + Tổng hợp).         │
  │ Hệ thống đọc, liệt kê nhân viên để chọn.                           │
  ├── BƯỚC 2 · XUẤT CSV TỔNG HỢP + PROMPT ─────────────────────────────┤
  │ Chọn nhân viên → hệ thống tính điểm và xuất:                        │
  │   • Tong-hop-raw_<MaNV>.csv  (file tổng hợp đúng format gốc)        │
  │   • prompt_<MaNV>.txt        (PROMPT để đưa cho Claude, kèm COPY)   │
  ├── BƯỚC 3 · DÁN KẾT QUẢ CLAUDE → BÁO CÁO ───────────────────────────┤
  │ Người dùng DÁN JSON Claude trả về → hệ thống ghép vào TEMPLATE      │
  │ có sẵn → render BAOCAO_<MaNV>.html (+ PDF nếu có GTK).             │
  └────────────────────────────────────────────────────────────────────┘

CÁCH DÙNG:
    python webapp.py
    -> mở trình duyệt: http://127.0.0.1:8000

KHÔNG gọi bất kỳ AI API nào.
"""

import argparse
import html
import json
import os
import re
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jinja2 import Template

import config
import content_provider
import data_loader
import main as pipeline

# Thư mục mặc định (có thể đổi qua tham số dòng lệnh).
DATA_DIR = "data"
OUT_DIR = "output"

# Kiểu nội dung theo đuôi file khi phục vụ download/xem.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

# ---------------------------------------------------------------------------
# Parser multipart/form-data (tự viết — Python 3.13+ đã gỡ module 'cgi').
# ---------------------------------------------------------------------------
def parse_multipart(content_type, body):
    """
    Bóc tách body multipart/form-data thành (fields, files):
      - fields: {name: giá trị chuỗi}
      - files : {name: (filename, bytes nội dung)}
    Giữ NGUYÊN bytes nội dung file (kể cả BOM) để ghi ra đĩa không sai lệch.
    """
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type or "")
    if not m:
        return {}, {}
    boundary = (m.group(1) or m.group(2)).strip()
    delim = b"--" + boundary.encode("latin-1")

    fields, files = {}, {}
    for part in body.split(delim):
        if not part or part in (b"--\r\n", b"--", b"\r\n"):
            continue
        # Mỗi phần hợp lệ được "đóng khung" bởi \r\n ở đầu và \r\n ở cuối.
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, content = part.split(b"\r\n\r\n", 1)

        name = filename = None
        for line in raw_headers.decode("utf-8", "replace").split("\r\n"):
            if line.lower().startswith("content-disposition"):
                nm = re.search(r'name="([^"]*)"', line)
                fn = re.search(r'filename="([^"]*)"', line)
                name = nm.group(1) if nm else None
                filename = fn.group(1) if fn else None
        if name is None:
            continue
        if filename is not None:
            files[name] = (filename, content)
        else:
            fields[name] = content.decode("utf-8", "replace")
    return fields, files


def _filepart_ok(part):
    """part là (filename, bytes); hợp lệ khi có tên file và nội dung khác rỗng."""
    return part is not None and part[0] and part[1]


# ---------------------------------------------------------------------------
# Giao diện (Jinja2 template dạng chuỗi) — autoescape=False, nên text động do
# người dùng nhập/đọc từ file đều được escape thủ công bằng html.escape().
# ---------------------------------------------------------------------------
PAGE_CSS = """
*{box-sizing:border-box}
body{font-family:'Segoe UI','DejaVu Sans',Arial,sans-serif;margin:0;background:#eef1f5;color:#222}
.bar{background:#1F4E79;color:#fff;padding:16px 28px;display:flex;align-items:center;gap:14px}
.bar h1{font-size:18px;margin:0;font-weight:600}
.bar .tag{background:#C00000;font-size:11px;letter-spacing:2px;padding:3px 10px;border-radius:10px}
.wrap{max-width:1040px;margin:22px auto;padding:0 18px}
.card{background:#fff;border-radius:10px;padding:22px 26px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:18px}
.card h2{font-size:16px;color:#1F4E79;margin:0 0 4px}
.card .sub{font-size:12.5px;color:#888;margin:0 0 14px}
label{font-size:13px;font-weight:600;color:#1F4E79;display:block;margin-bottom:6px}
input[type=text]{font-size:15px;padding:9px 12px;border:1px solid #cdd6e2;border-radius:7px;width:220px}
input[type=file]{font-size:13px;padding:9px 12px;border:1px dashed #9db4d0;border-radius:8px;width:100%;
  background:#f7faff;cursor:pointer}
.field{margin-bottom:16px}
textarea{width:100%;font-family:'Consolas','DejaVu Sans Mono',monospace;font-size:12.5px;line-height:1.55;
  border:1px solid #cdd6e2;border-radius:8px;padding:12px 14px;resize:vertical;background:#fbfcfe;color:#243}
.btn{display:inline-block;border:none;border-radius:7px;padding:10px 18px;font-size:14px;font-weight:600;
  cursor:pointer;text-decoration:none}
.btn-primary{background:#1F4E79;color:#fff}
.btn-ghost{background:#e7edf5;color:#1F4E79}
.btn-green{background:#2E7D32;color:#fff}
.btn-sm{padding:6px 12px;font-size:12.5px}
.row{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}
.hint{font-size:12.5px;color:#777;margin-top:8px;line-height:1.6}
.chips{margin-top:12px}
.chip{display:inline-block;background:#eef3fa;border:1px solid #d7e1ee;border-radius:14px;padding:5px 14px;
  font-size:13px;margin:4px 6px 0 0;color:#1F4E79;text-decoration:none}
.chip:hover{background:#1F4E79;color:#fff}
.err{background:#FCE4E4;border-left:4px solid #C00000;padding:12px 16px;border-radius:0 6px 6px 0;
  font-size:13px;white-space:pre-wrap;font-family:monospace}
.ok{background:#E2F0D9;border-left:4px solid #2E7D32;padding:12px 16px;border-radius:0 6px 6px 0;font-size:13px}
table.summary{border-collapse:collapse;font-size:13.5px;margin-top:10px;width:100%}
table.summary td,table.summary th{border:1px solid #dde3ea;padding:7px 12px;text-align:left}
table.summary th{background:#1F4E79;color:#fff}
.big{font-size:34px;font-weight:bold;color:#1F4E79}
.links a{margin-right:10px}
iframe{width:100%;height:1400px;border:1px solid #dde3ea;border-radius:8px;background:#fff}
.flash{font-size:13px;padding:10px 14px;border-radius:7px;margin-bottom:14px}
.flash.info{background:#DEEBF7;color:#1F4E79}
.steps{display:flex;gap:0;margin:0;font-size:12px;font-weight:600}
.steps .s{flex:1;text-align:center;padding:8px 6px;background:#e7edf5;color:#9aa7b8;border-right:2px solid #eef1f5}
.steps .s.active{background:#1F4E79;color:#fff}
.steps .s:first-child{border-radius:7px 0 0 7px}
.steps .s:last-child{border-radius:0 7px 7px 0;border-right:none}
.codehdr{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.codehdr .name{font-family:monospace;font-size:12.5px;color:#1F4E79;background:#eef3fa;padding:3px 9px;border-radius:6px}
.copied{font-size:12px;color:#2E7D32;font-weight:600;display:none}
"""

STEPBAR = """<div class="steps">
  <div class="s {{ 'active' if step==1 }}">① Tải lên 2 file CSV &amp; chọn nhân viên</div>
  <div class="s {{ 'active' if step==2 }}">② Xuất CSV tổng hợp + prompt</div>
  <div class="s {{ 'active' if step==3 }}">③ Dán kết quả Claude → Báo cáo</div>
</div>"""

UPLOAD_TMPL = Template("""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<title>Tải dữ liệu — Báo cáo 360°</title><style>{{ css }}</style></head><body>
<div class="bar"><span class="tag">360°</span><h1>Hệ thống tạo báo cáo đánh giá 360°</h1></div>
<div class="wrap">
  {% if flash %}<div class="flash info">{{ flash }}</div>{% endif %}
  <div class="card">""" + STEPBAR + """</div>

  <div class="card">
    <h2>Bước 1 · Tải lên 2 file CSV raw</h2>
    <p class="sub">Chọn đúng 2 file xuất từ hệ thống đánh giá. Hệ thống sẽ đọc và tính toán
      trực tiếp từ 2 file bạn tải lên (không dùng dữ liệu làm sẵn).</p>
    <form method="post" action="/upload" enctype="multipart/form-data">
      <div class="field">
        <label for="chi_tiet">① File CHI TIẾT &nbsp;<span style="color:#888;font-weight:400">— vd: "360 data raw(Chi tiet-raw).csv"</span></label>
        <input type="file" id="chi_tiet" name="chi_tiet" accept=".csv,text/csv" required>
      </div>
      <div class="field">
        <label for="tong_hop">② File TỔNG HỢP &nbsp;<span style="color:#888;font-weight:400">— vd: "360 data raw(Tong-hop-raw).csv"</span></label>
        <input type="file" id="tong_hop" name="tong_hop" accept=".csv,text/csv" required>
      </div>
      <button class="btn btn-primary" type="submit">Tải lên &amp; đọc dữ liệu →</button>
    </form>
    <div class="hint">
      {% if has_data %}Đã có dữ liệu tải trước đó —
        <a href="/employees">dùng lại dữ liệu cũ →</a>. Hoặc {% endif %}
      chưa có file để thử? <a href="/sample">Tạo dữ liệu mẫu để test nhanh</a>.
    </div>
  </div>
</div></body></html>""")

EMPLOYEES_TMPL = Template("""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<title>Chọn nhân viên — Báo cáo 360°</title><style>{{ css }}</style></head><body>
<div class="bar"><span class="tag">360°</span><h1>Chọn nhân viên cần tạo báo cáo</h1>
  <a class="btn btn-ghost" href="/" style="margin-left:auto">← Tải file khác</a></div>
<div class="wrap">
  {% if flash %}<div class="flash info">{{ flash }}</div>{% endif %}
  <div class="card">""" + STEPBAR + """</div>
  <div class="card">
    <h2>Bước 1 · Đã đọc dữ liệu — chọn nhân viên</h2>
    <p class="sub">Tìm thấy {{ employees|length }} nhân viên trong file Chi tiết.
      Chọn 1 mã để sang bước xuất CSV tổng hợp + prompt.</p>
    {% if employees %}
    <form method="post" action="/prepare" class="row">
      <div>
        <label for="ma_nv">Hoặc nhập mã trực tiếp</label>
        <input type="text" id="ma_nv" name="ma_nv" list="emp_list" value="{{ employees[0].ma }}" required>
        <datalist id="emp_list">
          {% for e in employees %}<option value="{{ e.ma }}">{{ e.ma }} — {{ e.ten }}</option>{% endfor %}
        </datalist>
      </div>
      <button class="btn btn-primary" type="submit">Tiếp tục →</button>
    </form>
    <div class="chips">
      {% for e in employees %}<a class="chip" href="/prepare?ma_nv={{ e.ma }}">{{ e.ma }} · {{ e.ten }}</a>{% endfor %}
    </div>
    {% else %}
    <div class="err">Không đọc được nhân viên nào. Kiểm tra lại: bạn đã tải đúng FILE CHI TIẾT
      vào ô ① chưa? (File này phải chứa cột Mã nhân viên / Họ và tên theo từng tiêu chí.)</div>
    {% endif %}
  </div>
</div></body></html>""")

PREPARE_TMPL = Template("""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<title>Chuẩn bị — {{ ma_nv }}</title><style>{{ css }}</style></head><body>
<div class="bar"><span class="tag">360°</span><h1>Xuất CSV + prompt — {{ s.employee.ho_ten }} ({{ ma_nv }})</h1>
  <a class="btn btn-ghost" href="/employees" style="margin-left:auto">← Nhân viên khác</a></div>
<div class="wrap">
  <div class="card">""" + STEPBAR + """</div>

  <div class="card">
    <h2>Kết quả tính điểm</h2>
    <div class="row" style="align-items:center">
      <div><div class="big">{{ '%.2f'|format(s.total_360) if s.total_360 is not none else 'N/A' }}</div>
        <div style="font-size:12px;color:#777">TỔNG 360° / 5.00 · {{ s.badge.label }}</div></div>
      <div style="flex:1">
        <table class="summary">
          <tr><th>Nhóm</th><th>Điểm</th><th>Hoàn thành</th></tr>
          {% for rel in s.relationship_order %}{% set g = s.group_averages[rel] %}
          <tr><td>{{ g.label }}</td>
            <td>{{ '%.4f'|format(g.score) if g.score is not none else 'N/A' }}</td>
            <td>{{ g.n_completed }}/{{ g.n_total }}</td></tr>
          {% endfor %}
        </table>
      </div>
    </div>
    <div class="links" style="margin-top:14px">
      <b>File đã xuất từ 2 file bạn tải lên:</b>
      <a class="btn btn-ghost btn-sm" href="/file/{{ files.csv }}">⬇ CSV Tổng hợp</a>
      <a class="btn btn-ghost btn-sm" href="/file/{{ files.prompt }}">⬇ prompt.txt</a>
      <a class="btn btn-ghost btn-sm" href="/file/{{ files.json }}">⬇ structured.json</a>
    </div>
  </div>

  <div class="card">
    <h2>Bước 2 · Đưa prompt này cho Claude</h2>
    <p class="sub">Bấm <b>Copy</b>, dán vào Claude (Claude Code hoặc claude.ai). Claude sẽ trả về
      MỘT object JSON — copy lại object đó để dùng ở Bước 3.</p>
    <div class="codehdr">
      <span class="name">{{ files.prompt }}</span>
      <button class="btn btn-ghost btn-sm" type="button" onclick="copyPrompt()">⧉ Copy prompt</button>
      <span class="copied" id="copied">✓ Đã copy</span>
    </div>
    <textarea id="promptbox" rows="14" readonly>{{ prompt_text }}</textarea>
  </div>

  <div class="card">
    <h2>Bước 3 · Dán kết quả của Claude vào đây</h2>
    <p class="sub">Dán nguyên object JSON Claude trả về (có thể kèm khối <code>```json</code>,
      hệ thống tự bóc). Sản phẩm sẽ ghép vào template và render báo cáo.</p>
    <form method="post" action="/finalize">
      <input type="hidden" name="ma_nv" value="{{ ma_nv }}">
      <textarea name="claude_json" rows="12" placeholder="Dán JSON Claude trả về vào đây..."></textarea>
      <div class="row" style="margin-top:12px">
        <button class="btn btn-primary" type="submit" name="mode" value="claude">Ghép nội dung Claude → Tạo báo cáo</button>
        <button class="btn btn-ghost" type="submit" name="mode" value="default">Xem nhanh (nội dung mặc định, bỏ qua Claude)</button>
      </div>
      <div class="hint">Mẹo: chưa cần Claude vẫn xem được — chọn “nội dung mặc định” để hệ thống tự sinh
        phần định tính theo luật từ số liệu.</div>
    </form>
  </div>
</div>
<script>
function copyPrompt(){
  var t=document.getElementById('promptbox');
  t.select(); t.setSelectionRange(0, t.value.length);
  var done=function(){var c=document.getElementById('copied');c.style.display='inline';
    setTimeout(function(){c.style.display='none';},1800);};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t.value).then(done,function(){document.execCommand('copy');done();});}
  else{document.execCommand('copy');done();}
}
</script>
</body></html>""")

RESULT_TMPL = Template("""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<title>Báo cáo 360° — {{ ma_nv }}</title><style>{{ css }}</style></head><body>
<div class="bar"><span class="tag">360°</span><h1>Báo cáo — {{ s.employee.ho_ten }} ({{ ma_nv }})</h1>
  <a class="btn btn-ghost" href="/prepare?ma_nv={{ ma_nv }}" style="margin-left:auto">← Sửa/đổi nội dung</a>
  <a class="btn btn-ghost" href="/">Tải file khác</a></div>
<div class="wrap">
  <div class="card">""" + STEPBAR + """</div>
  <div class="card">
    {% if content_source == 'claude' %}
      <div class="ok">✓ Báo cáo dùng nội dung định tính <b>từ Claude</b> (đã ghép vào template).</div>
    {% else %}
      <div class="flash info">Báo cáo đang dùng nội dung <b>mặc định (rule-based)</b>.
        Quay lại bước trước để dán kết quả Claude nếu muốn nội dung chất lượng hơn.</div>
    {% endif %}
    <div class="links" style="margin-top:14px">
      <b>Tải file:</b>
      <a class="btn btn-ghost btn-sm" href="/file/{{ files.html }}" target="_blank">HTML (tab mới)</a>
      <a class="btn btn-ghost btn-sm" href="/file/{{ files.csv }}">CSV Tổng hợp</a>
      <a class="btn btn-ghost btn-sm" href="/file/{{ files.json }}">Structured JSON</a>
      {% if files.claude %}<a class="btn btn-ghost btn-sm" href="/file/{{ files.claude }}">claude_content.json</a>{% endif %}
      {% if files.pdf %}<a class="btn btn-green btn-sm" href="/file/{{ files.pdf }}">⬇ PDF</a>
      {% else %}<span class="hint">PDF: bỏ qua (thiếu GTK trên Windows — xem requirements.txt).</span>{% endif %}
    </div>
  </div>
  <div class="card"><iframe src="/file/{{ files.html }}" title="Báo cáo"></iframe></div>
</div></body></html>""")

ERROR_TMPL = Template("""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<title>Lỗi</title><style>{{ css }}</style></head><body>
<div class="bar"><span class="tag">360°</span><h1>Có lỗi xảy ra</h1>
  <a class="btn btn-ghost" href="{{ back or '/' }}" style="margin-left:auto">← Quay lại</a></div>
<div class="wrap"><div class="card"><div class="err">{{ message }}</div></div></div>
</body></html>""")


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------
def list_employees(data_dir):
    """Đọc file Chi tiết (nếu có) để liệt kê các mã nhân viên + tên."""
    path = os.path.join(data_dir, config.INPUT_CHI_TIET)
    if not os.path.isfile(path):
        return []
    try:
        df = data_loader.load_chi_tiet(path)
        seen, out = set(), []
        for _, r in df.iterrows():
            ma = str(r["ma_nhan_vien"]).strip()
            if ma and ma not in seen:
                seen.add(ma)
                out.append({"ma": ma, "ten": str(r["ho_ten"]).strip()})
        return out
    except Exception:  # noqa: BLE001
        return []


def data_exists(data_dir):
    """True nếu đã có cả 2 file CSV trong thư mục data."""
    return (os.path.isfile(os.path.join(data_dir, config.INPUT_CHI_TIET))
            and os.path.isfile(os.path.join(data_dir, config.INPUT_TONG_HOP)))


def run_sample_generator(data_dir):
    """Nạp & chạy data/make_sample_data.py để sinh 2 file CSV demo."""
    import importlib.util
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "make_sample_data.py")
    spec = importlib.util.spec_from_file_location("make_sample_data", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    chi_tiet = os.path.join(data_dir, config.INPUT_CHI_TIET)
    tong_hop = os.path.join(data_dir, config.INPUT_TONG_HOP)
    mod.write_chi_tiet(chi_tiet)
    mod.write_tong_hop(tong_hop)


def _read_text(path):
    """Đọc file text UTF-8 an toàn (trả '' nếu lỗi)."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _load_structured(ma_nv):
    """Đọc lại structured_<MaNV>.json đã tạo ở bước chuẩn bị."""
    path = os.path.join(OUT_DIR, config.OUT_STRUCTURED.format(ma_nv=ma_nv))
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "Report360/3.0"

    # --- helpers gửi phản hồi ---
    def _send_html(self, body, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error_page(self, message, back=None):
        self._send_html(ERROR_TMPL.render(
            css=PAGE_CSS, message=html.escape(message), back=back), status=500)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    # --- GET ---
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._render_upload()
        elif path == "/employees":
            self._render_employees()
        elif path == "/sample":
            try:
                run_sample_generator(DATA_DIR)
                self._render_employees(flash="Đã tạo dữ liệu mẫu trong thư mục '%s'." % DATA_DIR)
            except Exception:  # noqa: BLE001
                self._send_error_page("Không tạo được dữ liệu mẫu:\n" + traceback.format_exc())
        elif path == "/prepare":
            self._do_prepare((query.get("ma_nv", [""])[0]).strip())
        elif path.startswith("/file/"):
            self._serve_file(urllib.parse.unquote(path[len("/file/"):]))
        else:
            self._send_html("<h1>404</h1>", status=404)

    # --- POST ---
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        ctype = self.headers.get("Content-Type", "")

        if parsed.path == "/upload":
            self._do_upload(ctype)
            return

        # Các form còn lại dùng application/x-www-form-urlencoded.
        body = self._read_body().decode("utf-8", "replace")
        form = urllib.parse.parse_qs(body, keep_blank_values=True)
        if parsed.path == "/prepare":
            self._do_prepare((form.get("ma_nv", [""])[0]).strip())
        elif parsed.path == "/finalize":
            ma = (form.get("ma_nv", [""])[0]).strip()
            mode = (form.get("mode", ["claude"])[0]).strip()
            claude_json = form.get("claude_json", [""])[0]
            self._do_finalize(ma, mode, claude_json)
        else:
            self._send_html("<h1>404</h1>", status=404)

    # --- BƯỚC 1: nhận 2 file người dùng tải lên ---
    def _do_upload(self, ctype):
        body = self._read_body()
        try:
            _fields, files = parse_multipart(ctype, body)
        except Exception:  # noqa: BLE001
            self._send_error_page("Không đọc được dữ liệu tải lên:\n" + traceback.format_exc())
            return

        chi_tiet = files.get("chi_tiet")
        tong_hop = files.get("tong_hop")
        if not _filepart_ok(chi_tiet) or not _filepart_ok(tong_hop):
            self._send_error_page(
                "Vui lòng chọn ĐỦ 2 file CSV: ① File Chi tiết và ② File Tổng hợp.", back="/")
            return

        # Lưu 2 file vào thư mục data/ đúng tên hệ thống dùng (ghi đè file cũ).
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(os.path.join(DATA_DIR, config.INPUT_CHI_TIET), "wb") as f:
                f.write(chi_tiet[1])
            with open(os.path.join(DATA_DIR, config.INPUT_TONG_HOP), "wb") as f:
                f.write(tong_hop[1])
        except OSError as exc:
            self._send_error_page(f"Không lưu được file tải lên: {exc}", back="/")
            return

        # Đọc thử để liệt kê nhân viên; nếu rỗng -> nhiều khả năng tải nhầm file.
        employees = list_employees(DATA_DIR)
        flash = ("Đã nhận: '%s' (chi tiết) + '%s' (tổng hợp). "
                 % (html.escape(chi_tiet[0]), html.escape(tong_hop[0])))
        if not employees:
            flash += "Nhưng chưa đọc được nhân viên nào — kiểm tra lại ô ① có đúng FILE CHI TIẾT không."
        self._render_employees(flash=flash)

    # --- BƯỚC 2: chuẩn bị (tính điểm + xuất CSV/prompt) ---
    def _do_prepare(self, ma_nv):
        if not ma_nv:
            self._send_error_page("Vui lòng chọn/nhập Mã nhân viên.", back="/employees")
            return
        if not data_exists(DATA_DIR):
            self._send_error_page("Chưa có dữ liệu. Hãy tải lên 2 file CSV trước.", back="/")
            return
        try:
            prep = pipeline.prepare(ma_nv=ma_nv, data_dir=DATA_DIR, out_dir=OUT_DIR)
        except (FileNotFoundError, ValueError) as exc:
            self._send_error_page(str(exc), back="/employees")
            return
        except Exception:  # noqa: BLE001
            self._send_error_page("Lỗi không mong muốn:\n" + traceback.format_exc(), back="/employees")
            return

        prompt_text = _read_text(prep["prompt_txt"])
        files = {
            "csv": os.path.basename(prep["tong_hop_csv"]),
            "prompt": os.path.basename(prep["prompt_txt"]),
            "json": os.path.basename(prep["structured_json"]),
        }
        self._send_html(PREPARE_TMPL.render(
            css=PAGE_CSS, ma_nv=ma_nv, s=prep["structured"], files=files,
            prompt_text=html.escape(prompt_text), step=2,
        ))

    # --- BƯỚC 3: hoàn thiện (ghép nội dung Claude + render) ---
    def _do_finalize(self, ma_nv, mode, claude_json):
        if not ma_nv:
            self._send_error_page("Thiếu Mã nhân viên.")
            return
        back = "/prepare?ma_nv=" + urllib.parse.quote(ma_nv)

        try:
            structured = _load_structured(ma_nv)
        except OSError:
            self._send_error_page(
                "Chưa có dữ liệu chuẩn bị cho nhân viên này. Hãy chạy Bước 2 trước.", back="/employees")
            return

        force_default = (mode == "default")
        if not force_default:
            try:
                content_provider.save_claude_content(OUT_DIR, ma_nv, claude_json)
            except ValueError as exc:
                self._send_error_page(str(exc), back=back)
                return

        try:
            fin = pipeline.finalize(
                ma_nv=ma_nv, out_dir=OUT_DIR, structured=structured,
                force_default=force_default,
            )
        except Exception:  # noqa: BLE001
            self._send_error_page("Lỗi khi render báo cáo:\n" + traceback.format_exc(), back=back)
            return

        claude_file = os.path.join(OUT_DIR, config.OUT_CONTENT.format(ma_nv=ma_nv))
        files = {
            "html": os.path.basename(fin["html"]),
            "pdf": os.path.basename(fin["pdf"]) if fin["pdf"] else None,
            "csv": config.OUT_TONGHOP.format(ma_nv=ma_nv),
            "json": config.OUT_STRUCTURED.format(ma_nv=ma_nv),
            "claude": os.path.basename(claude_file) if os.path.isfile(claude_file) else None,
        }
        self._send_html(RESULT_TMPL.render(
            css=PAGE_CSS, ma_nv=ma_nv, s=structured, files=files,
            content_source=fin["content_source"], step=3,
        ))

    # --- các trang ---
    def _render_upload(self, flash=None):
        self._send_html(UPLOAD_TMPL.render(
            css=PAGE_CSS, data_dir=DATA_DIR, has_data=data_exists(DATA_DIR),
            flash=flash, step=1,
        ))

    def _render_employees(self, flash=None):
        self._send_html(EMPLOYEES_TMPL.render(
            css=PAGE_CSS, employees=list_employees(DATA_DIR), flash=flash, step=1,
        ))

    def _serve_file(self, name):
        # Chỉ cho phép tên file (không cho path traversal).
        name = os.path.basename(name)
        full = os.path.join(OUT_DIR, name)
        if not os.path.isfile(full):
            self._send_html("<h1>404 - không thấy file</h1>", status=404)
            return
        ext = os.path.splitext(name)[1].lower()
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        # Log gọn, an toàn encoding.
        try:
            sys.stderr.write("[web] " + (fmt % args) + "\n")
        except Exception:  # noqa: BLE001
            pass


def main():
    global DATA_DIR, OUT_DIR
    parser = argparse.ArgumentParser(description="Giao diện web tạo báo cáo 360° (tải file + 2 bước Claude).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=DATA_DIR)
    parser.add_argument("--out-dir", default=OUT_DIR)
    args = parser.parse_args()

    DATA_DIR, OUT_DIR = args.data_dir, args.out_dir

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    os.makedirs(OUT_DIR, exist_ok=True)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print("=" * 60)
    print("  Hệ thống báo cáo 360° — giao diện web (tải file + 2 bước)")
    print(f"  Mở trình duyệt tại: {url}")
    print("  Nhấn Ctrl+C để dừng.")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng server.")
        httpd.server_close()


if __name__ == "__main__":
    main()
