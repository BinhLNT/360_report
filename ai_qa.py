# -*- coding: utf-8 -*-
"""
ai_qa.py  —  TÍNH NĂNG B: TRỢ LÝ HỎI-ĐÁP HR (AGENT + TOOL USE)
==============================================================
Một AGENT cho phép HR hỏi bằng ngôn ngữ tự nhiên trên dữ liệu 360° đã tính, ví dụ:
  "Ai có tiềm năng cao nhất phòng Kinh doanh?"
  "Điểm trung bình theo bộ phận?"   "So sánh top 5 và bottom 5."

Cơ chế (đúng kiểu AI Engineer): model KHÔNG được nhồi toàn bộ dữ liệu vào prompt.
Thay vào đó model gọi CÔNG CỤ (function calling) để TRUY VẤN dữ liệu thật trong
bộ nhớ, hệ thống thực thi rồi trả kết quả về — lặp tới khi model đủ thông tin trả
lời. Cách này: (1) chính xác, không bịa; (2) co giãn với 500+ NV; (3) minh bạch
(trả về cả "vết" các lệnh gọi công cụ để hiển thị).

Toàn bộ công cụ chạy CỤC BỘ trên structured_list — không gửi dữ liệu thô lên LLM
trừ những bản ghi model chủ động truy vấn.
"""

import json
import unicodedata

import ai_client

MAX_STEPS = 6                 # trần số vòng gọi công cụ cho mỗi câu hỏi


# ---------------------------------------------------------------------------
# Tiện ích dữ liệu
# ---------------------------------------------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower().strip()


def _rating(s):
    return (s.get("badge") or {}).get("label", "")


def _brief(s):
    e = s["employee"]
    return {
        "ma_nv": e["ma_nv"], "ho_ten": e["ho_ten"], "chuc_danh": e.get("chuc_danh", ""),
        "bo_phan": e.get("bo_phan", ""), "cap_bac": e.get("cap_bac", ""),
        "total_360": s.get("total_360"), "xep_loai": _rating(s),
    }


def _detail(s):
    d = _brief(s)
    ga = s.get("group_averages", {})
    d["diem_theo_nhom"] = {g.get("label", rel): g.get("score")
                           for rel, g in ga.items()}
    subs = [x for x in s.get("subcompetencies", []) if x.get("others") is not None]
    subs.sort(key=lambda x: x["others"], reverse=True)
    d["manh_nhat"] = [{"nhom": x["label"], "diem": x["others"]} for x in subs[:3]]
    d["yeu_nhat"] = [{"nhom": x["label"], "diem": x["others"]} for x in subs[-3:]]
    comments = s.get("all_comments") or []
    d["so_y_kien"] = len(comments)
    d["y_kien_mau"] = [f"[{c.get('rel','')}] {c.get('text','')}" for c in comments[:5]]
    comp = s.get("completion", {})
    d["hoan_thanh"] = f"{comp.get('completed',0)}/{comp.get('total',0)}"
    return d


# ---------------------------------------------------------------------------
# Các công cụ (thực thi cục bộ trên structured_list)
# ---------------------------------------------------------------------------
def _tool_filter_employees(sl, *, bo_phan=None, cap_bac=None, xep_loai=None,
                           chuc_danh=None, diem_toi_thieu=None, diem_toi_da=None, limit=50):
    out = []
    for s in sl:
        e = s["employee"]
        if bo_phan and _norm(bo_phan) not in _norm(e.get("bo_phan")):
            continue
        if cap_bac and _norm(cap_bac) not in _norm(e.get("cap_bac")):
            continue
        if chuc_danh and _norm(chuc_danh) not in _norm(e.get("chuc_danh")):
            continue
        if xep_loai and _norm(xep_loai) not in _norm(_rating(s)):
            continue
        t = s.get("total_360")
        if diem_toi_thieu is not None and (t is None or t < diem_toi_thieu):
            continue
        if diem_toi_da is not None and (t is None or t > diem_toi_da):
            continue
        out.append(_brief(s))
    out.sort(key=lambda x: (x["total_360"] is None, -(x["total_360"] or 0)))
    return {"count": len(out), "employees": out[:int(limit or 50)]}


def _tool_get_employee(sl, *, query):
    q = _norm(query)
    # Ưu tiên khớp đúng mã, rồi tới khớp tên (chứa).
    for s in sl:
        if _norm(s["employee"]["ma_nv"]) == q:
            return _detail(s)
    matches = [s for s in sl if q in _norm(s["employee"]["ho_ten"])]
    if not matches:
        return {"error": f"Không tìm thấy nhân viên khớp '{query}'."}
    if len(matches) > 1:
        return {"nhieu_ket_qua": [_brief(s) for s in matches[:10]],
                "ghi_chu": "Có nhiều người trùng; hãy hỏi rõ mã nhân viên."}
    return _detail(matches[0])


def _tool_aggregate(sl, *, group_by, metric="avg_score"):
    field = {"bo_phan": "bo_phan", "cap_bac": "cap_bac"}.get(group_by)
    groups = {}
    for s in sl:
        if group_by == "xep_loai":
            key = _rating(s) or "—"
        else:
            key = s["employee"].get(field, "") or "—"
        g = groups.setdefault(key, {"count": 0, "sum": 0.0, "n_score": 0})
        g["count"] += 1
        t = s.get("total_360")
        if t is not None:
            g["sum"] += t
            g["n_score"] += 1
    rows = []
    for key, g in groups.items():
        avg = round(g["sum"] / g["n_score"], 2) if g["n_score"] else None
        rows.append({"nhom": key, "so_nguoi": g["count"], "diem_tb": avg})
    rows.sort(key=lambda r: (r["diem_tb"] is None, -(r["diem_tb"] or 0))
              if metric == "avg_score" else (-r["so_nguoi"],))
    return {"group_by": group_by, "metric": metric, "rows": rows}


def _tool_rank_employees(sl, *, order="top", limit=5, bo_phan=None):
    pool = [s for s in sl if s.get("total_360") is not None]
    if bo_phan:
        pool = [s for s in pool if _norm(bo_phan) in _norm(s["employee"].get("bo_phan"))]
    pool.sort(key=lambda s: s["total_360"], reverse=(order != "bottom"))
    return {"order": order, "count_pool": len(pool),
            "employees": [_brief(s) for s in pool[:int(limit or 5)]]}


TOOLS_SPEC = [
    {"type": "function", "function": {
        "name": "filter_employees",
        "description": "Lọc/tra cứu danh sách nhân viên theo bộ phận, cấp bậc, chức danh, xếp loại, "
                       "khoảng điểm. Trả về danh sách tóm tắt đã sắp xếp theo điểm giảm dần.",
        "parameters": {"type": "object", "properties": {
            "bo_phan": {"type": "string"}, "cap_bac": {"type": "string"},
            "chuc_danh": {"type": "string"},
            "xep_loai": {"type": "string", "description": "vd: Xuất sắc, Tốt..."},
            "diem_toi_thieu": {"type": "number"}, "diem_toi_da": {"type": "number"},
            "limit": {"type": "integer", "description": "Số dòng tối đa (mặc định 50)."}},
            "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_employee",
        "description": "Lấy hồ sơ chi tiết MỘT nhân viên theo mã NV hoặc theo tên: điểm theo nhóm, "
                       "3 nhóm mạnh/yếu nhất, số ý kiến và vài ý kiến mẫu.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Mã nhân viên hoặc tên."}},
            "required": ["query"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "aggregate",
        "description": "Thống kê tổng hợp: đếm số người và điểm trung bình theo nhóm "
                       "(bộ phận / cấp bậc / xếp loại).",
        "parameters": {"type": "object", "properties": {
            "group_by": {"type": "string", "enum": ["bo_phan", "cap_bac", "xep_loai"]},
            "metric": {"type": "string", "enum": ["avg_score", "count"]}},
            "required": ["group_by"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "rank_employees",
        "description": "Xếp hạng nhân viên theo tổng điểm 360° (top hoặc bottom), có thể giới hạn "
                       "trong một bộ phận.",
        "parameters": {"type": "object", "properties": {
            "order": {"type": "string", "enum": ["top", "bottom"]},
            "limit": {"type": "integer"}, "bo_phan": {"type": "string"}},
            "additionalProperties": False}}},
]

_DISPATCH = {
    "filter_employees": _tool_filter_employees,
    "get_employee": _tool_get_employee,
    "aggregate": _tool_aggregate,
    "rank_employees": _tool_rank_employees,
}


def _system_prompt(n):
    return (
        "Bạn là trợ lý phân tích dữ liệu đánh giá 360° cho bộ phận Nhân sự. "
        f"Có {n} nhân viên trong dữ liệu. Hãy DÙNG CÁC CÔNG CỤ để truy vấn số liệu thật trước khi "
        "trả lời — TUYỆT ĐỐI KHÔNG bịa tên, điểm, hay con số. Có thể gọi nhiều công cụ nếu cần. "
        "Thang điểm 1.00–5.00. Trả lời bằng TIẾNG VIỆT, ngắn gọn, nêu rõ số liệu và tên/mã NV liên quan. "
        "Nếu công cụ không có dữ liệu, hãy nói rõ là không tìm thấy."
    )


# ---------------------------------------------------------------------------
# Vòng lặp agent
# ---------------------------------------------------------------------------
def answer(question, structured_list, *, max_steps=MAX_STEPS):
    """Trả lời câu hỏi HR bằng agent + tool use. Trả về dict {answer, trace, steps, usage}."""
    if not structured_list:
        return {"answer": "Chưa có dữ liệu nhân viên. Hãy chạy Bước 1 (tính điểm) trước.",
                "trace": [], "steps": 0, "usage": ai_client.usage_snapshot()}

    sl = structured_list
    messages = [
        {"role": "system", "content": _system_prompt(len(sl))},
        {"role": "user", "content": str(question or "").strip()},
    ]
    trace = []

    for step in range(1, max_steps + 1):
        resp = ai_client.chat(messages, tools=TOOLS_SPEC, tool_choice="auto",
                              temperature=0.2, reasoning_effort="medium")
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            return {"answer": (msg.content or "").strip(), "trace": trace,
                    "steps": step, "usage": ai_client.usage_snapshot()}

        # Ghi lại assistant turn (kèm tool_calls) vào lịch sử.
        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name,
                                         "arguments": tc.function.arguments}}
                           for tc in tool_calls],
        })

        # Thực thi từng công cụ và trả kết quả.
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            fn = _DISPATCH.get(name)
            if fn is None:
                result = {"error": f"Không có công cụ '{name}'."}
            else:
                try:
                    result = fn(sl, **args)
                except TypeError as exc:
                    result = {"error": f"Tham số không hợp lệ: {exc}"}
                except Exception as exc:               # noqa: BLE001
                    result = {"error": f"{type(exc).__name__}: {exc}"}
            trace.append({"tool": name, "args": args,
                          "summary": _summarize(name, result)})
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, ensure_ascii=False)})

    # Hết số vòng — chốt câu trả lời không dùng thêm công cụ.
    messages.append({"role": "user", "content":
                     "Hãy chốt câu trả lời ngắn gọn dựa trên dữ liệu đã truy vấn."})
    final = ai_client.chat_text(messages, temperature=0.2, reasoning_effort="medium")
    return {"answer": final.strip(), "trace": trace, "steps": max_steps,
            "usage": ai_client.usage_snapshot()}


def _summarize(name, result):
    if isinstance(result, dict):
        if "error" in result:
            return result["error"]
        if "count" in result:
            return f"{result['count']} kết quả"
        if "rows" in result:
            return f"{len(result['rows'])} nhóm"
        if "employees" in result:
            return f"{len(result['employees'])} người"
        if "ho_ten" in result:
            return result["ho_ten"]
    return "OK"
