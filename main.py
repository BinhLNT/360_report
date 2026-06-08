# -*- coding: utf-8 -*-
"""
main.py
=======
Điểm vào (entry point) của hệ thống tạo báo cáo 360°.

LUỒNG XỬ LÝ:
  1. Đọc 2 file CSV raw (Chi tiết + Tổng hợp).
  2. Tính điểm trung bình theo 3 nhóm quan hệ + Tổng 360° (score_calculator).
  3. Xuất file Tong-hop-raw_<MaNV>.csv (giữ đúng format file gốc).
  4. Dựng structured data + lưu structured_<MaNV>.json.
  5. Sinh prompt_<MaNV>.txt cho Claude.
  6. Lấy nội dung định tính (từ Claude nếu có, ngược lại sinh mặc định).
  7. Vẽ biểu đồ (matplotlib -> base64) + render HTML/PDF (Jinja2 + WeasyPrint).

CÁCH DÙNG:
  python main.py --ma-nv 015
  python main.py --ma-nv 015 --data-dir data --out-dir output
  python main.py --ma-nv 015 --content output/claude_content_015.json

KHÔNG gọi bất kỳ AI API nào.
"""

import argparse
import json
import os
import sys

import config
import data_loader
import structured_data
import tonghop_exporter
import prompt_generator
import content_provider
import chart_generator
import report_renderer


def force_utf8_console():
    """Ép stdout/stderr về UTF-8 để in được tiếng Việt trên console Windows
    (mặc định Windows dùng codepage cp125x không encode được ký tự dựng sẵn)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Tạo báo cáo đánh giá 360° từ 2 file CSV raw."
    )
    parser.add_argument("--ma-nv", required=True,
                        help="Mã nhân viên cần tạo báo cáo (ví dụ: 015).")
    parser.add_argument("--data-dir", default="data",
                        help="Thư mục chứa 2 file CSV raw (mặc định: data).")
    parser.add_argument("--out-dir", default="output",
                        help="Thư mục xuất kết quả (mặc định: output).")
    parser.add_argument("--content", default=None,
                        help="Đường dẫn file JSON nội dung từ Claude "
                             "(mặc định: <out-dir>/claude_content_<MaNV>.json nếu tồn tại).")
    parser.add_argument("--report-date", default=None,
                        help="Ngày báo cáo dd/mm/yyyy (mặc định: hôm nay).")
    return parser.parse_args(argv)


def prepare(ma_nv, data_dir="data", out_dir="output", report_date=None):
    """
    GIAI ĐOẠN 1 — CHUẨN BỊ.
    Đọc 2 file CSV raw -> tính điểm -> xuất `Tong-hop-raw_<MaNV>.csv`,
    `structured_<MaNV>.json` và `prompt_<MaNV>.txt`. KHÔNG render báo cáo.

    Đây là đầu ra để người dùng mang prompt sang Claude. Trả về dict gồm cả
    `structured` (để tái dùng ngay trong cùng tiến trình) và đường dẫn các file.
    """
    force_utf8_console()
    # --- Đường dẫn 2 file input ---
    chi_tiet_path = os.path.join(data_dir, config.INPUT_CHI_TIET)
    tong_hop_path = os.path.join(data_dir, config.INPUT_TONG_HOP)
    for p in (chi_tiet_path, tong_hop_path):
        if not os.path.isfile(p):
            raise FileNotFoundError(f"Không tìm thấy file input: {p}")

    print(f"[1/5] Đọc dữ liệu raw từ '{data_dir}' ...")
    df_chi_tiet = data_loader.load_chi_tiet(chi_tiet_path)
    df_tong_hop, th_columns = data_loader.load_tong_hop(tong_hop_path)

    print(f"[2/5] Tính điểm 360° cho nhân viên {ma_nv} ...")
    structured, _df_emp = structured_data.build_structured_data(
        ma_nv, df_chi_tiet, report_date=report_date
    )
    _print_score_summary(structured)

    print("[3/5] Xuất file Tổng hợp (Tong-hop-raw_<MaNV>.csv) ...")
    tonghop_path = tonghop_exporter.export_tong_hop(
        ma_nv=ma_nv,
        df_tong_hop=df_tong_hop,
        columns=th_columns,
        employee_meta=structured["employee"],
        group_averages={k: {"score": v["score"]} for k, v in structured["group_averages"].items()},
        total_360=structured["total_360"],
        status_text=structured["completion"]["status_text"],
        opinion_text=structured["opinion_text"],
        out_dir=out_dir,
    )

    print("[4/5] Lưu structured data (structured_<MaNV>.json) ...")
    structured_path = os.path.join(out_dir, config.OUT_STRUCTURED.format(ma_nv=ma_nv))
    os.makedirs(out_dir, exist_ok=True)
    with open(structured_path, "w", encoding="utf-8") as f:
        json.dump(structured, f, ensure_ascii=False, indent=2)

    print("[5/5] Sinh prompt cho Claude (prompt_<MaNV>.txt) ...")
    prompt_path = prompt_generator.write_prompt(structured, out_dir, ma_nv)

    return {
        "structured": structured,
        "tong_hop_csv": tonghop_path,
        "structured_json": structured_path,
        "prompt_txt": prompt_path,
    }


def finalize(ma_nv, out_dir="output", content_path=None, structured=None, force_default=False):
    """
    GIAI ĐOẠN 2 — HOÀN THIỆN.
    Ghép phần văn bản định tính (từ Claude nếu có, ngược lại sinh mặc định theo
    luật) vào template -> vẽ biểu đồ -> render `BAOCAO_<MaNV>.html` (+ PDF).

    Nếu không truyền sẵn `structured`, hàm đọc lại từ `structured_<MaNV>.json`
    (đã tạo ở giai đoạn chuẩn bị) — cho phép người dùng quay lại sau khi đã có
    kết quả Claude mà không phải tính lại từ đầu.
    """
    force_utf8_console()
    if structured is None:
        structured_path = os.path.join(out_dir, config.OUT_STRUCTURED.format(ma_nv=ma_nv))
        if not os.path.isfile(structured_path):
            raise FileNotFoundError(
                f"Chưa có '{structured_path}'. Hãy chạy giai đoạn CHUẨN BỊ (prepare) trước."
            )
        with open(structured_path, encoding="utf-8") as f:
            structured = json.load(f)

    print("[1/2] Lấy nội dung định tính ...")
    if force_default:
        # Ép dùng nội dung mặc định, BỎ QUA file Claude cũ (nếu có).
        content, source = content_provider.build_default_content(structured), "default"
    else:
        if content_path is None:
            default_content = os.path.join(out_dir, config.OUT_CONTENT.format(ma_nv=ma_nv))
            content_path = default_content if os.path.isfile(default_content) else None
        content, source = content_provider.get_content(structured, content_path)
    print(f"      -> Nguồn nội dung: {'Claude (JSON)' if source == 'claude' else 'Mặc định (rule-based)'}")

    print("[2/2] Vẽ biểu đồ + render báo cáo (HTML/PDF) ...")
    charts = chart_generator.build_all_charts(structured)
    html_path, pdf_path = report_renderer.render_report(
        structured, content, source, charts, out_dir, ma_nv
    )
    return {"html": html_path, "pdf": pdf_path, "content_source": source}


def run(ma_nv, data_dir="data", out_dir="output", content_path=None, report_date=None):
    """Chạy GỘP cả 2 giai đoạn cho 1 mã nhân viên (tiện cho CLI một phát).
    Trả về dict các đường dẫn output."""
    prep = prepare(ma_nv, data_dir=data_dir, out_dir=out_dir, report_date=report_date)
    fin = finalize(ma_nv, out_dir=out_dir, content_path=content_path,
                   structured=prep["structured"])
    outputs = {
        "tong_hop_csv": prep["tong_hop_csv"],
        "structured_json": prep["structured_json"],
        "prompt_txt": prep["prompt_txt"],
        "html": fin["html"],
        "pdf": fin["pdf"],
    }
    _print_outputs(outputs)
    return outputs


def _print_score_summary(structured):
    """In nhanh điểm số ra console để người dùng kiểm tra."""
    def f(v):
        return config.NA_TEXT if v is None else f"{v:.4f}"
    ga = structured["group_averages"]
    print(f"      - Cấp trên : {f(ga['cap_tren']['score'])}  "
          f"({ga['cap_tren']['n_completed']}/{ga['cap_tren']['n_total']})")
    print(f"      - Đồng cấp : {f(ga['dong_cap']['score'])}  "
          f"({ga['dong_cap']['n_completed']}/{ga['dong_cap']['n_total']})")
    print(f"      - Cấp dưới : {f(ga['cap_duoi']['score'])}  "
          f"({ga['cap_duoi']['n_completed']}/{ga['cap_duoi']['n_total']})")
    print(f"      - TỔNG 360°: {f(structured['total_360'])}  "
          f"[{structured['badge']['label']}]")


def _print_outputs(outputs):
    print("\n===== HOÀN TẤT =====")
    for key, path in outputs.items():
        status = path if path else "(bỏ qua / lỗi)"
        print(f"  {key:>16}: {status}")


def main(argv=None):
    args = parse_args(argv)
    try:
        run(
            ma_nv=str(args.ma_nv).strip(),
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            content_path=args.content,
            report_date=args.report_date,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[LỖI] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
