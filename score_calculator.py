# -*- coding: utf-8 -*-
"""
score_calculator.py
===================
TÍNH ĐIỂM 360° từ DataFrame chi tiết. Đây là "trái tim" của hệ thống.

CÔNG THỨC (đã đối chiếu khớp 100% với số liệu mẫu của file Tổng hợp gốc):

  1. Điểm 1 nhóm mục tiêu (Phẩm chất / Năng lực) của 1 người đánh giá:
        group_score = Σ(ĐIỂM × Hệ_số) / Σ(Hệ_số)        (chuẩn hoá theo tổng hệ số)

  2. Điểm tổng của 1 người đánh giá:
        total = Σ_nhóm( Trọng_số_nhóm × group_score ) / Σ_nhóm( Trọng_số_nhóm )
        (tương đương 0.3×Phẩm chất + 0.7×Năng lực)

  3. Điểm trung bình theo nhóm quan hệ (Cấp trên / Đồng cấp / Cấp dưới):
        = trung bình cộng `total` của những người ĐÃ ĐÁNH GIÁ trong nhóm đó.

  4. Tổng điểm 360°:
        = trung bình cộng điểm trung bình của CÁC NHÓM QUAN HỆ có dữ liệu
          (nhóm không ai đánh giá -> bỏ qua).

Ngoài ra còn tính:
  * Ma trận điểm theo 10 nhóm tiêu chí con × nhóm quan hệ (cho radar/heatmap).
  * Điểm theo từng hành vi (behavior) để lấy Top/Bottom & chênh lệch (gap).
"""

import unicodedata
import pandas as pd

import config


# ---------------------------------------------------------------------------
# Tiện ích chuẩn hoá text
# ---------------------------------------------------------------------------
def strip_accents(text):
    """Bỏ dấu tiếng Việt + về chữ thường để so khớp từ khoá an toàn."""
    if text is None:
        return ""
    s = unicodedata.normalize("NFD", str(text))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # 'đ'/'Đ' không tách dấu bằng NFD -> xử lý riêng.
    s = s.replace("đ", "d").replace("Đ", "D")
    return s.lower().strip()


def normalize_relationship(text):
    """Map giá trị cột 'Mối quan hệ' -> key nội bộ (cap_tren/dong_cap/cap_duoi)."""
    norm = strip_accents(text)
    for key, keywords in config.RELATIONSHIP_KEYWORDS.items():
        if any(kw in norm for kw in keywords):
            return key
    return None  # không nhận diện được


def classify_subcompetency(ten_muc_tieu, ten_nhom):
    """
    Phân loại 1 'Tên mục tiêu' vào 1 trong 10 nhóm tiêu chí con.
    Trả về (key, label, group) hoặc (None, None, None) nếu không khớp.
    """
    norm = strip_accents(ten_muc_tieu)
    for key, label, group, keywords in config.SUBCOMPETENCIES:
        if any(kw in norm for kw in [strip_accents(k) for k in keywords]):
            return key, label, group
    return None, None, None


def is_completed(trang_thai):
    """True nếu người đánh giá đã hoàn thành ('Đã đánh giá')."""
    return "da danh gia" in strip_accents(trang_thai)


# ---------------------------------------------------------------------------
# 1. ĐIỂM CỦA TỪNG NGƯỜI ĐÁNH GIÁ
# ---------------------------------------------------------------------------
def _weighted_group_score(group_rows):
    """group_score = Σ(điểm×hệ_số)/Σ(hệ_số). Trả về None nếu không có dữ liệu."""
    valid = group_rows.dropna(subset=["diem", "he_so"])
    total_heso = valid["he_so"].sum()
    if total_heso <= 0:
        # Không có hệ số -> dùng trung bình cộng đơn giản.
        return float(valid["diem"].mean()) if len(valid) else None
    return float((valid["diem"] * valid["he_so"]).sum() / total_heso)


def compute_evaluator_scores(df_emp):
    """
    Tính điểm cho từng người đánh giá của 1 nhân viên.

    Tham số:
        df_emp: DataFrame chi tiết đã lọc theo 1 mã nhân viên.
    Trả về:
        list[dict], mỗi dict gồm:
            ma_ad, relationship (key), completed (bool),
            group_scores {GROUP_*: float},
            total (float|None),
            subcomp {subcomp_key: float},
            y_kien_chung (str)
    """
    evaluators = []
    for ma_ad, rows in df_emp.groupby("ma_ad", sort=False):
        rel_key = normalize_relationship(rows["moi_quan_he"].iloc[0])
        completed = is_completed(rows["trang_thai"].iloc[0])

        # --- Điểm theo nhóm cha (Phẩm chất / Năng lực) + tổng có trọng số ---
        group_scores = {}
        weighted_sum = 0.0
        weight_sum = 0.0
        for group_key in (config.GROUP_PHAM_CHAT, config.GROUP_NANG_LUC):
            grows = rows[rows["ten_nhom"].apply(
                lambda v, gk=group_key: _match_group(v, gk))]
            gscore = _weighted_group_score(grows)
            group_scores[group_key] = gscore
            if gscore is not None and len(grows):
                w = grows["trong_so"].dropna()
                weight = float(w.iloc[0]) if len(w) else 0.0
                weighted_sum += weight * gscore
                weight_sum += weight

        total = (weighted_sum / weight_sum) if weight_sum > 0 else None

        # --- Điểm theo 10 nhóm tiêu chí con (trung bình các hành vi trong nhóm) ---
        subcomp = {}
        for key, label, group, _kw in config.SUBCOMPETENCIES:
            srows = rows[rows["ten_muc_tieu"].apply(
                lambda v, k=key: classify_subcompetency(v, None)[0] == k)]
            vals = srows["diem"].dropna()
            subcomp[key] = float(vals.mean()) if len(vals) else None

        evaluators.append({
            "ma_ad": ma_ad,
            "relationship": rel_key,
            "completed": completed,
            "group_scores": group_scores,
            "total": total,
            "subcomp": subcomp,
            "y_kien_chung": str(rows["y_kien_chung"].iloc[0]).strip(),
        })
    return evaluators


def _match_group(ten_nhom, group_key):
    """Khớp 'Tên nhóm mục tiêu' với GROUP_PHAM_CHAT / GROUP_NANG_LUC."""
    norm = strip_accents(ten_nhom)
    if group_key == config.GROUP_PHAM_CHAT:
        return "pham chat" in norm or "leadership qualities" in norm
    if group_key == config.GROUP_NANG_LUC:
        return "nang luc" in norm or "leadership ability" in norm
    return False


# ---------------------------------------------------------------------------
# 2. ĐIỂM TRUNG BÌNH THEO NHÓM QUAN HỆ + TỔNG 360
# ---------------------------------------------------------------------------
def compute_group_averages(evaluators):
    """
    Trả về dict {rel_key: {'score': float|None, 'n_completed': int, 'n_total': int}}.
    'score' = trung bình `total` của những người đã đánh giá trong nhóm.
    """
    result = {}
    for rel_key in config.RELATIONSHIP_ORDER:
        group = [e for e in evaluators if e["relationship"] == rel_key]
        completed = [e for e in group if e["completed"] and e["total"] is not None]
        score = (sum(e["total"] for e in completed) / len(completed)) if completed else None
        result[rel_key] = {
            "score": score,
            "n_completed": len(completed),
            "n_total": len(group),
        }
    return result


def compute_total_360(group_averages):
    """Tổng 360 = trung bình điểm của các nhóm quan hệ CÓ dữ liệu."""
    scores = [g["score"] for g in group_averages.values() if g["score"] is not None]
    return (sum(scores) / len(scores)) if scores else None


# ---------------------------------------------------------------------------
# 3. MA TRẬN ĐIỂM THEO NHÓM TIÊU CHÍ CON (cho radar / heatmap)
# ---------------------------------------------------------------------------
def compute_subcomp_matrix(evaluators):
    """
    Trả về list theo thứ tự config.SUBCOMPETENCIES, mỗi phần tử:
        {key, label, group, others, cap_tren, dong_cap, cap_duoi}
    - others   = trung bình (pooled) trên TẤT CẢ người đã đánh giá.
    - cap_*    = trung bình trên người đã đánh giá thuộc nhóm quan hệ tương ứng.
    Giá trị None nếu không có dữ liệu.
    """
    completed = [e for e in evaluators if e["completed"]]
    matrix = []
    for key, label, group, _kw in config.SUBCOMPETENCIES:
        row = {"key": key, "label": label, "group": group}

        # others (pooled)
        pooled = [e["subcomp"][key] for e in completed if e["subcomp"].get(key) is not None]
        row["others"] = (sum(pooled) / len(pooled)) if pooled else None

        # theo từng nhóm quan hệ
        for rel_key in config.RELATIONSHIP_ORDER:
            vals = [
                e["subcomp"][key]
                for e in completed
                if e["relationship"] == rel_key and e["subcomp"].get(key) is not None
            ]
            row[rel_key] = (sum(vals) / len(vals)) if vals else None
        matrix.append(row)
    return matrix


# ---------------------------------------------------------------------------
# 4. ĐIỂM THEO TỪNG HÀNH VI (behavior) – cho Top/Bottom & Gap
# ---------------------------------------------------------------------------
def compute_behavior_scores(df_emp):
    """
    Tính điểm pooled & theo nhóm quan hệ cho TỪNG hành vi (mỗi 'Tên mục tiêu').
    Trả về list[dict]: {behavior, subcomp_key, subcomp_label, group,
                        others, cap_tren, dong_cap, cap_duoi}
    """
    # Chỉ lấy dòng của người đã đánh giá.
    df = df_emp[df_emp["trang_thai"].apply(is_completed)].copy()
    df["rel_key"] = df["moi_quan_he"].apply(normalize_relationship)

    behaviors = []
    for behavior_text, rows in df.groupby("ten_muc_tieu", sort=False):
        sub_key, sub_label, group = classify_subcompetency(behavior_text, None)
        if sub_key is None:
            continue  # bỏ qua tiêu chí không phân loại được

        rec = {
            "behavior": behavior_text,
            "subcomp_key": sub_key,
            "subcomp_label": sub_label,
            "group": group,
        }
        diem_all = rows["diem"].dropna()
        rec["others"] = float(diem_all.mean()) if len(diem_all) else None
        for rel_key in config.RELATIONSHIP_ORDER:
            v = rows[rows["rel_key"] == rel_key]["diem"].dropna()
            rec[rel_key] = float(v.mean()) if len(v) else None
        behaviors.append(rec)
    return behaviors


def top_bottom_behaviors(behaviors, n=5):
    """Lấy Top n & Bottom n hành vi theo điểm 'others'."""
    valid = [b for b in behaviors if b["others"] is not None]
    top = sorted(valid, key=lambda b: b["others"], reverse=True)[:n]
    bottom = sorted(valid, key=lambda b: b["others"])[:n]
    return top, bottom


def biggest_gaps(behaviors, rel_a=config.REL_CAP_DUOI, rel_b=config.REL_DONG_CAP, n=5):
    """
    Lấy n hành vi có chênh lệch lớn nhất giữa 2 nhóm quan hệ (mặc định
    Cấp dưới vs Đồng cấp). delta = rel_a - rel_b (giữ dấu).
    """
    gaps = []
    for b in behaviors:
        a, c = b.get(rel_a), b.get(rel_b)
        if a is not None and c is not None:
            gaps.append({
                "subcomp_label": b["subcomp_label"],
                "behavior": b["behavior"],
                "a": a, "b": c, "delta": a - c,
            })
    gaps.sort(key=lambda g: abs(g["delta"]), reverse=True)
    return gaps[:n]


# ---------------------------------------------------------------------------
# 5. THỐNG KÊ HOÀN THÀNH
# ---------------------------------------------------------------------------
def completion_stats(evaluators):
    """Trả về (so_hoan_thanh, tong_nguoi_moi)."""
    total = len(evaluators)
    completed = sum(1 for e in evaluators if e["completed"])
    return completed, total
