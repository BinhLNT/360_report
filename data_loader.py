# -*- coding: utf-8 -*-
"""
data_loader.py
==============
Chịu trách nhiệm ĐỌC 2 file CSV đầu vào và chuẩn hoá về DataFrame sạch.

Thách thức thực tế của dữ liệu xuất từ hệ thống đánh giá:
  * File "Chi tiết" có 1 dòng "banner" ở trên cùng (gộp ô) trước dòng header thật.
  * Header có các cột TRÙNG TÊN ("Mã biểu mẫu", "Ý KIẾN") -> không thể tin cậy theo tên.
  * Có thể có BOM (utf-8-sig).
=> Giải pháp: tự dò dòng header, rồi LẤY CỘT THEO VỊ TRÍ (index) thay vì theo tên.
"""

import csv
import pandas as pd

import config


# ---------------------------------------------------------------------------
# Tiện ích chung
# ---------------------------------------------------------------------------
def _read_raw_lines(path, max_lines=40):
    """Đọc một số dòng đầu của file (text) để dò vị trí dòng header."""
    with open(path, "r", encoding=config.ENCODING, newline="") as f:
        lines = []
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            lines.append(line)
    return lines


def _find_header_row(path, must_contain):
    """
    Tìm chỉ số dòng (0-based) chứa header thật bằng cách kiểm tra dòng nào
    chứa ĐỦ tất cả các từ khoá trong `must_contain` (so khớp không phân biệt
    hoa/thường). Nếu không tìm thấy -> mặc định 0.
    """
    needles = [s.lower() for s in must_contain]
    for idx, line in enumerate(_read_raw_lines(path)):
        low = line.lower()
        if all(n in low for n in needles):
            return idx
    return 0


def _read_header_names(path, header_row):
    """Đọc đúng tên cột (kể cả cột rỗng) tại dòng header_row, giữ nguyên bản gốc."""
    with open(path, "r", encoding=config.ENCODING, newline="") as f:
        reader = csv.reader(f)
        for idx, row in enumerate(reader):
            if idx == header_row:
                return row
    return []


# ---------------------------------------------------------------------------
# 1. ĐỌC FILE CHI TIẾT (theo từng tiêu chí, từng người đánh giá)
# ---------------------------------------------------------------------------
# Vị trí cột chuẩn của file Chi tiết (0-based) sau dòng header.
_CHI_TIET_COL_INDEX = {
    "ma_ad": 0,           # Mã người đánh giá
    "moi_quan_he": 1,     # Mối quan hệ với người được đánh giá
    "ma_bm_dg": 2,        # Mã biểu mẫu (của người đánh giá)
    "trang_thai": 3,      # Trạng thái (Đã đánh giá / Chờ đánh giá)
    "tong_diem": 4,       # Tổng điểm (hệ thống tính sẵn, dùng để đối chiếu)
    "y_kien_chung": 5,    # Ý kiến chung của người đánh giá
    "ma_nhan_vien": 6,    # Mã CBLĐ được đánh giá
    "ho_ten": 7,
    "chuc_danh": 8,
    "bo_phan": 9,
    "cap_bac": 10,
    "ma_bieu_mau": 11,    # Mã biểu mẫu của CBLĐ
    "ten_nhom": 12,       # Tên nhóm mục tiêu (PHẨM CHẤT / NĂNG LỰC)
    "trong_so": 13,       # Trọng số nhóm mục tiêu (30 / 70)
    "ten_muc_tieu": 14,   # Tên mục tiêu (tiêu chí cụ thể)
    "he_so": 15,          # Hệ Số ÁP DỤNG
    "diem": 16,           # ĐIỂM ĐÁNH GIÁ
}


def load_chi_tiet(path):
    """
    Đọc file Chi tiết -> DataFrame với các cột đã đổi tên chuẩn (theo vị trí).
    Trả về cột số (tong_diem, trong_so, he_so, diem) ở dạng float (NaN nếu lỗi).
    """
    header_row = _find_header_row(path, must_contain=["Mối quan hệ", "ĐIỂM ĐÁNH GIÁ"])

    # Đọc toàn bộ là string để không mất dữ liệu; tự ép kiểu sau.
    raw = pd.read_csv(
        path,
        encoding=config.ENCODING,
        skiprows=header_row,
        header=0,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )

    # Lấy cột theo VỊ TRÍ (an toàn với cột trùng tên).
    data = {}
    n_cols = raw.shape[1]
    for name, idx in _CHI_TIET_COL_INDEX.items():
        if idx < n_cols:
            data[name] = raw.iloc[:, idx].astype(str).str.strip()
        else:
            data[name] = ""
    df = pd.DataFrame(data)

    # Ép kiểu số cho các cột tính toán.
    for col in ["tong_diem", "trong_so", "he_so", "diem"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Loại các dòng rác (không có tên mục tiêu hoặc không có mã nhân viên).
    df = df[(df["ten_muc_tieu"] != "") & (df["ma_nhan_vien"] != "")].reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# 2. ĐỌC FILE TỔNG HỢP (metadata + ý kiến chung tổng hợp)
# ---------------------------------------------------------------------------
def load_tong_hop(path):
    """
    Đọc file Tổng hợp -> (DataFrame, header_goc).
    GIỮ NGUYÊN tên cột gốc (kể cả cột rỗng) để khi xuất file output bám đúng format.
    Trả về DataFrame (mọi cột là string) và list tên cột gốc.
    """
    header_row = _find_header_row(
        path, must_contain=["Mã nhân viên", "TỔNG ĐIỂM ĐÁNH GIÁ 360"]
    )
    header_names = _read_header_names(path, header_row)

    df = pd.read_csv(
        path,
        encoding=config.ENCODING,
        skiprows=header_row,
        header=0,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )

    # pandas tự đặt tên "Unnamed: N" cho cột rỗng -> khôi phục lại tên gốc
    # (thường là chuỗi rỗng) để xuất file giữ đúng format mẫu.
    if header_names and len(header_names) == df.shape[1]:
        df.columns = header_names

    return df, list(df.columns)
