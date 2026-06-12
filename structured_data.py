# -*- coding: utf-8 -*-
"""
structured_data.py
==================
Lắp ráp toàn bộ kết quả tính toán thành MỘT dict "structured data" – nguồn dữ
liệu duy nhất dùng chung cho: (a) template HTML, (b) sinh prompt cho Claude,
(c) sinh nội dung định tính mặc định khi chưa có Claude.

Dict này thuần SỐ LIỆU (không chứa ảnh base64) để có thể ghi ra JSON gọn nhẹ.
"""

from datetime import datetime

import config
import score_calculator as calc


def build_structured_data(ma_nv, df_chi_tiet, report_date=None):
    """
    Tạo structured data cho 1 nhân viên.

    Tham số:
        ma_nv       : mã nhân viên (str)
        df_chi_tiet : DataFrame chi tiết đã đọc (toàn bộ nhân viên)
        report_date : 'dd/mm/yyyy' (mặc định = hôm nay)
    Trả về: dict structured data.
    """
    if report_date is None:
        report_date = datetime.now().strftime("%d/%m/%Y")

    # 1. Lọc dữ liệu của riêng nhân viên này.
    df_emp = df_chi_tiet[df_chi_tiet["ma_nhan_vien"].astype(str).str.strip()
                         == str(ma_nv).strip()].reset_index(drop=True)
    if df_emp.empty:
        raise ValueError(f"Không tìm thấy dữ liệu cho mã nhân viên '{ma_nv}' trong file Chi tiết.")

    first = df_emp.iloc[0]
    employee = {
        "ma_nv": str(ma_nv).strip(),
        "ho_ten": str(first["ho_ten"]).strip(),
        "chuc_danh": str(first["chuc_danh"]).strip(),
        "bo_phan": str(first["bo_phan"]).strip(),
        "cap_bac": str(first["cap_bac"]).strip(),
        "ma_bieu_mau": str(first["ma_bieu_mau"]).strip(),
    }

    # 2. Tính điểm.
    evaluators = calc.compute_evaluator_scores(df_emp)
    group_averages = calc.compute_group_averages(evaluators)
    total_360 = calc.compute_total_360(group_averages)
    subcomp_matrix = calc.compute_subcomp_matrix(evaluators)
    behaviors = calc.compute_behavior_scores(df_emp)
    top5, bottom5 = calc.top_bottom_behaviors(behaviors, n=5)
    gaps = calc.biggest_gaps(behaviors, n=5)
    n_completed, n_total = calc.completion_stats(evaluators)

    # 3. Trạng thái & ý kiến chung tổng hợp.
    status_label = "Đã hoàn thành" if (n_total > 0 and n_completed == n_total) else "Chưa hoàn thành"
    status_text = f"{status_label} {n_completed}/{n_total}"
    comments = _collect_comments(evaluators)
    all_comments = _collect_all_comments(evaluators)
    opinion_text = "\n\n".join(comments)

    # 4. Badge xếp loại.
    badge = _make_badge(total_360)

    # 5. Đánh giá độ tin cậy dữ liệu (data quality).
    data_quality = _assess_quality(group_averages)

    # 6. Đóng gói.
    structured = {
        "employee": employee,
        "report_date": report_date,
        "weights": {"pham_chat": config.WEIGHT_PHAM_CHAT, "nang_luc": config.WEIGHT_NANG_LUC},
        "consensus_threshold": config.CONSENSUS_THRESHOLD,
        "completion": {"completed": n_completed, "total": n_total, "status_text": status_text},
        "group_averages": {
            rel: {
                "label": config.RELATIONSHIP_DISPLAY[rel],
                "score": group_averages[rel]["score"],
                "n_completed": group_averages[rel]["n_completed"],
                "n_total": group_averages[rel]["n_total"],
            }
            for rel in config.RELATIONSHIP_ORDER
        },
        "total_360": total_360,
        "badge": badge,
        "subcompetencies": subcomp_matrix,
        "behaviors": _compact_behaviors(behaviors),
        "top5": _simplify_behaviors(top5),
        "bottom5": _simplify_behaviors(bottom5),
        "gaps": gaps,
        "comments": comments,
        "all_comments": all_comments,
        "opinion_text": opinion_text,
        "data_quality": data_quality,
        "relationship_order": config.RELATIONSHIP_ORDER,
        "relationship_display": config.RELATIONSHIP_DISPLAY,
    }
    return structured, df_emp


# ---------------------------------------------------------------------------
# Hàm phụ trợ
# ---------------------------------------------------------------------------
def _collect_comments(evaluators):
    """Lấy danh sách ý kiến chung KHÁC RỖNG & KHÔNG TRÙNG của người đã đánh giá."""
    seen = set()
    comments = []
    for e in evaluators:
        if not e["completed"]:
            continue
        txt = (e["y_kien_chung"] or "").strip()
        if txt and txt.lower() not in ("nan", "n/a", "#n/a") and txt not in seen:
            seen.add(txt)
            comments.append(txt)
    return comments


def _collect_all_comments(evaluators):
    """Lấy TOÀN BỘ ý kiến của TỪNG người đánh giá đã hoàn thành (không gộp trùng),
    ẩn danh theo NHÓM quan hệ. Trả về list[{rel, text}]."""
    out = []
    for e in evaluators:
        if not e["completed"]:
            continue
        txt = (e["y_kien_chung"] or "").strip()
        if txt and txt.lower() not in ("nan", "n/a", "#n/a"):
            rel = config.RELATIONSHIP_DISPLAY.get(e["relationship"], "Khác")
            out.append({"rel": rel, "text": txt})
    return out


def _make_badge(total):
    """Chọn nhãn xếp loại theo tổng điểm 360."""
    if total is None:
        return {"label": "Chưa đủ dữ liệu", "color": "#888888"}
    for threshold, label, color in config.BADGE_LEVELS:
        if total >= threshold:
            return {"label": label, "color": color}
    return {"label": "Dưới mong đợi", "color": "#C00000"}


def _assess_quality(group_averages):
    """Sinh cảnh báo về độ tin cậy dữ liệu (thiếu Self/Cấp trên, nhóm nhỏ...)."""
    has_cap_tren = group_averages[config.REL_CAP_TREN]["n_completed"] > 0
    n_dong_cap = group_averages[config.REL_DONG_CAP]["n_completed"]
    n_cap_duoi = group_averages[config.REL_CAP_DUOI]["n_completed"]

    missing = []
    # Bộ dữ liệu 360 hiện không có nhóm "Tự đánh giá".
    missing.append("Tự đánh giá")
    if not has_cap_tren:
        missing.append("Cấp trên")

    parts = []
    if missing:
        parts.append("Báo cáo KHÔNG có dữ liệu " + " & ".join(f"<b>{m}</b>" for m in missing) + ".")
    if n_dong_cap <= 1:
        parts.append(f"Nhóm <b>Đồng cấp chỉ có {n_dong_cap} người</b> hoàn thành.")
    if parts:
        parts.append(
            "Do đó: (1) chưa dựng được Johari Window thật (Self vs Others) — Phần 3 dùng "
            "<b>Ma trận đồng thuận giữa các nhóm rater</b> thay thế; "
            "(2) các so sánh liên quan nhóm ít người chỉ mang tính tham khảo. "
            "Khuyến nghị thu thập thêm góc nhìn Self & Cấp trên trước khi ra quyết định nhân sự."
        )

    return {
        "has_self": False,
        "has_cap_tren": has_cap_tren,
        "n_dong_cap": n_dong_cap,
        "n_cap_duoi": n_cap_duoi,
        "warning_html": " ".join(parts),
    }


def _compact_behaviors(behaviors):
    """Giữ TOÀN BỘ hành vi (điểm theo từng nhóm rater) để dựng ma trận File thứ 4.

    Mỗi phần tử: {subcomp_key, behavior, others, cap_tren, dong_cap, cap_duoi}.
    Exporter sẽ gom theo subcomp_key + thứ tự để khớp vào 24 hành vi chuẩn.
    """
    return [
        {
            "subcomp_key": b["subcomp_key"],
            "behavior": b["behavior"],
            "others": b.get("others"),
            "cap_tren": b.get("cap_tren"),
            "dong_cap": b.get("dong_cap"),
            "cap_duoi": b.get("cap_duoi"),
            "comments": b.get("comments", []),   # ý kiến theo từng mục tiêu (per-objective)
        }
        for b in behaviors
    ]


def _simplify_behaviors(behaviors):
    """Rút gọn list behavior cho top/bottom: chỉ giữ nhãn + điểm."""
    return [
        {
            "label": b["subcomp_label"],
            "behavior": b["behavior"],
            "score": b["others"],
        }
        for b in behaviors
    ]
