# -*- coding: utf-8 -*-
"""
prompt_generator.py
==================
Sinh file `prompt_<MaNV>.txt` – một prompt RẤT CHI TIẾT để người dùng đưa cho
Claude tạo phần VĂN BẢN định tính của báo cáo (Executive Summary, Start/Stop/
Continue, Phân tích chênh lệch, Khuyến nghị phát triển).

QUAN TRỌNG: file này chỉ TẠO RA văn bản prompt. Hệ thống KHÔNG gọi bất kỳ AI
API nào. Người dùng tự đưa prompt cho Claude, rồi dán JSON kết quả vào file
`claude_content_<MaNV>.json` để bước render đọc lên.
"""

import os

import config


def _fmt(value, decimals=config.DISPLAY_DECIMALS):
    """Định dạng số an toàn (None -> 'N/A')."""
    if value is None:
        return config.NA_TEXT
    return f"{float(value):.{decimals}f}"


def _block_scores(structured):
    """Khối text: điểm theo nhóm quan hệ + tổng 360."""
    lines = []
    for rel in structured["relationship_order"]:
        g = structured["group_averages"][rel]
        lines.append(
            f"  - {g['label']}: {_fmt(g['score'])} "
            f"({g['n_completed']}/{g['n_total']} người hoàn thành)"
        )
    lines.append(f"  - TỔNG ĐIỂM 360°: {_fmt(structured['total_360'])} / 5.00 "
                 f"(xếp loại: {structured['badge']['label']})")
    return "\n".join(lines)


def _block_subcomp(structured):
    """Khối text: bảng 10 nhóm tiêu chí con."""
    lines = []
    for s in structured["subcompetencies"]:
        lines.append(
            f"  - {s['label']}: Tổng={_fmt(s['others'])}, "
            f"Cấp trên={_fmt(s.get('cap_tren'))}, "
            f"Đồng cấp={_fmt(s.get('dong_cap'))}, "
            f"Cấp dưới={_fmt(s.get('cap_duoi'))}"
        )
    return "\n".join(lines)


def _block_top_bottom(structured):
    """Khối text: top/bottom hành vi."""
    top = "\n".join(f"  - {b['label']}: {_fmt(b['score'])}" for b in structured["top5"])
    bottom = "\n".join(f"  - {b['label']}: {_fmt(b['score'])}" for b in structured["bottom5"])
    return top, bottom


def _block_gaps(structured):
    """Khối text: chênh lệch Cấp dưới vs Đồng cấp."""
    lines = []
    for g in structured["gaps"]:
        lines.append(
            f"  - {g['subcomp_label']}: Cấp dưới={_fmt(g['a'])}, "
            f"Đồng cấp={_fmt(g['b'])}, Δ={_fmt(g['delta'])}"
        )
    return "\n".join(lines) if lines else "  (không đủ 2 nhóm rater để so sánh)"


def _block_comments(structured):
    """Khối text: trích nguyên văn ý kiến chung (ẩn danh)."""
    if not structured["comments"]:
        return "  (không có ý kiến định tính)"
    return "\n".join(f'  {i+1}. "{c}"' for i, c in enumerate(structured["comments"]))


JSON_SCHEMA = """{
  "executive_summary": "<1-2 đoạn HTML ngắn tóm tắt tổng quan kết quả, nêu mức điểm, điểm mạnh nổi bật và 1-2 lưu ý>",
  "start_stop_continue": {
    "continue": ["<hành vi nên TIẾP TỤC phát huy>", "..."],
    "start": ["<hành vi nên BẮT ĐẦU làm>", "..."],
    "stop": ["<hành vi nên CÂN NHẮC DỪNG; nếu không có, ghi 1 câu trung tính>"]
  },
  "analysis": "<1 đoạn phân tích chênh lệch giữa các nhóm rater & ý nghĩa coaching>",
  "development_tips": {
    "<Tên nhóm tiêu chí điểm thấp>": ["<gợi ý phát triển 1>", "<gợi ý 2>"]
  },
  "ai_note": "<1 câu lưu ý rằng nội dung do AI tổng hợp, cần OD/HRBP rà soát>"
}"""


def build_prompt(structured):
    """Tạo nội dung prompt (str) từ structured data."""
    emp = structured["employee"]
    dq = structured["data_quality"]
    top, bottom = _block_top_bottom(structured)

    prompt = f"""Bạn là chuyên gia Phát triển Tổ chức (OD) & Nhân sự (HRBP). Hãy viết phần VĂN BẢN
định tính cho một BÁO CÁO ĐÁNH GIÁ 360° dựa HOÀN TOÀN trên dữ liệu định lượng và các
ý kiến nguyên văn được cung cấp bên dưới. TUYỆT ĐỐI KHÔNG bịa thêm số liệu hay sự kiện
ngoài dữ liệu đã cho.

============================================================
THÔNG TIN NGƯỜI ĐƯỢC ĐÁNH GIÁ
============================================================
- Mã nhân viên : {emp['ma_nv']}
- Họ và tên    : {emp['ho_ten']}
- Chức danh    : {emp['chuc_danh']}
- Bộ phận      : {emp['bo_phan']}
- Ngày báo cáo : {structured['report_date']}
- Tiến độ      : {structured['completion']['status_text']}

============================================================
PHƯƠNG PHÁP TÍNH ĐIỂM
============================================================
- Điểm mỗi người đánh giá = 30% Phẩm chất + 70% Năng lực (trọng số theo biểu mẫu).
- Điểm theo nhóm quan hệ  = trung bình cộng điểm của người hoàn thành trong nhóm.
- Tổng 360°               = trung bình cộng các nhóm quan hệ có dữ liệu.
- Báo cáo phục vụ PHÁT TRIỂN CÁ NHÂN, không dùng đơn lẻ cho khen thưởng/kỷ luật.

============================================================
ĐIỂM THEO NHÓM QUAN HỆ
============================================================
{_block_scores(structured)}

============================================================
ĐIỂM THEO 10 NHÓM TIÊU CHÍ CON
============================================================
{_block_subcomp(structured)}

============================================================
TOP 5 HÀNH VI ĐIỂM CAO NHẤT
============================================================
{top}

============================================================
TOP 5 HÀNH VI ĐIỂM THẤP NHẤT (ưu tiên phát triển)
============================================================
{bottom}

============================================================
CHÊNH LỆCH GÓC NHÌN (Cấp dưới − Đồng cấp)
============================================================
{_block_gaps(structured)}

============================================================
Ý KIẾN ĐỊNH TÍNH (NGUYÊN VĂN, ĐÃ ẨN DANH)
============================================================
{_block_comments(structured)}

============================================================
LƯU Ý ĐỘ TIN CẬY DỮ LIỆU
============================================================
{dq['warning_html'].replace('<b>', '').replace('</b>', '')}

============================================================
YÊU CẦU ĐẦU RA
============================================================
1. Viết bằng TIẾNG VIỆT, giọng văn chuyên nghiệp, trung lập, mang tính xây dựng.
2. Ẩn danh hoàn toàn (không gắn tên/nhóm cụ thể vào từng nhận xét).
3. Phần 'development_tips' CHỈ tạo cho các nhóm tiêu chí có điểm THẤP nhất ở trên.
4. CHỈ trả về DUY NHẤT một object JSON hợp lệ theo đúng schema sau (không thêm chữ nào
   ngoài JSON, không bọc trong ```):

{JSON_SCHEMA}
"""
    return prompt


def write_prompt(structured, out_dir, ma_nv):
    """Ghi prompt ra file prompt_<MaNV>.txt. Trả về đường dẫn."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, config.OUT_PROMPT.format(ma_nv=ma_nv))
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_prompt(structured))
    return path
