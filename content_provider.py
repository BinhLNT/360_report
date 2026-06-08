# -*- coding: utf-8 -*-
"""
content_provider.py
==================
Cung cấp phần NỘI DUNG ĐỊNH TÍNH cho báo cáo theo 2 nguồn:

  (A) Từ Claude: đọc file JSON `claude_content_<MaNV>.json` mà người dùng dán
      kết quả của Claude vào (đúng schema ở prompt).
  (B) Mặc định (fallback): nếu chưa có file JSON, hệ thống TỰ SINH nội dung
      theo LUẬT từ số liệu (rule-based) — không dùng AI — để báo cáo vẫn đầy đủ.

Nhờ vậy hệ thống chạy được end-to-end ngay cả khi chưa có Claude, đồng thời sẵn
sàng "ghép nội dung từ Claude" khi có file JSON.
"""

import json
import os

import config


# ---------------------------------------------------------------------------
# Lựa chọn nguồn nội dung
# ---------------------------------------------------------------------------
def get_content(structured, content_path=None):
    """
    Trả về (content_dict, source) trong đó source ∈ {'claude', 'default'}.

    - Nếu content_path tồn tại & đọc được JSON hợp lệ -> dùng (A).
    - Ngược lại -> sinh nội dung mặc định (B).
    """
    if content_path and os.path.isfile(content_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _normalize_content(data), "claude"
        except (json.JSONDecodeError, OSError):
            # File lỗi -> rơi về mặc định, không làm vỡ pipeline.
            pass
    return build_default_content(structured), "default"


def _strip_code_fence(text):
    """Bóc khối ```json ... ``` nếu người dùng dán kèm (Claude hay bọc như vậy)."""
    t = text.strip()
    if t.startswith("```"):
        # Bỏ dòng mở đầu (```json hoặc ```), giữ phần còn lại tới dấu đóng.
        lines = t.splitlines()
        if lines:
            lines = lines[1:]                       # bỏ dòng ```... mở đầu
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]                      # bỏ dòng ``` đóng
        t = "\n".join(lines).strip()
    return t


def save_claude_content(out_dir, ma_nv, raw_text):
    """
    Lưu nội dung Claude (chuỗi JSON người dùng DÁN vào sản phẩm) thành file
    `claude_content_<MaNV>.json` để bước render đọc lên.

    Trả về (path, content_dict đã chuẩn hoá). Ném ValueError nếu JSON không hợp lệ.
    """
    raw_text = _strip_code_fence(raw_text or "")
    if not raw_text:
        raise ValueError("Nội dung trống. Hãy dán JSON kết quả của Claude vào ô bên dưới.")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON không hợp lệ (dòng {exc.lineno}, cột {exc.colno}): {exc.msg}. "
            "Hãy đảm bảo bạn dán ĐÚNG object JSON Claude trả về (không kèm chữ thừa)."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("JSON phải là một object (bắt đầu bằng '{').")

    content = _normalize_content(data)                # kiểm tra & điền key thiếu
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, config.OUT_CONTENT.format(ma_nv=ma_nv))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path, content


def _normalize_content(data):
    """Đảm bảo content từ Claude có đủ key cần thiết (điền rỗng nếu thiếu)."""
    ssc = data.get("start_stop_continue", {}) or {}
    return {
        "executive_summary": data.get("executive_summary", "").strip(),
        "start_stop_continue": {
            "continue": list(ssc.get("continue", []) or []),
            "start": list(ssc.get("start", []) or []),
            "stop": list(ssc.get("stop", []) or []),
        },
        "analysis": data.get("analysis", "").strip(),
        "development_tips": dict(data.get("development_tips", {}) or {}),
        "ai_note": data.get("ai_note", "").strip(),
    }


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
                    "(không dùng AI). Khuyến nghị OD/HRBP rà soát và bổ sung nhận định trước khi dùng "
                    "trong coaching. Có thể thay thế bằng nội dung Claude qua file claude_content_*.json."),
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
