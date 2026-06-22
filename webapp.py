# -*- coding: utf-8 -*-
"""
webapp.py
=========
Giao diện web (dashboard) trực quan cho hệ thống 360° — chạy nội bộ trên trình duyệt.

Luồng:
  Bước 1: bấm "Tính điểm & Sinh File thứ 4"  -> output/360_AI_input_full.xlsx
  Bước 2: bấm "Tự động điền bằng AI" (ai_engine gọi LLM điền cột AI) -> rà soát/duyệt
  Bước 3: chọn bộ lọc -> "Xuất báo cáo PDF" -> xem/tải báo cáo

Tác vụ nặng chạy ở luồng nền; trang tự hỏi tiến độ (progress bar).

Chạy:  .venv\\Scripts\\python.exe webapp.py   ->  http://127.0.0.1:8000
"""

import csv
import io
import os
import threading
import zipfile
from collections import Counter

from flask import (Flask, jsonify, render_template, request,
                   send_file, send_from_directory, abort)

import config
import utils
import data_loader
import batch_builder
import batch_report
import file4_reader
import report_content
import report_renderer
import chart_generator
# (competency_exporter được ai_engine dùng nội bộ — webapp không gọi trực tiếp nữa)
import ai_client          # lớp gọi LLM dùng chung (tính năng AI)
import ai_engine          # A: tự động điền nội dung AI
import ai_qa              # B: trợ lý hỏi-đáp HR (agent)
import ai_review          # C: kiểm chứng grounding

utils.force_utf8_console()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024   # trần upload 1GB/request (an toàn)


@app.errorhandler(413)
def _too_large(e):
    return jsonify({"ok": False, "error": "File tải lên quá lớn (giới hạn 1GB)."}), 413

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "output")
REPORTS_DIR = os.path.join(OUT_DIR, "reports")
FILE4_PATH = os.path.join(OUT_DIR, config.OUT_BATCH_XLSX_WIDE)
AI_CSV_PATH = os.path.join(OUT_DIR, "ai_autofill_result.csv")   # CSV kết quả tự động điền AI

# ---- Trạng thái dùng chung (1 tiến trình, 1 người dùng nội bộ) ----
STATE = {"structured_list": None, "records": {}}
TASK = {"running": False, "name": "", "current": 0, "total": 0,
        "message": "", "error": None, "done": False, "result": None}
_LOCK = threading.Lock()
_MPL_LOCK = threading.Lock()   # bảo vệ matplotlib (pyplot không thread-safe)


# ---------------------------------------------------------------------------
# Tác vụ nền
# ---------------------------------------------------------------------------
def _update(message, current=0, total=0):
    TASK["message"] = message
    TASK["current"] = current
    TASK["total"] = total


def _run_async(name, fn):
    """Chạy fn(update) trong luồng nền nếu chưa có tác vụ nào đang chạy."""
    with _LOCK:
        if TASK["running"]:
            return False
        TASK.update(running=True, name=name, current=0, total=0,
                    message="Đang bắt đầu...", error=None, done=False, result=None)

    def worker():
        try:
            result = fn(_update)
            TASK["result"] = result
            TASK["message"] = "Hoàn tất."
        except Exception as exc:  # noqa: BLE001
            TASK["error"] = f"{type(exc).__name__}: {exc}"
            TASK["message"] = "Lỗi: " + TASK["error"]
        finally:
            TASK["done"] = True
            TASK["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return True


def _task_step1(update):
    path = os.path.join(DATA_DIR, config.INPUT_CHI_TIET)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Thiếu file Chi tiết: {config.INPUT_CHI_TIET} trong data/")
    update("Đọc file Chi tiết...")
    df = data_loader.load_chi_tiet(path)
    update("Tính điểm 360° cho toàn bộ nhân viên...")
    sl, errors = batch_builder.build_all_structured(
        df, progress_cb=lambda d, t: update(f"Tính điểm {d}/{t}...", d, t))
    update("Sinh File thứ 4 (Excel) + prompt chung...")
    with _MPL_LOCK:
        out = batch_builder.write_outputs(sl, OUT_DIR)
    STATE["structured_list"] = sl
    STATE["records"] = _load_records()
    return {"n_emp": len(sl), "errors": len(errors), **out}


def _task_build(update, filters, only_approved, limit, make_pdf, only_ma=None, from_file4=False):
    sl = STATE.get("structured_list")
    if only_ma:
        # CHỌN TAY: chỉ làm báo cáo cho NHỮNG NGƯỜI ĐƯỢC CHỌN.
        if sl is not None:
            sel = {str(m).strip() for m in only_ma}
            sl = [s for s in sl if s["employee"]["ma_nv"] in sel]   # lọc từ bản đã tính (rất nhanh)
        # sl is None -> để batch_report.run() tự tính điểm RIÊNG cho nhóm được chọn
        # (không tính cả 203 người).
    elif sl is None:
        # Tạo theo bộ lọc / toàn bộ -> phải tính tất cả để áp được bộ lọc.
        update("Tính điểm (chưa có sẵn)...")
        df = data_loader.load_chi_tiet(os.path.join(DATA_DIR, config.INPUT_CHI_TIET))
        sl, _ = batch_builder.build_all_structured(
            df, progress_cb=lambda d, t: update(f"Tính điểm {d}/{t}...", d, t))
        STATE["structured_list"] = sl
    update("Đang dựng báo cáo...")
    with _MPL_LOCK:
        res = batch_report.run(
            out_dir=REPORTS_DIR, structured_list=sl, filters=filters,
            only_approved=only_approved, limit=limit, make_pdf=make_pdf, only_ma=only_ma,
            from_file4=from_file4,
            progress_cb=lambda i, t, ma: update(f"Render {i}/{t}: {ma}", i, t))
    return res


# ---------------------------------------------------------------------------
# Tiện ích trạng thái
# ---------------------------------------------------------------------------
def _file_info(name):
    p = os.path.join(DATA_DIR, name)
    if os.path.isfile(p):
        return {"present": True, "size_mb": round(os.path.getsize(p) / 1048576, 1)}
    return {"present": False, "size_mb": 0}


def _load_records():
    if os.path.isfile(FILE4_PATH):
        try:
            return file4_reader.read_file4(FILE4_PATH)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _compute_one(ma_nv):
    """Tính điểm cho ĐÚNG một nhân viên (khi chưa chạy Bước 1 cho cả lô — vd vừa
    upload File thứ 4). Trả về structured dict hoặc None nếu không có dữ liệu."""
    path = os.path.join(DATA_DIR, config.INPUT_CHI_TIET)
    if not os.path.isfile(path):
        return None
    df = data_loader.load_chi_tiet(path)
    key = df["ma_nhan_vien"].astype(str).str.strip()
    sub = df[key == str(ma_nv).strip()]
    if sub.empty:
        return None
    sl, _ = batch_builder.build_all_structured(sub)
    return sl[0] if sl else None


def _ensure_structured_list(only_ma=None, update=None):
    """Trả về structured_list (đã tính). Nếu chưa có thì tính từ file Chi tiết.
    only_ma -> chỉ tính nhóm đó (nhanh, KHÔNG cache vì là tập con)."""
    sl = STATE.get("structured_list")
    if sl is not None:
        return sl
    path = os.path.join(DATA_DIR, config.INPUT_CHI_TIET)
    if not os.path.isfile(path):
        return None
    if update:
        update("Tính điểm (chưa có sẵn)...")
    df = data_loader.load_chi_tiet(path)
    if only_ma:
        sel = {str(m).strip() for m in only_ma}
        df = df[df["ma_nhan_vien"].astype(str).str.strip().isin(sel)]
    cb = (lambda d, t: update(f"Tính điểm {d}/{t}...", d, t)) if update else None
    sl, _ = batch_builder.build_all_structured(df, progress_cb=cb)
    if not only_ma:
        STATE["structured_list"] = sl    # bộ đầy đủ -> cache lại
    return sl


def _task_ai_autofill(update, only_ma, only_missing):
    """Tự động sinh nội dung AI rồi ghi vào cột AI của File thứ 4 (tính năng A)."""
    if not os.path.isfile(FILE4_PATH):
        raise FileNotFoundError("Chưa có File thứ 4 — hãy chạy Bước 1 trước khi tự động điền AI.")
    if not ai_client.is_configured():
        raise RuntimeError("Chưa cấu hình API key. Hãy điền OPENAI_API_KEY trong file .env "
                           "rồi khởi động lại server.")
    sl = _ensure_structured_list(only_ma=only_ma, update=update)
    if not sl:
        raise RuntimeError("Không có dữ liệu để tính. Hãy tải file Chi tiết (Bước dữ liệu) trước.")
    update("Đang sinh nội dung bằng AI...")
    stats = ai_engine.autofill_file4(
        FILE4_PATH, sl, only_ma=only_ma, only_missing=only_missing, csv_out=AI_CSV_PATH,
        progress_cb=lambda d, t: update(f"AI điền {d}/{t}...", d, t))
    STATE["records"] = _load_records()
    return stats


def _report_index_map():
    """Đọc output/reports/_index.csv -> {ma_nv: tên_file_pdf}. Tên file báo cáo
    nay theo TÊN người nên cần index để biết file của từng mã NV."""
    idx = os.path.join(REPORTS_DIR, "_index.csv")
    out = {}
    if os.path.isfile(idx):
        try:
            with open(idx, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    ma = (row.get("ma_nv") or "").strip()
                    pdf = (row.get("pdf") or "").strip()
                    if ma and pdf:
                        out[ma] = pdf
        except OSError:
            pass
    return out


def _summary():
    sl = STATE.get("structured_list")
    if not sl:
        return {"done": False}
    ratings = Counter(s["badge"]["label"] for s in sl)
    bo_phan = sorted({s["employee"]["bo_phan"] for s in sl if s["employee"]["bo_phan"]})
    cap_bac = sorted({s["employee"]["cap_bac"] for s in sl if s["employee"]["cap_bac"]})
    return {
        "done": True,
        "n_emp": len(sl),
        "n_full": sum(1 for s in sl if s["total_360"] is not None),
        "ratings": dict(ratings),
        "bo_phan": bo_phan,
        "cap_bac": cap_bac,
        "ratings_list": sorted(ratings),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/state")
def api_state():
    n_reports = len([f for f in os.listdir(REPORTS_DIR) if f.endswith(".pdf")]) \
        if os.path.isdir(REPORTS_DIR) else 0
    records = STATE.get("records") or {}
    n_file4 = len(records)
    return jsonify({
        "files": {
            "chi_tiet": _file_info(config.INPUT_CHI_TIET),
            "tong_hop": _file_info(config.INPUT_TONG_HOP),
            "tieu_chi": _file_info(config.INPUT_COMPETENCY),
        },
        "file4_exists": os.path.isfile(FILE4_PATH),
        "file4_ai_filled": sum(1 for r in records.values() if file4_reader.has_ai_content(r)),
        "file4_approved": sum(1 for r in records.values() if file4_reader.is_approved(r)),
        "n_reports": n_reports,
        "n_file4": n_file4,
        "encrypt": config.PDF_ENCRYPT,
        "password_scheme": config.PDF_PASSWORD_SCHEME,
        "summary": _summary(),
        "task": TASK,
    })


@app.route("/api/progress")
def api_progress():
    return jsonify(TASK)


@app.route("/api/step1", methods=["POST"])
def api_step1():
    ok = _run_async("step1", _task_step1)
    return jsonify({"started": ok})


@app.route("/api/build", methods=["POST"])
def api_build():
    body = request.get_json(silent=True) or {}
    filters = {k: (body.get(k) or "").strip() or None
               for k in ("bo_phan", "chuc_danh", "cap_bac", "rating")}
    only_approved = bool(body.get("only_approved"))
    make_pdf = not bool(body.get("no_pdf"))
    from_file4 = bool(body.get("from_file4"))
    limit = body.get("limit")
    limit = int(limit) if str(limit).isdigit() and int(limit) > 0 else None
    # Chọn tay: danh sách mã NV cụ thể (ưu tiên hơn filter nếu có).
    ma_list = body.get("ma_list")
    only_ma = [str(m).strip() for m in ma_list if str(m).strip()] \
        if isinstance(ma_list, list) and ma_list else None
    ok = _run_async("build",
                    lambda u: _task_build(u, filters, only_approved, limit, make_pdf,
                                          only_ma, from_file4))
    return jsonify({"started": ok})


@app.route("/api/employees")
def api_employees():
    sl = STATE.get("structured_list") or []
    records = STATE.get("records") or {}
    pdf_map = _report_index_map()
    rows = []
    seen = set()
    for s in sl:
        ma = s["employee"]["ma_nv"]
        seen.add(ma)
        rec = records.get(ma)
        pdf_file = pdf_map.get(ma)
        has_pdf = bool(pdf_file and os.path.isfile(os.path.join(REPORTS_DIR, pdf_file)))
        rows.append({
            "ma_nv": ma,
            "ho_ten": s["employee"]["ho_ten"],
            "bo_phan": s["employee"]["bo_phan"],
            "chuc_danh": s["employee"]["chuc_danh"],
            "cap_bac": s["employee"]["cap_bac"],
            "tong_360": round(s["total_360"], 2) if s["total_360"] is not None else None,
            "rating": s["badge"]["label"],
            "rating_color": s["badge"]["color"],
            "in_file4": rec is not None,
            "has_ai": bool(rec and file4_reader.has_ai_content(rec)),
            "approved": bool(rec and file4_reader.is_approved(rec)),
            "has_pdf": has_pdf,
            "pdf_file": pdf_file if has_pdf else None,
        })
    # Người CÓ trong File thứ 4 nhưng CHƯA tính điểm (vd vừa upload File 4, chưa
    # chạy Bước 1) -> vẫn hiện để CHỌN ngay; điểm/xếp loại tính khi tạo báo cáo.
    for ma, rec in records.items():
        if ma in seen:
            continue
        ident = rec.get("identity", {})
        pdf_file = pdf_map.get(ma)
        has_pdf = bool(pdf_file and os.path.isfile(os.path.join(REPORTS_DIR, pdf_file)))
        rows.append({
            "ma_nv": ma,
            "ho_ten": ident.get("ho_ten", ""),
            "bo_phan": ident.get("ban_chuoi_khoi", ""),
            "chuc_danh": ident.get("chuc_danh", ""),
            "cap_bac": ident.get("cap_bac", ""),
            "tong_360": None,
            "rating": "—",
            "rating_color": "#9aa7b4",
            "in_file4": True,
            "has_ai": file4_reader.has_ai_content(rec),
            "approved": file4_reader.is_approved(rec),
            "has_pdf": has_pdf,
            "pdf_file": pdf_file if has_pdf else None,
        })
    return jsonify(rows)


@app.route("/preview/<ma_nv>")
def preview(ma_nv):
    if TASK["running"]:
        return "Đang có tác vụ chạy, thử lại sau khi xong.", 409
    sl = STATE.get("structured_list") or []
    s = next((x for x in sl if x["employee"]["ma_nv"] == ma_nv), None)
    if s is None:
        s = _compute_one(ma_nv)   # vừa upload File 4, chưa chạy Bước 1 -> tính riêng người này
    if s is None:
        abort(404)
    rec = (STATE.get("records") or {}).get(ma_nv)
    content, source = report_content.build_content(s, rec)
    with _MPL_LOCK:
        charts = chart_generator.build_all_charts(s)
        html = report_renderer.build_html(s, content, source, charts)
    return html


@app.route("/reports/<path:filename>")
def reports(filename):
    return send_from_directory(REPORTS_DIR, filename)


@app.route("/download/file4")
def download_file4():
    if not os.path.isfile(FILE4_PATH):
        abort(404)
    return send_file(FILE4_PATH, as_attachment=True)


@app.route("/download/reports-zip")
def download_zip():
    if not os.path.isdir(REPORTS_DIR):
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(REPORTS_DIR):
            if f.endswith(".pdf"):
                z.write(os.path.join(REPORTS_DIR, f), f)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="bao_cao_360.zip",
                     mimetype="application/zip")


# ---------------------------------------------------------------------------
# TÍNH NĂNG AI (A: tự động điền · B: hỏi-đáp · C: kiểm chứng)
# ---------------------------------------------------------------------------
@app.route("/api/ai-status")
def api_ai_status():
    """Trạng thái cấu hình AI + token đã dùng (cho badge & ô chi phí trên dashboard)."""
    ai_client.reload_env()                  # nạp lại .env để đổi key không cần restart
    cfg = ai_client.settings()
    sl = STATE.get("structured_list")
    return jsonify({
        "configured": ai_client.is_configured(),
        "model": cfg["model"],
        "endpoint": cfg["base_url"] or "api.openai.com",
        "n_emp": len(sl) if sl else 0,
        "usage": ai_client.usage_snapshot(),
        "has_csv": os.path.isfile(AI_CSV_PATH),
    })


@app.route("/api/ai-autofill", methods=["POST"])
def api_ai_autofill():
    """A — Tự động điền 16 trường AI vào File thứ 4 (toàn bộ hoặc nhóm đã chọn)."""
    body = request.get_json(silent=True) or {}
    only_missing = bool(body.get("only_missing"))
    ma_list = body.get("ma_list")
    only_ma = [str(m).strip() for m in ma_list if str(m).strip()] \
        if isinstance(ma_list, list) and ma_list else None
    ok = _run_async("ai-autofill", lambda u: _task_ai_autofill(u, only_ma, only_missing))
    return jsonify({"started": ok})


@app.route("/api/ai-ask", methods=["POST"])
def api_ai_ask():
    """B — Trợ lý hỏi-đáp HR (agent + tool use) trên dữ liệu 360°."""
    body = request.get_json(silent=True) or {}
    q = (body.get("question") or "").strip()
    if not q:
        return jsonify({"ok": False, "error": "Hãy nhập câu hỏi."}), 400
    if not ai_client.is_configured():
        return jsonify({"ok": False, "error": "Chưa cấu hình API key (file .env → OPENAI_API_KEY)."}), 400
    sl = _ensure_structured_list()
    if not sl:
        return jsonify({"ok": False, "error": "Chưa có dữ liệu. Hãy tải file Chi tiết & chạy Bước 1."}), 400
    try:
        res = ai_qa.answer(q, sl)
    except Exception as exc:                       # noqa: BLE001
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify({"ok": True, **res})


@app.route("/api/ai-review/<ma_nv>")
def api_ai_review(ma_nv):
    """C — Kiểm chứng grounding nội dung AI của 1 nhân viên."""
    sl = STATE.get("structured_list") or []
    s = next((x for x in sl if x["employee"]["ma_nv"] == ma_nv), None)
    if s is None:
        s = _compute_one(ma_nv)
    if s is None:
        return jsonify({"ok": False, "error": "Không có dữ liệu điểm cho nhân viên này."}), 404
    rec = (STATE.get("records") or {}).get(ma_nv)
    fields = (rec or {}).get("ai", {})
    if not any((v or "").strip() for v in fields.values()):
        return jsonify({"ok": False, "error": "Nhân viên này chưa có nội dung AI để kiểm chứng "
                        "(hãy Tự động điền AI hoặc nạp File thứ 4 đã có nội dung)."}), 400
    try:
        res = ai_review.check(s, fields, use_judge=ai_client.is_configured())
    except Exception as exc:                       # noqa: BLE001
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify({"ok": True, "ma_nv": ma_nv, "ho_ten": s["employee"]["ho_ten"], **res})


@app.route("/download/ai-csv")
def download_ai_csv():
    """Tải CSV kết quả tự động điền AI (ma_nv + 16 cột) để lưu trữ/đối soát."""
    if not os.path.isfile(AI_CSV_PATH):
        abort(404)
    return send_file(AI_CSV_PATH, as_attachment=True, download_name="ket_qua_ai.csv")


@app.route("/api/upload-inputs", methods=["POST"])
def upload_inputs():
    """Tải lên 3 file đầu vào (CSV) -> lưu vào data/ đúng tên cấu hình.
    Field: chi_tiet / tong_hop / tieu_chi (chấp nhận tải từng phần)."""
    mapping = {
        "chi_tiet": config.INPUT_CHI_TIET,
        "tong_hop": config.INPUT_TONG_HOP,
        "tieu_chi": config.INPUT_COMPETENCY,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    saved = []
    for field, target in mapping.items():
        f = request.files.get(field)
        if f and f.filename:
            if not f.filename.lower().endswith(".csv"):
                return jsonify({"ok": False, "error": f"{field}: cần file .csv (UTF-8)"}), 400
            f.save(os.path.join(DATA_DIR, target))
            saved.append(field)
    if not saved:
        return jsonify({"ok": False, "error": "Chưa chọn file nào."}), 400
    STATE["structured_list"] = None       # dữ liệu mới -> phải tính lại
    return jsonify({"ok": True, "saved": saved})


@app.route("/api/upload-file4", methods=["POST"])
def upload_file4():
    """Tải lên File thứ 4 đã rà soát (ghi đè output/360_AI_input_full.xlsx)."""
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "error": "Cần file .xlsx"}), 400
    os.makedirs(OUT_DIR, exist_ok=True)
    f.save(FILE4_PATH)
    STATE["records"] = _load_records()
    return jsonify({"ok": True, "n_file4": len(STATE["records"]),
                    "ai_filled": sum(1 for r in STATE["records"].values()
                                     if file4_reader.has_ai_content(r))})


if __name__ == "__main__":
    os.makedirs(REPORTS_DIR, exist_ok=True)
    # KHÔNG tự nạp File thứ 4 cũ trên đĩa lúc khởi động: danh sách nhân viên chỉ
    # xuất hiện SAU KHI người dùng tải File thứ 4 lên (hoặc chạy Bước 1) trong
    # phiên hiện tại. Trước đó bảng để TRỐNG.
    STATE["records"] = {}
    print("Mở trình duyệt: http://127.0.0.1:8000")
    app.run(host="127.0.0.1", port=8000, threaded=True, debug=False)
