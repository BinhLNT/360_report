# -*- coding: utf-8 -*-
"""
chart_generator.py
==================
Sinh các biểu đồ bằng matplotlib và trả về dạng base64 (data URI) để nhúng
thẳng vào HTML/PDF (không cần file ảnh rời).

4 biểu đồ tương ứng các phần của báo cáo:
  * score_bar : điểm tổng theo nhóm quan hệ (Phần 1)
  * radar     : radar 10 nhóm tiêu chí con (Phần 2)
  * consensus : ma trận đồng thuận giữa các nhóm rater (Phần 3)
  * gap_bar   : chênh lệch Cấp dưới vs Đồng cấp theo nhóm tiêu chí (Phần 4)

Dùng backend 'Agg' để chạy headless (không cần GUI).
"""

import base64
import io
import math

import matplotlib
matplotlib.use("Agg")  # backend không cần màn hình
import matplotlib.pyplot as plt
import numpy as np

import config

# Font hỗ trợ tiếng Việt (DejaVu Sans là font mặc định của matplotlib, đủ dấu).
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False

# Bảng màu chủ đạo (đồng bộ với template).
COLOR_PRIMARY = "#1F4E79"
COLOR_ACCENT = "#2E75B6"
COLOR_GREEN = "#2E7D32"
COLOR_ORANGE = "#ED7D31"
COLOR_RED = "#C00000"
COLOR_GREY = "#BBBBBB"


# ---------------------------------------------------------------------------
# Tiện ích chung
# ---------------------------------------------------------------------------
def _fig_to_base64(fig):
    """Chuyển figure matplotlib -> chuỗi data URI base64 PNG, rồi đóng figure."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return "data:image/png;base64," + b64


def build_all_charts(structured):
    """Tạo cả 4 biểu đồ, trả về dict {name: data_uri}."""
    return {
        "score_bar": chart_score_bar(structured),
        "radar": chart_radar(structured),
        "consensus": chart_consensus(structured),
        "gap_bar": chart_gap_bar(structured),
    }


# ---------------------------------------------------------------------------
# 1. Biểu đồ điểm tổng theo nhóm quan hệ
# ---------------------------------------------------------------------------
def chart_score_bar(structured):
    labels, values, colors = [], [], []

    # Cột Tổng 360 trước.
    total = structured["total_360"]
    if total is not None:
        labels.append("TỔNG 360°")
        values.append(total)
        colors.append(COLOR_PRIMARY)

    # Các nhóm quan hệ có dữ liệu.
    for rel in structured["relationship_order"]:
        g = structured["group_averages"][rel]
        if g["score"] is not None:
            labels.append(g["label"])
            values.append(g["score"])
            colors.append(COLOR_ACCENT)

    fig, ax = plt.subplots(figsize=(8.2, max(1.6, 0.7 * len(labels) + 0.8)))
    if not values:
        ax.text(0.5, 0.5, "Chưa có dữ liệu điểm", ha="center", va="center")
        ax.axis("off")
        return _fig_to_base64(fig)

    y = np.arange(len(labels))[::-1]  # đảo để mục đầu nằm trên
    bars = ax.barh(y, values, color=colors, height=0.55)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlim(0, config.SCORE_MAX)
    ax.set_xlabel("Điểm (thang 1 – 5)", fontsize=10)
    ax.axvline(config.CONSENSUS_THRESHOLD, color=COLOR_ORANGE, linestyle="--",
               linewidth=1, alpha=0.7)
    for bar, val in zip(bars, values):
        ax.text(val + 0.06, bar.get_y() + bar.get_height() / 2,
                f"{val:.2f}", va="center", fontsize=11, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_base64(fig)


# ---------------------------------------------------------------------------
# 2. Biểu đồ radar 10 nhóm tiêu chí con
# ---------------------------------------------------------------------------
def chart_radar(structured):
    subs = structured["subcompetencies"]
    labels = [s["label"] for s in subs]
    n = len(labels)

    angles = [i / n * 2 * math.pi for i in range(n)]
    angles += angles[:1]  # khép vòng

    fig = plt.figure(figsize=(8.6, 8.0))
    ax = fig.add_subplot(111, polar=True)
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, config.SCORE_MAX)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], fontsize=8, color="#888")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)

    # Vùng "Others" (tổng) tô nền.
    others = [_z(s["others"]) for s in subs]
    others += others[:1]
    ax.plot(angles, others, color=COLOR_PRIMARY, linewidth=2, label="Tổng (Others)")
    ax.fill(angles, others, color=COLOR_ACCENT, alpha=0.25)

    # Đường nét đứt cho từng nhóm quan hệ có dữ liệu.
    rel_styles = {
        config.REL_CAP_TREN: (COLOR_RED, ":"),
        config.REL_DONG_CAP: (COLOR_ORANGE, "--"),
        config.REL_CAP_DUOI: (COLOR_GREEN, "-."),
    }
    for rel, (color, ls) in rel_styles.items():
        vals = [s.get(rel) for s in subs]
        if all(v is None for v in vals):
            continue
        plotted = [_z(v) for v in vals]
        plotted += plotted[:1]
        ax.plot(angles, plotted, color=color, linewidth=1.4, linestyle=ls,
                label=config.RELATIONSHIP_DISPLAY[rel])

    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.10), fontsize=9)
    fig.tight_layout()
    return _fig_to_base64(fig)


# ---------------------------------------------------------------------------
# 3. Ma trận đồng thuận (heatmap subcomp × nhóm quan hệ)
# ---------------------------------------------------------------------------
def chart_consensus(structured):
    subs = structured["subcompetencies"]
    rels = structured["relationship_order"]
    rel_labels = [config.RELATIONSHIP_DISPLAY[r] for r in rels]
    row_labels = [s["label"] for s in subs]

    # Ma trận giá trị (NaN nếu thiếu).
    data = np.full((len(subs), len(rels)), np.nan)
    for i, s in enumerate(subs):
        for j, r in enumerate(rels):
            v = s.get(r)
            if v is not None:
                data[i, j] = v

    cmap = plt.cm.RdYlGn.copy()
    cmap.set_bad(color="#EEEEEE")  # ô thiếu dữ liệu -> xám nhạt

    fig, ax = plt.subplots(figsize=(7.2, 8.4))
    masked = np.ma.masked_invalid(data)
    im = ax.imshow(masked, cmap=cmap, vmin=config.SCORE_MIN, vmax=config.SCORE_MAX,
                   aspect="auto")

    ax.set_xticks(range(len(rel_labels)))
    ax.set_xticklabels(rel_labels, fontsize=10)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=9)

    # Ghi giá trị lên từng ô.
    for i in range(len(subs)):
        for j in range(len(rels)):
            v = data[i, j]
            txt = "—" if np.isnan(v) else f"{v:.2f}"
            color = "black" if (np.isnan(v) or v >= config.CONSENSUS_THRESHOLD) else "white"
            ax.text(j, i, txt, ha="center", va="center", fontsize=9, color=color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.6)
    cbar.set_label(f"Điểm (ngưỡng tham chiếu {config.CONSENSUS_THRESHOLD})", fontsize=9)
    ax.set_title("Ma trận điểm theo nhóm tiêu chí × nhóm rater", fontsize=11, pad=12)
    fig.tight_layout()
    return _fig_to_base64(fig)


# ---------------------------------------------------------------------------
# 4. Biểu đồ chênh lệch Cấp dưới vs Đồng cấp
# ---------------------------------------------------------------------------
def chart_gap_bar(structured):
    subs = structured["subcompetencies"]
    items = []
    for s in subs:
        a, b = s.get(config.REL_CAP_DUOI), s.get(config.REL_DONG_CAP)
        if a is not None and b is not None:
            items.append((s["label"], a - b))

    fig, ax = plt.subplots(figsize=(8.2, max(2.0, 0.55 * len(items) + 1.0)))
    if not items:
        ax.text(0.5, 0.5, "Không đủ 2 nhóm rater để so chênh lệch",
                ha="center", va="center")
        ax.axis("off")
        return _fig_to_base64(fig)

    items.sort(key=lambda x: x[1])
    labels = [x[0] for x in items]
    deltas = [x[1] for x in items]
    y = np.arange(len(labels))
    colors = [COLOR_GREEN if d >= 0 else COLOR_RED for d in deltas]
    bars = ax.barh(y, deltas, color=colors, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.axvline(0, color="#333", linewidth=0.8)
    ax.set_xlabel("Δ = Điểm Cấp dưới − Điểm Đồng cấp", fontsize=10)
    for bar, d in zip(bars, deltas):
        offset = 0.02 if d >= 0 else -0.02
        ax.text(d + offset, bar.get_y() + bar.get_height() / 2,
                f"{d:+.2f}", va="center",
                ha="left" if d >= 0 else "right", fontsize=9, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_base64(fig)


def _z(v):
    """None -> 0 để vẽ; giữ nguyên nếu có giá trị."""
    return 0.0 if v is None else float(v)
