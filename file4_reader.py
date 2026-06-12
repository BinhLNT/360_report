# -*- coding: utf-8 -*-
"""
file4_reader.py
===============
Đọc NGƯỢC "File thứ 4" (Excel) mà người dùng đã rà soát/điền — lấy nội dung AI
+ Khuyến nghị + trạng thái rà soát cho từng nhân viên.

Dùng CHUNG cấu trúc cột với competency_exporter (_build_column_spec) để luôn
khớp vị trí cột, không hard-code.
"""

import openpyxl

import config
import competency_exporter


def _column_map():
    """Trả về dict {col_index_0based: (kind, key)} cho các cột cần đọc."""
    spec = competency_exporter._build_column_spec()
    out = {}
    for i, col in enumerate(spec):
        kind = col["kind"]
        if kind in ("identity", "ai", "review"):
            out[i] = (kind, col["key"])
        elif kind == "ketqua":
            out[i] = ("ketqua", "ket_qua")
        elif kind == "khuyennghi":
            out[i] = ("khuyennghi", "khuyen_nghi")
    return out


def read_file4(path, first_data_row=4):
    """
    Đọc File thứ 4. Trả về dict {ma_nv: record}, mỗi record:
        {
          "ma_nv", "identity": {ma_nv, ho_ten, chuc_danh, ban_chuoi_khoi, cap_bac, trang_thai},
          "ai": {<16 key AI>: text}, "khuyen_nghi": text,
          "review": {trang_thai_ra_soat, nguoi_ra_soat, ngay_ra_soat, ghi_chu_ra_soat},
        }
    Ô trống -> chuỗi rỗng.
    """
    colmap = _column_map()
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    records = {}
    for row in ws.iter_rows(min_row=first_data_row, values_only=True):
        if row is None:
            continue
        rec = {"identity": {}, "ai": {}, "review": {}, "khuyen_nghi": ""}
        for ci, (kind, key) in colmap.items():
            val = row[ci] if ci < len(row) else None
            val = "" if val is None else str(val).strip()
            if kind == "identity":
                rec["identity"][key] = val
            elif kind == "ai":
                rec["ai"][key] = val
            elif kind == "review":
                rec["review"][key] = val
            elif kind == "khuyennghi":
                rec["khuyen_nghi"] = val
        ma = rec["identity"].get("ma_nv", "").strip()
        if not ma:
            continue  # bỏ dòng trống
        rec["ma_nv"] = ma
        records[ma] = rec
    wb.close()
    return records


def has_ai_content(record):
    """True nếu record có ít nhất 1 trường AI (hoặc Khuyến nghị) đã được điền."""
    if record.get("khuyen_nghi", "").strip():
        return True
    return any(v.strip() for v in record.get("ai", {}).values())


def is_approved(record):
    """True nếu trạng thái rà soát = 'Đã duyệt'."""
    return record.get("review", {}).get("trang_thai_ra_soat", "").strip() == config.REVIEW_STATUS_APPROVED
