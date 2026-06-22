# -*- coding: utf-8 -*-
"""
content_provider.py
==================
Sinh phần NỘI DUNG ĐỊNH TÍNH MẶC ĐỊNH cho báo cáo theo LUẬT từ số liệu
(rule-based, KHÔNG gọi AI). Dùng làm FALLBACK của report_content khi một nhân
viên chưa có nội dung AI trong File thứ 4 — để báo cáo vẫn đầy đủ.

(Nội dung AI thật do `ai_engine` tự động sinh & ghi vào File thứ 4.)
"""

import config


# ---------------------------------------------------------------------------
# Sinh nội dung mặc định theo LUẬT (không AI)
# ---------------------------------------------------------------------------
def build_default_content(structured):
    """Tạo nội dung định tính mặc định từ số liệu structured (rule-based)."""
    return {
        "executive_summary": _default_summary(structured),
        "start_stop_continue": {
            "continue": _default_continue(structured),
            "start": _default_start(structured),
            "stop": _default_stop(structured),
        },
        "analysis": _default_analysis(structured),
        "development_tips": _default_tips(structured),
        "ai_note": ("Phần định tính dưới đây được hệ thống TỔNG HỢP TỰ ĐỘNG theo luật từ số liệu "
                    "(chưa có nội dung AI). Khuyến nghị OD/HRBP rà soát và bổ sung nhận định trước khi "
                    "dùng trong coaching."),
    }


def _fmt(v):
    if v is None:
        return config.NA_TEXT
    return f"{float(v):.{config.DISPLAY_DECIMALS}f}"


def _sorted_subcomps(structured, reverse=False):
    """Sắp xếp nhóm tiêu chí con theo điểm 'others' (loại None)."""
    subs = [s for s in structured["subcompetencies"] if s["others"] is not None]
    return sorted(subs, key=lambda s: s["others"], reverse=reverse)


def _default_summary(structured):
    emp = structured["employee"]
    total = structured["total_360"]
    badge = structured["badge"]["label"]
    strongest = _sorted_subcomps(structured, reverse=True)[:3]
    strong_txt = ", ".join(s["label"] for s in strongest) if strongest else "—"
    return (
        f"Tổng điểm 360° của <b>{emp['ho_ten']}</b> đạt <b>{_fmt(total)}/5.00</b> "
        f"(xếp loại: <b>{badge}</b>), tổng hợp từ "
        f"{structured['completion']['completed']}/{structured['completion']['total']} "
        f"người đánh giá đã hoàn thành. "
        f"Các nhóm tiêu chí nổi bật nhất: <b>{strong_txt}</b>. "
        f"Báo cáo phục vụ mục đích phát triển cá nhân; cần đọc cùng phần lưu ý độ tin cậy dữ liệu."
    )


def _default_continue(structured):
    top = _sorted_subcomps(structured, reverse=True)[:3]
    items = [f"Tiếp tục phát huy thế mạnh ở nhóm <b>{s['label']}</b> (điểm {_fmt(s['others'])})."
             for s in top]
    if structured["comments"]:
        items.append("Duy trì tinh thần trách nhiệm và vai trò dẫn dắt được đồng nghiệp ghi nhận.")
    return items or ["Tiếp tục duy trì các điểm mạnh hiện có."]


def _default_start(structured):
    low = _sorted_subcomps(structured)[:2]
    items = [f"Tập trung cải thiện nhóm <b>{s['label']}</b> (điểm {_fmt(s['others'])} — thấp nhất)."
             for s in low]
    items.append("Tăng cường trao đổi & tham vấn đội ngũ trong quá trình ra và triển khai quyết định "
                 "để tạo đồng thuận và nâng hiệu quả thực thi.")
    return items


def _default_stop(structured):
    return ["Chưa ghi nhận phản hồi định tính nào chỉ ra hành vi cần dừng. "
            "Lưu ý số lượng người đánh giá còn ít và phản hồi thiên về tổng quan."]


def _default_analysis(structured):
    gaps = structured["gaps"]
    if not gaps:
        return ("Chưa đủ dữ liệu từ ≥2 nhóm rater để phân tích chênh lệch góc nhìn. "
                "Khuyến nghị thu thập thêm góc nhìn Cấp trên và Tự đánh giá.")
    g = gaps[0]
    direction = "cao hơn" if g["delta"] > 0 else "thấp hơn"
    return (
        f"Chênh lệch góc nhìn lớn nhất nằm ở nhóm <b>{g['subcomp_label']}</b>: "
        f"Cấp dưới đánh giá {direction} Đồng cấp ({_fmt(g['a'])} so với {_fmt(g['b'])}, "
        f"Δ={_fmt(g['delta'])}). Đây là điểm đáng lưu ý để đối thoại trong coaching nhằm "
        f"thống nhất kỳ vọng giữa các nhóm liên quan."
    )


def _default_tips(structured):
    """Lấy tip từ thư viện config.DEV_TIPS cho 4 nhóm tiêu chí điểm thấp nhất."""
    low = _sorted_subcomps(structured)[:4]
    tips = {}
    for s in low:
        lib = config.DEV_TIPS.get(s["key"])
        if lib:
            tips[s["label"]] = list(lib)
    return tips
