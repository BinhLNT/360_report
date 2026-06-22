# -*- coding: utf-8 -*-
"""
batch_builder.py
================
CHẾ ĐỘ BATCH (>= 500 nhân viên).

Module này:

  1. Tính điểm 360° cho TOÀN BỘ nhân viên trong file Chi tiết (tái dùng
     score_calculator + structured_data).
  2. Sinh "FILE THỨ 4" dạng Excel (.xlsx): mỗi nhân viên 1 dòng gồm
        [cột dữ liệu gốc/context]  +  [cột AI (để trống)]  +  [cột rà soát].

KHÔNG gọi AI API ở đây. Cột AI được `ai_engine` tự động điền (auto-fill). Sau khi
con người rà soát/duyệt, dữ liệu được ghép vào template để xuất báo cáo PDF (Phase 3).
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


def write_outputs(structured_list, out_dir):
    """
    Ghi "File thứ 4" (Excel, định dạng WIDE bám mẫu "Tổng hợp tiêu chí": 24 hành vi
    × 4 khối rater + Khuyến nghị + cột AI + cột rà soát) ra out_dir.

    Nội dung cột AI do ai_engine tự động điền (xem ai_engine.autofill_file4).
    Trả về dict {"batch_xlsx": <đường dẫn>}.
    """
    os.makedirs(out_dir, exist_ok=True)
    xlsx_path = os.path.join(out_dir, config.OUT_BATCH_XLSX_WIDE)
    competency_exporter.build_competency_workbook(structured_list, xlsx_path)
    return {"batch_xlsx": xlsx_path}
