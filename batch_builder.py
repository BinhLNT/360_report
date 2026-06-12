# -*- coding: utf-8 -*-
"""
batch_builder.py
================
CHẾ ĐỘ BATCH (>= 500 nhân viên).

Thay cho quy trình cũ "1 prompt / 1 người", module này:

  1. Tính điểm 360° cho TOÀN BỘ nhân viên trong file Chi tiết (tái dùng
     score_calculator + structured_data).
  2. Sinh "FILE THỨ 4" dạng Excel (.xlsx): mỗi nhân viên 1 dòng gồm
        [cột dữ liệu gốc/context]  +  [cột AI để Claude điền]  +  [cột rà soát].
  3. Sinh 1 PROMPT CHUNG (prompt_chung.txt) dùng cho mọi nhân viên — mô tả
     vai trò, phương pháp tính điểm, ý nghĩa từng cột AI và schema JSON đầu ra.

KHÔNG gọi AI API ở đây. File thứ 4 + prompt chung là đầu vào cho bước AI điền
(cơ chế auto-fill sẽ chốt sau). Sau khi con người rà soát/duyệt trong Excel,
dữ liệu được ghép vào template để xuất báo cáo PDF hàng loạt (Phase 3).
"""

import os

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import config
import structured_data
import competency_exporter


# ---------------------------------------------------------------------------
# 1. TÍNH ĐIỂM CHO TOÀN BỘ NHÂN VIÊN
# ---------------------------------------------------------------------------
def list_employee_ids(df_chi_tiet):
    """Danh sách mã nhân viên duy nhất, giữ thứ tự xuất hiện trong file Chi tiết."""
    seen, ids = set(), []
    for ma in df_chi_tiet["ma_nhan_vien"].astype(str).str.strip():
        if ma and ma not in seen:
            seen.add(ma)
            ids.append(ma)
    return ids


def build_all_structured(df_chi_tiet, report_date=None, progress_cb=None):
    """
    Tính structured data cho mọi nhân viên.
    Trả về (results, errors):
        results : list[dict structured] theo thứ tự xuất hiện.
        errors  : list[(ma_nv, thông điệp lỗi)] cho các mã tính thất bại.

    Tối ưu cho quy mô lớn (>= 500 NV): GOM NHÓM theo mã nhân viên MỘT LẦN rồi
    tính trên từng nhóm nhỏ, thay vì quét lại toàn bộ DataFrame cho mỗi người
    (tránh độ phức tạp O(n²)).

    progress_cb(done, total): gọi lại để báo tiến độ (tuỳ chọn, cho giao diện).
    """
    # Gom nhóm 1 lần theo mã nhân viên đã chuẩn hoá.
    key = df_chi_tiet["ma_nhan_vien"].astype(str).str.strip()
    groups = {ma: sub for ma, sub in df_chi_tiet.groupby(key, sort=False)}

    ids = list_employee_ids(df_chi_tiet)
    total = len(ids)
    results, errors = [], []
    for i, ma_nv in enumerate(ids, 1):
        sub = groups.get(ma_nv)
        if sub is None:
            errors.append((ma_nv, "Không gom được nhóm dữ liệu."))
        else:
            try:
                structured, _df_emp = structured_data.build_structured_data(
                    ma_nv, sub.reset_index(drop=True), report_date=report_date
                )
                results.append(structured)
            except (ValueError, KeyError) as exc:
                errors.append((ma_nv, str(exc)))
        if progress_cb and (i % 10 == 0 or i == total):
            progress_cb(i, total)
    return results, errors


# ---------------------------------------------------------------------------
# 2. SUY RA GIÁ TRỊ CÁC CỘT DỮ LIỆU GỐC / CONTEXT
# ---------------------------------------------------------------------------
def _fmt(value, decimals=config.DISPLAY_DECIMALS):
    if value is None:
        return config.NA_TEXT
    return f"{float(value):.{decimals}f}"


def _context_block(structured):
    """Khối text dễ đọc, gói toàn bộ số liệu chính của 1 nhân viên để AI tham chiếu."""
    ga = structured["group_averages"]
    lines = [
        f"TỔNG 360°: {_fmt(structured['total_360'])}/5.00 — xếp loại: {structured['badge']['label']}.",
        "Điểm theo nhóm quan hệ: " + "; ".join(
            f"{ga[rel]['label']}={_fmt(ga[rel]['score'])} "
            f"({ga[rel]['n_completed']}/{ga[rel]['n_total']})"
            for rel in structured["relationship_order"]
        ) + ".",
    ]

    subs = [s for s in structured["subcompetencies"] if s["others"] is not None]
    if subs:
        top = sorted(subs, key=lambda s: s["others"], reverse=True)[:3]
        low = sorted(subs, key=lambda s: s["others"])[:3]
        lines.append("Nhóm tiêu chí CAO nhất: " +
                     ", ".join(f"{s['label']}={_fmt(s['others'])}" for s in top) + ".")
        lines.append("Nhóm tiêu chí THẤP nhất: " +
                     ", ".join(f"{s['label']}={_fmt(s['others'])}" for s in low) + ".")

    if structured["top5"]:
        lines.append("Top hành vi: " +
                     ", ".join(f"{b['label']} ({_fmt(b['score'])})" for b in structured["top5"][:3]) + ".")
    if structured["bottom5"]:
        lines.append("Hành vi yếu: " +
                     ", ".join(f"{b['label']} ({_fmt(b['score'])})" for b in structured["bottom5"][:3]) + ".")
    if structured["gaps"]:
        g = structured["gaps"][0]
        lines.append(f"Chênh lệch lớn nhất: {g['subcomp_label']} "
                     f"(Cấp dưới {_fmt(g['a'])} vs Đồng cấp {_fmt(g['b'])}, Δ={_fmt(g['delta'])}).")
    if structured["comments"]:
        quotes = " | ".join(f'"{c}"' for c in structured["comments"][:5])
        lines.append("Ý kiến nguyên văn (ẩn danh): " + quotes)
    return "\n".join(lines)


def _source_values(structured):
    """Map key cột dữ liệu gốc -> giá trị hiển thị cho 1 nhân viên."""
    emp = structured["employee"]
    ga = structured["group_averages"]
    return {
        "ma_nv":         emp["ma_nv"],
        "ho_ten":        emp["ho_ten"],
        "chuc_danh":     emp["chuc_danh"],
        "bo_phan":       emp["bo_phan"],
        "cap_bac":       emp["cap_bac"],
        "manager":       "",            # chưa có trong dữ liệu gốc — chờ nguồn (Phase 2)
        "team":          "",            # chưa có trong dữ liệu gốc — chờ nguồn (Phase 2)
        "trang_thai":    structured["completion"]["status_text"],
        "diem_cap_tren": _fmt(ga["cap_tren"]["score"]),
        "diem_dong_cap": _fmt(ga["dong_cap"]["score"]),
        "diem_cap_duoi": _fmt(ga["cap_duoi"]["score"]),
        "tong_360":      _fmt(structured["total_360"]),
        "xep_loai":      structured["badge"]["label"],
        "du_lieu_tom_tat": _context_block(structured),
    }


# ---------------------------------------------------------------------------
# 3. SINH "FILE THỨ 4" (Excel skeleton)
# ---------------------------------------------------------------------------
# Bề rộng cột (ký tự) theo key — key không có trong map dùng giá trị mặc định.
_COL_WIDTH = {
    "ho_ten": 20, "chuc_danh": 18, "bo_phan": 16, "trang_thai": 16,
    "du_lieu_tom_tat": 60, "xep_loai": 18,
}
_AI_COL_WIDTH = 34
_DEFAULT_WIDTH = 13


def build_ai_workbook(structured_list, out_path):
    """
    Ghi file thứ 4 (Excel). Mỗi nhân viên 1 dòng: cột gốc + cột AI (trống) +
    cột rà soát. Trả về đường dẫn file đã ghi.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = config.BATCH_SHEET_NAME

    # --- Dựng danh sách cột: (key, nhãn, nhóm) ---
    columns = []
    columns += [(k, lbl, "source") for k, lbl in config.SOURCE_FIELDS]
    columns += [(k, lbl, "ai") for k, lbl, _desc in config.AI_FIELDS]
    columns += [(k, lbl, "review") for k, lbl, _vals in config.REVIEW_FIELDS]

    fills = {
        "source": PatternFill("solid", fgColor=config.XLSX_FILL_SOURCE),
        "ai":     PatternFill("solid", fgColor=config.XLSX_FILL_AI),
        "review": PatternFill("solid", fgColor=config.XLSX_FILL_REVIEW),
    }
    header_fill = PatternFill("solid", fgColor=config.XLSX_FILL_HEADER)
    header_font = Font(bold=True, color="FFFFFFFF")
    wrap_top = Alignment(wrap_text=True, vertical="top")

    # --- Hàng header ---
    for col_idx, (_key, label, _group) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = (
            _AI_COL_WIDTH if _group == "ai"
            else _COL_WIDTH.get(_key, _DEFAULT_WIDTH)
        )

    # --- Các dòng dữ liệu nhân viên ---
    review_defaults = {"trang_thai_ra_soat": config.REVIEW_STATUS_DEFAULT}
    for r, structured in enumerate(structured_list, start=2):
        src = _source_values(structured)
        for col_idx, (key, _label, group) in enumerate(columns, start=1):
            if group == "source":
                value = src.get(key, "")
            elif group == "review":
                value = review_defaults.get(key, "")
            else:  # ai — để trống cho Claude điền
                value = ""
            cell = ws.cell(row=r, column=col_idx, value=value)
            cell.fill = fills[group]
            cell.alignment = wrap_top

    # --- Dropdown cho các cột rà soát có danh sách giá trị ---
    n_rows = len(structured_list) + 1
    for col_idx, (key, _label, _group) in enumerate(columns, start=1):
        valid_values = next(
            (vals for k, _lbl, vals in config.REVIEW_FIELDS if k == key and vals), None
        )
        if valid_values:
            letter = get_column_letter(col_idx)
            dv = DataValidation(
                type="list",
                formula1='"' + ",".join(valid_values) + '"',
                allow_blank=True,
            )
            dv.add(f"{letter}2:{letter}{max(n_rows, 2)}")
            ws.add_data_validation(dv)

    # --- Cố định hàng header + cột Mã/Tên để dễ rà soát file lớn ---
    ws.freeze_panes = "C2"
    ws.row_dimensions[1].height = 30
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(n_rows, 1)}"

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    wb.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# 4. SINH PROMPT CHUNG (dùng cho toàn bộ nhân viên)
# ---------------------------------------------------------------------------
def build_common_prompt():
    """Tạo nội dung 1 prompt chung (str): vai trò + phương pháp + schema cột AI."""
    # Bảng mô tả từng cột AI cần điền.
    field_lines = "\n".join(
        f'  - "{key}" ({label}): {desc}'
        for key, label, desc in config.AI_FIELDS
    )
    # Dòng tiêu đề CSV đầu ra (ma_nv + các cột AI).
    csv_header = "ma_nv," + ",".join(key for key, _l, _d in config.AI_FIELDS)
    enum_san_sang = " / ".join(["Sẵn sàng ngay", "Sẵn sàng 1–2 năm", "Chưa sẵn sàng"])
    enum_nhan_tai = " / ".join(["Ngôi sao", "Tiềm năng cao", "Vững vàng", "Cần hỗ trợ"])

    return f"""Bạn là chuyên gia Phát triển Tổ chức (OD) & Nhân sự (HRBP). Nhiệm vụ: viết phần
VĂN BẢN ĐỊNH TÍNH cho BÁO CÁO ĐÁNH GIÁ 360° của NHIỀU nhân viên, dựa HOÀN TOÀN trên
số liệu định lượng và ý kiến nguyên văn được cung cấp cho từng người.

============================================================
NGUYÊN TẮC BẮT BUỘC
============================================================
1. TUYỆT ĐỐI KHÔNG bịa thêm số liệu, sự kiện, tên người ngoài dữ liệu đã cho.
2. Viết bằng TIẾNG VIỆT, giọng văn chuyên nghiệp, trung lập, mang tính xây dựng.
3. Ẩn danh hoàn toàn (không gắn tên/nhóm cụ thể vào từng nhận xét tiêu cực).
4. Báo cáo phục vụ PHÁT TRIỂN CÁ NHÂN, không dùng đơn lẻ cho khen thưởng/kỷ luật.
5. Nếu một nhân viên thiếu dữ liệu (ít người đánh giá), hãy nêu rõ tính tham khảo.

============================================================
PHƯƠNG PHÁP TÍNH ĐIỂM (đã có sẵn trong dữ liệu)
============================================================
- Điểm mỗi người đánh giá = 30% Phẩm chất + 70% Năng lực (trọng số theo biểu mẫu).
- Điểm theo nhóm quan hệ  = trung bình điểm người hoàn thành (Cấp trên/Đồng cấp/Cấp dưới).
- Tổng 360°               = trung bình các nhóm quan hệ có dữ liệu. Thang điểm 1.00–5.00.

============================================================
DỮ LIỆU ĐẦU VÀO (File thứ 4)
============================================================
Mỗi nhân viên là 1 dòng gồm: Mã nhân viên, Họ tên, Chức danh, Bộ phận, Cấp bậc,
KẾT QUẢ ĐÁNH GIÁ (Tổng 360°), điểm TỪNG HÀNH VI theo 4 khối (TỔNG / CẤP TRÊN /
ĐỒNG NGHIỆP-ĐỐI TÁC / CẤP DƯỚI), và cột "Ý kiến đánh giá (từng người, ẩn danh)"
chứa nguyên văn nhận xét của người đánh giá. HÃY DÙNG ĐÚNG các số liệu & ý kiến
này, KHÔNG bịa thêm.

============================================================
CÁC TRƯỜNG CẦN SINH cho MỖI nhân viên
============================================================
{field_lines}

============================================================
ĐỊNH DẠNG ĐẦU RA — CSV (UTF-8)
============================================================
Trả về DUY NHẤT một bảng CSV (UTF-8), KHÔNG kèm bất kỳ chữ nào ngoài CSV, KHÔNG bọc
trong ```. Quy tắc:
1. DÒNG ĐẦU là tiêu đề, ĐÚNG thứ tự cột sau:
{csv_header}
2. Mỗi nhân viên 1 dòng; cột đầu "ma_nv" để ghép kết quả về đúng người.
3. Phân tách bằng dấu phẩy. Nếu một ô chứa dấu phẩy, xuống dòng hoặc dấu ngoặc kép
   thì BỌC ô đó trong ngoặc kép "...", và nhân đôi ngoặc kép bên trong ("").
4. Các trường danh sách (điểm mạnh, nên bắt đầu, ...) ghi mỗi ý trên 1 DÒNG MỚI
   ngay TRONG ô (ô đó phải được bọc trong ngoặc kép).
5. "muc_do_san_sang_thang_tien" PHẢI thuộc: {enum_san_sang}.
6. "nhom_nhan_tai" PHẢI thuộc: {enum_nhan_tai}.

File CSV này dùng để TẢI XUỐNG rồi NẠP LẠI vào hệ thống (khớp theo ma_nv) ở bước sau.
"""


def write_outputs(structured_list, out_dir, wide=True):
    """
    Ghi File thứ 4 + prompt chung ra out_dir. Trả về dict đường dẫn.

    wide=True (mặc định): File thứ 4 theo ĐỊNH DẠNG WIDE bám mẫu "Tổng hợp tiêu
    chí" (24 hành vi × 4 khối rater + Khuyến nghị + cột AI + cột rà soát).
    wide=False: bản gọn (1 dòng/người, cột AI cạnh cột điểm tổng).
    """
    os.makedirs(out_dir, exist_ok=True)
    prompt_path = os.path.join(out_dir, config.OUT_COMMON_PROMPT)
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(build_common_prompt())

    if wide:
        xlsx_path = os.path.join(out_dir, config.OUT_BATCH_XLSX_WIDE)
        competency_exporter.build_competency_workbook(structured_list, xlsx_path)
    else:
        xlsx_path = os.path.join(out_dir, config.OUT_BATCH_XLSX)
        build_ai_workbook(structured_list, xlsx_path)

    return {"batch_xlsx": xlsx_path, "common_prompt": prompt_path}
