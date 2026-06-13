# -*- coding: utf-8 -*-
"""
batch_report.py
===============
PHASE 3 — Xuất BÁO CÁO PDF HÀNG LOẠT từ:
  - File Chi tiết (tính điểm + biểu đồ cho từng nhân viên), và
  - "File thứ 4" đã rà soát (nội dung AI + trạng thái duyệt).

Có BỘ LỌC khi xuất: Bộ phận / Chức danh / Cấp bậc / Rating (xếp loại) / trạng
thái rà soát. Render HTML (Jinja2) -> PDF (Playwright, mở Chromium 1 lần cho cả lô).

CÁCH DÙNG:
  # Xuất tất cả (nội dung AI nếu có, nếu trống dùng mặc định theo luật)
  python batch_report.py

  # Lọc theo bộ phận + cấp bậc, chỉ NV đã duyệt, giới hạn 20 bản để thử
  python batch_report.py --bo-phan "Khối Công nghệ" --cap-bac T2 --only-approved --limit 20

  # Chỉ xuất HTML (bỏ PDF) để xem nhanh
  python batch_report.py --no-pdf --limit 5
"""

import argparse
import csv
import os
import re
import sys
import unicodedata

import config
import data_loader
import batch_builder
import file4_reader
import report_content
import report_renderer
import chart_generator
import pdf_protect
import utils
from score_calculator import strip_accents


# ---------------------------------------------------------------------------
# Tên file báo cáo theo TÊN người (an toàn cho hệ thống file)
# ---------------------------------------------------------------------------
def _safe_filename(text, fallback="nhan_vien"):
    """Chuyển 'Trần Đức Long' -> 'Tran_Duc_Long' (bỏ dấu, giữ hoa/thường, thay
    ký tự không an toàn bằng '_'). Trả về fallback nếu rỗng."""
    s = unicodedata.normalize("NFD", str(text or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"[^A-Za-z0-9_]+", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or fallback


def _unique_base(ho_ten, ma_nv, used):
    """Tên file CƠ SỞ duy nhất theo họ tên. Nếu trùng tên -> nối thêm mã NV
    (mã NV là duy nhất nên đảm bảo không đè file). `used` là set tích luỹ."""
    base = _safe_filename(ho_ten)
    if base in used:
        base = f"{base}_{_safe_filename(ma_nv, ma_nv)}"
    used.add(base)
    return base


# ---------------------------------------------------------------------------
# Lọc nhân viên
# ---------------------------------------------------------------------------
def _match(value, wanted):
    """True nếu `wanted` rỗng, hoặc một trong các giá trị (phân tách bằng ',')
    là chuỗi con của `value` (không phân biệt hoa/thường/dấu)."""
    if not wanted:
        return True
    v = strip_accents(value or "")
    return any(strip_accents(w.strip()) in v for w in str(wanted).split(",") if w.strip())


def select(structured_list, records, filters, only_approved, skip_empty,
           only_ma=None, require_file4=False):
    """Lọc danh sách -> list (structured, record|None). Trả về (selected, stats).

    `only_ma` (set/list mã NV): nếu có -> CHỈ xuất đúng những người này (chọn tay),
    BỎ QUA bộ lọc & 'chỉ đã duyệt' (người dùng đã chủ động chọn).
    `require_file4`: nếu True -> CHỈ xuất những người CÓ TRONG File thứ 4 (records)."""
    only_set = {str(m).strip() for m in only_ma} if only_ma else None
    selected = []
    stats = {"total": len(structured_list), "no_data": 0, "filtered_out": 0,
             "not_approved": 0, "not_in_file4": 0, "manager_team_unsupported": False}

    if filters.get("manager") or filters.get("team"):
        stats["manager_team_unsupported"] = True   # không có cột nguồn trong dữ liệu

    for s in structured_list:
        ma = s["employee"]["ma_nv"]
        rec = records.get(ma)

        if skip_empty and s["total_360"] is None:
            stats["no_data"] += 1
            continue

        # Chế độ chọn tay: chỉ giữ người được chọn, bỏ qua filter + duyệt.
        if only_set is not None:
            if ma in only_set:
                selected.append((s, rec))
            else:
                stats["filtered_out"] += 1
            continue

        # Chỉ tạo báo cáo cho người CÓ TRONG File thứ 4.
        if require_file4 and rec is None:
            stats["not_in_file4"] += 1
            continue

        emp = s["employee"]
        if not (_match(emp["bo_phan"], filters.get("bo_phan"))
                and _match(emp["chuc_danh"], filters.get("chuc_danh"))
                and _match(emp["cap_bac"], filters.get("cap_bac"))
                and _match(s["badge"]["label"], filters.get("rating"))):
            stats["filtered_out"] += 1
            continue

        if only_approved:
            if not (rec and file4_reader.is_approved(rec)):
                stats["not_approved"] += 1
                continue

        selected.append((s, rec))
    stats["selected"] = len(selected)
    return selected, stats


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run(data_dir="data", out_dir="output/reports", file4_path=None,
        filters=None, only_approved=False, skip_empty=True, limit=None,
        make_pdf=True, report_date=None, structured_list=None, progress_cb=None,
        encrypt=None, only_ma=None, from_file4=False):
    utils.force_utf8_console()
    filters = filters or {}
    if encrypt is None:
        encrypt = config.PDF_ENCRYPT

    if file4_path is None:
        file4_path = os.path.join("output", config.OUT_BATCH_XLSX_WIDE)

    if structured_list is None:
        chi_tiet_path = os.path.join(data_dir, config.INPUT_CHI_TIET)
        if not os.path.isfile(chi_tiet_path):
            raise FileNotFoundError(f"Không tìm thấy file Chi tiết: {chi_tiet_path}")
        print(f"[1/4] Đọc Chi tiết + tính điểm toàn bộ ...")
        df = data_loader.load_chi_tiet(chi_tiet_path)
        structured_list, _errors = batch_builder.build_all_structured(df, report_date=report_date)
        print(f"      -> {len(structured_list)} NV")
    else:
        print(f"[1/4] Dùng dữ liệu đã tính sẵn ({len(structured_list)} NV)")

    records = {}
    if os.path.isfile(file4_path):
        records = file4_reader.read_file4(file4_path)
        n_ai = sum(1 for r in records.values() if file4_reader.has_ai_content(r))
        print(f"[2/4] Đọc File thứ 4: {len(records)} dòng | có nội dung AI: {n_ai}")
    else:
        print(f"[2/4] (Không thấy File thứ 4 '{file4_path}' -> dùng nội dung mặc định theo luật)")

    selected, stats = select(structured_list, records, filters, only_approved, skip_empty,
                             only_ma, require_file4=from_file4)
    if stats["manager_team_unsupported"]:
        print("      ! Bộ lọc Manager/Team chưa hỗ trợ (không có cột nguồn trong dữ liệu) — đã bỏ qua.")
    print(f"[3/4] Lọc: chọn {stats['selected']}/{stats['total']} "
          f"(thiếu dữ liệu {stats['no_data']}, loại bởi filter {stats['filtered_out']}, "
          f"chưa duyệt {stats['not_approved']}, ngoài File 4 {stats['not_in_file4']})")
    if limit:
        selected = selected[:limit]
        print(f"      -> giới hạn {len(selected)} bản (--limit)")
    if not selected:
        print("      (Không có NV nào khớp — dừng.)")
        return {"rendered": 0, "out_dir": out_dir}

    os.makedirs(out_dir, exist_ok=True)
    # Dọn báo cáo cũ -> bộ kết quả (PDF + _index.csv) luôn KHỚP đúng lần xuất này
    # (tránh file mồ côi khi đổi cách đặt tên file hoặc khi xuất tập khác).
    _cleared = 0
    for fn in os.listdir(out_dir):
        if fn.startswith("BAOCAO_") and fn.lower().endswith((".pdf", ".html")):
            try:
                os.remove(os.path.join(out_dir, fn))
                _cleared += 1
            except OSError:
                pass
    if _cleared:
        print(f"      (đã dọn {_cleared} file báo cáo cũ)")
    print(f"[4/4] Render {len(selected)} báo cáo (HTML{' + PDF' if make_pdf else ''}) ...")

    do_encrypt = bool(encrypt and make_pdf)
    manifest_rows = []
    index_rows = []
    used_names = set()
    renderer = None
    try:
        if make_pdf:
            from pdf_playwright import PdfRenderer
            renderer = PdfRenderer().__enter__()

        for i, (s, rec) in enumerate(selected, 1):
            ma = s["employee"]["ma_nv"]
            # Tên file = TÊN người được làm báo cáo (an toàn cho hệ thống file).
            base = _unique_base(s["employee"]["ho_ten"], ma, used_names)
            content, source = report_content.build_content(s, rec)
            charts = chart_generator.build_all_charts(s)
            html = report_renderer.build_html(s, content, source, charts)

            html_path = os.path.join(out_dir, f"BAOCAO_{base}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            pdf_path = ""
            if renderer:
                pdf_path = os.path.join(out_dir, f"BAOCAO_{base}.pdf")
                renderer.render(html, pdf_path)
                if do_encrypt:
                    user_pw = pdf_protect.password_for(ma)
                    pdf_protect.encrypt_pdf_inplace(pdf_path, user_pw)
                    manifest_rows.append({"ma_nv": ma,
                                          "ho_ten": s["employee"]["ho_ten"],
                                          "password": user_pw})

            index_rows.append({
                "ma_nv": ma, "ho_ten": s["employee"]["ho_ten"],
                "bo_phan": s["employee"]["bo_phan"], "chuc_danh": s["employee"]["chuc_danh"],
                "cap_bac": s["employee"]["cap_bac"], "tong_360": s["total_360"],
                "xep_loai": s["badge"]["label"], "noi_dung": source,
                "trang_thai_ra_soat": (rec or {}).get("review", {}).get("trang_thai_ra_soat", ""),
                "pdf": os.path.basename(pdf_path) if pdf_path else "",
            })
            if progress_cb:
                progress_cb(i, len(selected), ma)
            if i % 25 == 0 or i == len(selected):
                print(f"      ... {i}/{len(selected)}")
    finally:
        if renderer:
            renderer.__exit__(None, None, None)

    # Ghi index
    index_path = os.path.join(out_dir, "_index.csv")
    with open(index_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(index_rows[0].keys()))
        w.writeheader()
        w.writerows(index_rows)

    # Ghi manifest mật khẩu (TUYỆT MẬT) ra THƯ MỤC CHA của out_dir (không lẫn vào
    # thư mục PDF được phát/zip), để HR phát mật khẩu cho từng người.
    manifest_path = None
    if manifest_rows:
        parent = os.path.dirname(os.path.abspath(out_dir))
        manifest_path = os.path.join(parent, config.OUT_PASSWORD_MANIFEST)
        pdf_protect.write_manifest(manifest_rows, manifest_path)

    print(f"\n===== HOÀN TẤT — {len(index_rows)} báo cáo =====")
    print(f"  Thư mục : {out_dir}")
    print(f"  Index   : {index_path}")
    if do_encrypt:
        print(f"  Mã hoá  : BẬT (AES-256) — scheme mật khẩu = '{config.PDF_PASSWORD_SCHEME}'")
        print(f"  Manifest: {manifest_path}  (TUYỆT MẬT — đừng phát kèm báo cáo)")
    return {"rendered": len(index_rows), "out_dir": out_dir, "index": index_path,
            "encrypted": do_encrypt, "manifest": manifest_path}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Xuất báo cáo 360° PDF hàng loạt (có bộ lọc).")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out-dir", default="output/reports")
    p.add_argument("--file4", default=None, help="Đường dẫn File thứ 4 (mặc định output/360_AI_input_full.xlsx)")
    p.add_argument("--bo-phan", default=None, help="Lọc Bộ phận (chuỗi con, nhiều giá trị ngăn bằng ',')")
    p.add_argument("--chuc-danh", default=None, help="Lọc Chức danh")
    p.add_argument("--cap-bac", default=None, help="Lọc Cấp bậc (vd T2)")
    p.add_argument("--rating", default=None, help="Lọc Xếp loại (vd 'Tốt','Xuất sắc')")
    p.add_argument("--manager", default=None, help="(chưa hỗ trợ — thiếu cột nguồn)")
    p.add_argument("--team", default=None, help="(chưa hỗ trợ — thiếu cột nguồn)")
    p.add_argument("--only-approved", action="store_true", help="Chỉ xuất NV có Trạng thái rà soát = 'Đã duyệt'")
    p.add_argument("--from-file4", action="store_true", help="Chỉ xuất những người CÓ TRONG File thứ 4")
    p.add_argument("--include-empty", action="store_true", help="Xuất cả NV chưa đủ dữ liệu điểm")
    p.add_argument("--limit", type=int, default=None, help="Giới hạn số bản (để thử)")
    p.add_argument("--no-pdf", action="store_true", help="Chỉ xuất HTML, bỏ PDF")
    p.add_argument("--no-encrypt", action="store_true",
                   help="Tắt mã hoá PDF (mặc định: bật theo config.PDF_ENCRYPT)")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    filters = {"bo_phan": a.bo_phan, "chuc_danh": a.chuc_danh, "cap_bac": a.cap_bac,
               "rating": a.rating, "manager": a.manager, "team": a.team}
    try:
        run(data_dir=a.data_dir, out_dir=a.out_dir, file4_path=a.file4, filters=filters,
            only_approved=a.only_approved, skip_empty=not a.include_empty,
            limit=a.limit, make_pdf=not a.no_pdf, encrypt=not a.no_encrypt,
            from_file4=a.from_file4)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[LỖI] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
