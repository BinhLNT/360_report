# -*- coding: utf-8 -*-
"""
structured_from_file4.py
========================
Đọc NGƯỢC "File thứ 4" (định dạng wide) và dựng lại structured-like dict cho từng
nhân viên — **CHỈ TỪ chính File thứ 4** (điểm 24 hành vi × 4 khối rater + ý kiến),
KHÔNG cần file Chi tiết gốc.

Nhờ đó: người dùng chỉ cần upload File thứ 4 (đã có cột điểm từ Bước 1) là AI tự
sinh được nội dung — File thứ 4 trở thành đầu vào ĐỘC LẬP.

Bố cục cột lấy từ `competency_exporter._build_column_spec()` (nguồn chân lý duy
nhất), nên luôn khớp với cách Bước 1 GHI ra File thứ 4. Tái dùng đúng các hàm
tổng hợp của `score_calculator` (top/bottom, gaps) và badge của `structured_data`
để đảm bảo nhất quán với đường tính từ Chi tiết.
"""

import re
from datetime import datetime

import openpyxl

import config
import competency_exporter
import score_calculator as calc
import structured_data

_SUBCOMP_LABEL = {key: label for key, label, _g, _kw in config.SUBCOMPETENCIES}
_SUBCOMP_GROUP = {key: group for key, label, group, _kw in config.SUBCOMPETENCIES}
_COMP_COUNT_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_CMT_LINE_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------
def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_comments(text):
    """'[Cấp trên] abc\n[Đồng cấp] def' -> [{rel:'Cấp trên', text:'abc'}, ...].

    Ô "Ý kiến" gộp các ý kiến bằng '\n' nhưng KHÔNG escape '\n' bên trong từng ý
    kiến. Vì vậy dòng KHÔNG khớp tiền tố '[rel]' được coi là DÒNG TIẾP NỐI của ý
    kiến ngay trước (nối lại), tránh tách vụn 1 ý kiến thành nhiều mục rel rỗng.
    """
    out = []
    for line in str(text or "").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        m = _CMT_LINE_RE.match(line)
        if m:
            out.append({"rel": m.group(1).strip(), "text": m.group(2).strip()})
        elif out:
            out[-1]["text"] = (out[-1]["text"] + "\n" + line).strip()
        else:
            out.append({"rel": "", "text": line})
    return out


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals)) if vals else None


# ---------------------------------------------------------------------------
# Bản đồ cột (đo 1 lần từ spec)
# ---------------------------------------------------------------------------
def _column_index():
    """Trả về dict các chỉ số cột (0-based) cần để đọc điểm/ý kiến từ File 4."""
    spec = competency_exporter._build_column_spec()
    idx = {"identity": {}, "scores": [], "comments": [], "ketqua": None, "ykien": None}
    for i, c in enumerate(spec):
        kind = c["kind"]
        if kind == "identity":
            idx["identity"][c["key"]] = i
        elif kind == "ketqua":
            idx["ketqua"] = i
        elif kind == "ykien":
            idx["ykien"] = i
        elif kind == "score":
            if c.get("sub_role") == "score":
                idx["scores"].append((i, c["behavior_index"], c["score_src"]))
            elif c.get("sub_role") == "comment":
                idx["comments"].append((i, c["behavior_index"]))
    return idx


# ---------------------------------------------------------------------------
# Dựng structured cho 1 dòng
# ---------------------------------------------------------------------------
def _build_one(row, idx, report_date):
    def cell(ci):
        return row[ci] if (ci is not None and ci < len(row)) else None

    ident = idx["identity"]
    ma_nv = str(cell(ident.get("ma_nv")) or "").strip()
    if not ma_nv:
        return None

    employee = {
        "ma_nv": ma_nv,
        "ho_ten": str(cell(ident.get("ho_ten")) or "").strip(),
        "chuc_danh": str(cell(ident.get("chuc_danh")) or "").strip(),
        "bo_phan": str(cell(ident.get("ban_chuoi_khoi")) or "").strip(),
        "cap_bac": str(cell(ident.get("cap_bac")) or "").strip(),
        "ma_bieu_mau": "",
    }
    trang_thai = str(cell(ident.get("trang_thai")) or "").strip()
    total_360 = _to_float(cell(idx["ketqua"]))

    # --- 24 hành vi: điểm theo 4 nguồn ---
    behaviors = []
    for sub_key, behavior_text in config.BEHAVIORS:
        behaviors.append({
            "behavior": behavior_text, "subcomp_key": sub_key,
            "subcomp_label": _SUBCOMP_LABEL.get(sub_key, sub_key),
            "group": _SUBCOMP_GROUP.get(sub_key),
            "others": None, "cap_tren": None, "dong_cap": None, "cap_duoi": None,
            "comments": [],
        })
    for ci, b_idx, score_src in idx["scores"]:
        if 0 <= b_idx < len(behaviors):
            behaviors[b_idx][score_src] = _to_float(cell(ci))
    for ci, b_idx in idx["comments"]:
        if 0 <= b_idx < len(behaviors):
            behaviors[b_idx]["comments"] = _parse_comments(cell(ci))

    # --- 10 nhóm tiêu chí con (gộp từ 24 hành vi) ---
    subcompetencies = []
    for key, label, group, _kw in config.SUBCOMPETENCIES:
        grp = [b for b in behaviors if b["subcomp_key"] == key]
        subcompetencies.append({
            "key": key, "label": label, "group": group,
            "others": _mean([b["others"] for b in grp]),
            "cap_tren": _mean([b["cap_tren"] for b in grp]),
            "dong_cap": _mean([b["dong_cap"] for b in grp]),
            "cap_duoi": _mean([b["cap_duoi"] for b in grp]),
        })

    # --- Điểm theo nhóm quan hệ (xấp xỉ: TB điểm hành vi của nhóm đó) ---
    group_averages = {}
    for rel in config.RELATIONSHIP_ORDER:
        score = _mean([b[rel] for b in behaviors])
        group_averages[rel] = {
            "label": config.RELATIONSHIP_DISPLAY[rel],
            "score": score, "n_completed": None, "n_total": None,
        }

    # --- Top/Bottom & Gap: TÁI DÙNG score_calculator (nhất quán với Chi tiết) ---
    top5, bottom5 = calc.top_bottom_behaviors(behaviors, n=5)
    gaps = calc.biggest_gaps(behaviors, n=5)

    # --- Ý kiến (gộp & ẩn danh) lấy từ cột "Ý kiến đánh giá (từng người…)" ---
    all_comments = _parse_comments(cell(idx["ykien"]))
    seen, comments = set(), []
    for c in all_comments:
        t = c["text"].strip()
        if t and t not in seen:
            seen.add(t)
            comments.append(t)

    # --- Completion: tách "x/y" trong Trạng thái ---
    m = _COMP_COUNT_RE.search(trang_thai)
    completed, total = (int(m.group(1)), int(m.group(2))) if m else (None, None)

    return {
        "employee": employee,
        "report_date": report_date,
        "weights": {"pham_chat": config.WEIGHT_PHAM_CHAT, "nang_luc": config.WEIGHT_NANG_LUC},
        "consensus_threshold": config.CONSENSUS_THRESHOLD,
        "completion": {"completed": completed, "total": total, "status_text": trang_thai},
        "group_averages": group_averages,
        "total_360": total_360,
        "badge": structured_data._make_badge(total_360),
        "subcompetencies": subcompetencies,
        "behaviors": behaviors,
        "top5": [{"label": b["subcomp_label"], "behavior": b["behavior"], "score": b["others"]} for b in top5],
        "bottom5": [{"label": b["subcomp_label"], "behavior": b["behavior"], "score": b["others"]} for b in bottom5],
        "gaps": gaps,
        "comments": comments,
        "all_comments": all_comments,
        "opinion_text": "\n\n".join(comments),
        "relationship_order": config.RELATIONSHIP_ORDER,
        "relationship_display": config.RELATIONSHIP_DISPLAY,
        "source": "file4",          # đánh dấu: dựng từ File thứ 4 (độc lập)
    }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def build_all(path, first_data_row=4, report_date=None):
    """Đọc File thứ 4 -> list[structured] cho mọi nhân viên (bỏ dòng không có mã NV)."""
    if report_date is None:
        report_date = datetime.now().strftime("%d/%m/%Y")
    idx = _column_index()
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    out = []
    for row in ws.iter_rows(min_row=first_data_row, values_only=True):
        if row is None:
            continue
        s = _build_one(row, idx, report_date)
        if s is not None:
            out.append(s)
    wb.close()
    return out
