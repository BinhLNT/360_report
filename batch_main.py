# -*- coding: utf-8 -*-
"""
batch_main.py
=============
Điểm vào CLI cho CHẾ ĐỘ BATCH (>= 500 nhân viên).

LUỒNG:
  1. Đọc file Chi tiết (toàn bộ nhân viên).
  2. Tính điểm 360° cho TẤT CẢ nhân viên.
  3. Sinh "FILE THỨ 4" (Excel: data gốc + cột AI trống + cột rà soát) và
     PROMPT CHUNG (prompt_chung.txt).

CÁCH DÙNG:
  python batch_main.py
  python batch_main.py --data-dir data --out-dir output --report-date 09/06/2026

KHÔNG gọi AI API. Đầu ra dùng cho bước AI điền + con người rà soát.
"""

import argparse
import os
import sys

import config
import data_loader
import batch_builder
import utils


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Sinh File thứ 4 (Excel) + prompt chung cho toàn bộ nhân viên."
    )
    p.add_argument("--data-dir", default="data",
                   help="Thư mục chứa file Chi tiết (mặc định: data).")
    p.add_argument("--out-dir", default="output",
                   help="Thư mục xuất kết quả (mặc định: output).")
    p.add_argument("--report-date", default=None,
                   help="Ngày báo cáo dd/mm/yyyy (mặc định: hôm nay).")
    return p.parse_args(argv)


def run(data_dir="data", out_dir="output", report_date=None):
    utils.force_utf8_console()

    chi_tiet_path = os.path.join(data_dir, config.INPUT_CHI_TIET)
    if not os.path.isfile(chi_tiet_path):
        raise FileNotFoundError(f"Không tìm thấy file Chi tiết: {chi_tiet_path}")

    print(f"[1/3] Đọc file Chi tiết: {chi_tiet_path}")
    df_chi_tiet = data_loader.load_chi_tiet(chi_tiet_path)
    ids = batch_builder.list_employee_ids(df_chi_tiet)
    print(f"      -> {len(ids)} nhân viên: {', '.join(ids[:10])}{' ...' if len(ids) > 10 else ''}")

    print("[2/3] Tính điểm 360° cho toàn bộ nhân viên ...")
    results, errors = batch_builder.build_all_structured(df_chi_tiet, report_date=report_date)
    print(f"      -> Thành công: {len(results)} | Lỗi: {len(errors)}")
    for ma_nv, msg in errors:
        print(f"        ! {ma_nv}: {msg}")

    if not results:
        raise ValueError("Không tính được nhân viên nào — kiểm tra lại file Chi tiết.")

    # Cảnh báo nếu ma trận hành vi sẽ TRỐNG: có điểm nhóm nhưng không phân loại
    # được tiêu chí (thường do cột 'Tên mục tiêu' không khớp 24 hành vi chuẩn).
    blank = [s["employee"]["ma_nv"] for s in results
             if not s.get("behaviors") and s.get("total_360") is not None]
    if blank:
        print(f"      ! CẢNH BÁO: {len(blank)}/{len(results)} nhân viên có điểm tổng nhưng "
              f"KHÔNG phân loại được tiêu chí -> ma trận 24 hành vi sẽ TRỐNG.")
        print(f"        (vd: {', '.join(blank[:10])}{' ...' if len(blank) > 10 else ''}) "
              f"Kiểm tra cột 'Tên mục tiêu' trong file Chi tiết có khớp 24 hành vi chuẩn không.")

    print("[3/3] Sinh File thứ 4 (Excel) + prompt chung ...")
    out = batch_builder.write_outputs(results, out_dir)

    print("\n===== HOÀN TẤT =====")
    print(f"  File thứ 4 (Excel): {out['batch_xlsx']}")
    print(f"  Prompt chung      : {out['common_prompt']}")
    print(f"  Số dòng nhân viên : {len(results)}")
    return out


def main(argv=None):
    args = parse_args(argv)
    try:
        run(data_dir=args.data_dir, out_dir=args.out_dir, report_date=args.report_date)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[LỖI] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
