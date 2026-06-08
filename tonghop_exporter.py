# -*- coding: utf-8 -*-
"""
tonghop_exporter.py
===================
Xuất file `Tong-hop-raw_<MaNV>.csv` cho 1 nhân viên, GIỮ ĐÚNG format của file
`360 data raw(Tong-hop-raw).csv` gốc (cùng tập cột, cùng thứ tự, kể cả các cột
phụ như AD / CHECK DS Gốc / cột rỗng).

Cách làm để đảm bảo "giống hệt format":
  1. Lấy hàng gốc của nhân viên trong file Tổng hợp (nếu có) làm khung.
  2. Ghi đè 4 cột điểm + cột Trạng thái + cột Ý KIẾN CHUNG bằng số liệu TÍNH LẠI.
  3. Nếu file gốc không có hàng nào cho nhân viên -> tạo hàng mới theo đúng header,
     điền metadata từ file Chi tiết, các cột còn lại để trống.

LƯU Ý KỸ THUẬT: file Tổng hợp có NHIỀU CỘT TRÙNG TÊN (kể cả nhiều cột rỗng "").
=> Toàn bộ thao tác làm việc THEO VỊ TRÍ (index), không dùng dict-theo-tên, để
   tránh việc các cột trùng tên bị gộp/ghi đè lẫn nhau.
"""

import os
import pandas as pd

import config
from score_calculator import strip_accents


# ---------------------------------------------------------------------------
# Tiện ích tìm CHỈ SỐ cột theo từ khoá (chịu được sai khác hoa/thường, dấu, khoảng trắng)
# ---------------------------------------------------------------------------
def find_col_index(columns, keyword):
    """Trả về chỉ số cột đầu tiên có chứa `keyword` (so khớp đã bỏ dấu), hoặc None."""
    needle = strip_accents(keyword)
    for idx, col in enumerate(columns):
        if needle in strip_accents(col):
            return idx
    return None


def fmt_score(value):
    """Định dạng điểm: None -> 'N/A'; số -> chuỗi gọn (bỏ số 0 thừa)."""
    if value is None:
        return config.NA_TEXT
    s = f"{float(value):.8f}".rstrip("0").rstrip(".")
    return s if s else "0"


# ---------------------------------------------------------------------------
# Xuất file Tổng hợp cho 1 nhân viên
# ---------------------------------------------------------------------------
def export_tong_hop(
    ma_nv,
    df_tong_hop,
    columns,
    employee_meta,
    group_averages,
    total_360,
    status_text,
    opinion_text,
    out_dir,
):
    """
    Ghi file Tong-hop-raw_<MaNV>.csv. Trả về đường dẫn file.
    """
    n = len(columns)
    idx_emp = find_col_index(columns, config.TONGHOP_EMP_COL_KEYWORD)

    # 1. Lấy hàng gốc của nhân viên (THEO VỊ TRÍ) để làm khung; nếu không có -> rỗng.
    values = None
    if idx_emp is not None and not df_tong_hop.empty:
        emp_series = df_tong_hop.iloc[:, idx_emp].astype(str).str.strip()
        matched = df_tong_hop[emp_series == str(ma_nv).strip()]
        if len(matched):
            values = list(matched.iloc[0].values)

    if values is None:
        # Tạo khung rỗng + điền metadata cơ bản theo vị trí.
        values = ["" for _ in range(n)]
        if idx_emp is not None:
            values[idx_emp] = str(ma_nv).strip()
        _fill_metadata_by_index(values, columns, employee_meta)

    # Đảm bảo độ dài đúng bằng số cột.
    values = (values + [""] * n)[:n]

    # 2. Ghi đè các cột điểm + trạng thái + ý kiến (theo vị trí).
    for rel_key in config.RELATIONSHIP_ORDER:
        idx = find_col_index(columns, config.TONGHOP_SCORE_COL_KEYWORDS[rel_key])
        if idx is not None:
            values[idx] = fmt_score(group_averages[rel_key]["score"])

    idx_total = find_col_index(columns, config.TONGHOP_TOTAL_COL_KEYWORD)
    if idx_total is not None:
        values[idx_total] = fmt_score(total_360)

    idx_status = find_col_index(columns, config.TONGHOP_STATUS_COL_KEYWORD)
    if idx_status is not None:
        values[idx_status] = status_text

    idx_opinion = find_col_index(columns, config.TONGHOP_OPINION_COL_KEYWORD)
    if idx_opinion is not None and opinion_text:
        values[idx_opinion] = opinion_text

    # 3. Xuất 1 hàng theo đúng thứ tự & tên cột gốc (cho phép trùng tên).
    out_df = pd.DataFrame([values], columns=columns)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, config.OUT_TONGHOP.format(ma_nv=ma_nv))
    out_df.to_csv(out_path, index=False, encoding=config.ENCODING)
    return out_path


def _fill_metadata_by_index(values, columns, meta):
    """Điền metadata cơ bản (theo vị trí) khi file gốc không có nhân viên."""
    mapping = {
        "họ và tên": meta.get("ho_ten", ""),
        "chức danh": meta.get("chuc_danh", ""),
        "bộ phận": meta.get("bo_phan", ""),
        "cấp bậc": meta.get("cap_bac", ""),
        "mã biểu mẫu": meta.get("ma_bieu_mau", ""),
    }
    for kw, val in mapping.items():
        idx = find_col_index(columns, kw)
        if idx is not None and not values[idx]:
            values[idx] = val
