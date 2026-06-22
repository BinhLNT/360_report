# -*- coding: utf-8 -*-
"""
ai_review.py  —  TÍNH NĂNG C: KIỂM CHỨNG CHẤT LƯỢNG NỘI DUNG AI (GUARDRAIL)
==========================================================================
Trước khi nội dung AI được dùng trong báo cáo nhân sự, module này kiểm tra xem nó
có BÁM SÁT SỐ LIỆU không — chống "ảo giác" (hallucination) và mâu thuẫn.

Hai lớp kiểm chứng:
  1. RULE-BASED (tất định, không tốn API):
     - Đủ trường bắt buộc, enum hợp lệ.
     - Nhãn "nhóm nhân tài" / "mức sẵn sàng" có nhất quán với tổng điểm không.
     - Các CON SỐ điểm xuất hiện trong văn bản có khớp số liệu thật không
       (phát hiện số bịa).
  2. LLM-AS-JUDGE (khi có API): một lượt gọi model độc lập chấm điểm grounding
     0–1, liệt kê vấn đề và lý do — kiểu "đánh giá chéo".

Đây là phần thể hiện tư duy "AI Engineer production": có đo lường & chốt chặn
chất lượng, không chỉ sinh ra rồi dùng luôn.
"""

import re

import config
import ai_client
import ai_engine

# Ngưỡng nhất quán nhãn ↔ tổng điểm (nới lỏng để tránh báo động giả).
_NHAN_TAI_MIN = {"Ngôi sao": 4.2, "Tiềm năng cao": 3.8, "Vững vàng": 3.3, "Cần hỗ trợ": 0.0}
_NHAN_TAI_MAX = {"Ngôi sao": 5.01, "Tiềm năng cao": 5.01, "Vững vàng": 4.5, "Cần hỗ trợ": 3.9}

_DEC_RE = re.compile(r"\d+[.,]\d+")          # chỉ bắt SỐ THẬP PHÂN (điểm), bỏ qua "90 ngày"


# ---------------------------------------------------------------------------
# Thu thập "số liệu thật" để đối chiếu
# ---------------------------------------------------------------------------
def _known_numbers(structured):
    vals = set()

    def add(v):
        if isinstance(v, (int, float)):
            vals.add(round(float(v), config.DISPLAY_DECIMALS))

    add(structured.get("total_360"))
    for g in (structured.get("group_averages") or {}).values():
        add(g.get("score"))
    for s in structured.get("subcompetencies", []):
        for k in ("others", "cap_tren", "dong_cap", "cap_duoi"):
            add(s.get(k))
    for b in (structured.get("top5", []) + structured.get("bottom5", [])):
        add(b.get("score"))
    for g in structured.get("gaps", []):
        for k in ("a", "b", "delta"):
            add(g.get(k))
    return vals


def _check_numbers(fields, known):
    """Tìm số thập phân trong văn bản AI không khớp số liệu thật (nghi bịa).

    So khớp ĐÚNG tới DISPLAY_DECIMALS chữ số — vì cả số liệu thật lẫn số trong
    văn bản đều ở dạng 2 chữ số thập phân, khớp gần đúng sẽ làm guardrail vô nghĩa.
    """
    suspicious = []
    for key, text in fields.items():
        for m in _DEC_RE.findall(text or ""):
            try:
                num = round(float(m.replace(",", ".")), config.DISPLAY_DECIMALS)
            except ValueError:
                continue
            if num > 5.0:                    # ngoài thang điểm 360 (vd năm, %, số ngày) -> bỏ qua
                continue
            if num not in known:
                suspicious.append({"field": key, "value": m})
    return suspicious


# ---------------------------------------------------------------------------
# 1. Kiểm chứng RULE-BASED
# ---------------------------------------------------------------------------
def rule_check(structured, fields):
    checks = []

    def add(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    keys = ai_engine.field_keys()
    missing = [k for k in keys if not (fields.get(k) or "").strip()]
    add("Đủ 16 trường nội dung", not missing,
        ("Thiếu: " + ", ".join(missing)) if missing else "Đủ")

    san_sang = (fields.get("muc_do_san_sang_thang_tien") or "").strip()
    add("Enum 'mức sẵn sàng' hợp lệ", san_sang in ai_engine.ENUM_SAN_SANG,
        san_sang or "(trống)")
    nhan_tai = (fields.get("nhom_nhan_tai") or "").strip()
    add("Enum 'nhóm nhân tài' hợp lệ", nhan_tai in ai_engine.ENUM_NHAN_TAI,
        nhan_tai or "(trống)")

    total = structured.get("total_360")
    if total is not None and nhan_tai in _NHAN_TAI_MIN:
        ok = _NHAN_TAI_MIN[nhan_tai] <= total <= _NHAN_TAI_MAX[nhan_tai]
        add("Nhãn nhân tài nhất quán với tổng điểm", ok,
            f"{nhan_tai} ↔ tổng {total:.2f}")
    else:
        add("Nhãn nhân tài nhất quán với tổng điểm", True, "Bỏ qua (thiếu điểm)")

    suspicious = _check_numbers(fields, _known_numbers(structured))
    add("Không có số liệu lạ (nghi bịa)", not suspicious,
        ("Số nghi bịa: " + ", ".join(f"{s['value']}({s['field']})" for s in suspicious[:6]))
        if suspicious else "Các số đều khớp dữ liệu")

    passed = sum(1 for c in checks if c["passed"])
    return {
        "score": round(passed / len(checks), 2) if checks else 1.0,
        "passed": passed, "total": len(checks),
        "checks": checks,
        "suspicious_numbers": suspicious,
    }


# ---------------------------------------------------------------------------
# 2. LLM-AS-JUDGE (khi có API)
# ---------------------------------------------------------------------------
_JUDGE_SYSTEM = (
    "Bạn là giám định viên độc lập, kiểm tra xem một đoạn NHẬN XÉT do AI viết cho báo cáo "
    "đánh giá 360° có BÁM SÁT dữ liệu số được cung cấp không, có bịa đặt hay mâu thuẫn không. "
    "Chỉ căn cứ vào DỮ LIỆU và NHẬN XÉT được đưa ra. Trả về DUY NHẤT một JSON object với các khoá: "
    '"grounded" (true/false — nhận xét có hoàn toàn dựa trên dữ liệu không), '
    '"score" (số 0..1 — mức độ bám sát dữ liệu), '
    '"issues" (mảng chuỗi — các điểm bịa/mâu thuẫn/không có cơ sở; rỗng nếu không có), '
    '"rationale" (1-2 câu giải thích ngắn). Không kèm chữ nào ngoài JSON.'
)


def judge_check(structured, fields):
    """Chấm grounding bằng LLM. Trả về dict hoặc None nếu chưa cấu hình/ lỗi."""
    if not ai_client.is_configured():
        return None
    content_block = "\n".join(
        f"### {label}\n{fields.get(key,'').strip()}"
        for key, label, _d in config.AI_FIELDS
    )
    user = (
        "DỮ LIỆU SỐ (nguồn sự thật):\n\n"
        + ai_engine.build_employee_context(structured)
        + "\n\n============================\nNHẬN XÉT AI CẦN KIỂM CHỨNG:\n\n"
        + content_block
    )
    try:
        data = ai_client.chat_json(
            [{"role": "system", "content": _JUDGE_SYSTEM},
             {"role": "user", "content": user}],
            temperature=0.0, max_tokens=2500, reasoning_effort="low")
    except Exception as exc:                      # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(data, dict):
        return {"error": "LLM giám định không trả về JSON object."}
    return {
        "grounded": bool(data.get("grounded", False)),
        "score": _clamp01(data.get("score")),
        "issues": [str(x) for x in (data.get("issues") or [])][:10],
        "rationale": str(data.get("rationale", "")).strip(),
    }


def _clamp01(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Tổng hợp
# ---------------------------------------------------------------------------
def check(structured, fields, *, use_judge=True):
    """
    Kiểm chứng nội dung AI của 1 nhân viên. Trả về dict:
      {rule, judge, verdict:{ok, score, summary}}
    """
    rule = rule_check(structured, fields)
    judge = judge_check(structured, fields) if use_judge else None

    judge_ok = True
    parts = [f"Rule {rule['passed']}/{rule['total']}"]
    score = rule["score"]
    if judge and "error" not in judge:
        judge_ok = judge["grounded"] and (judge["score"] is None or judge["score"] >= 0.7)
        if judge["score"] is not None:
            score = round((rule["score"] + judge["score"]) / 2, 2)
            parts.append(f"Judge {judge['score']:.2f}")
        else:
            parts.append("Judge: " + ("đạt" if judge["grounded"] else "có vấn đề"))
    elif judge and "error" in judge:
        parts.append("Judge lỗi")

    ok = rule["score"] >= 0.8 and judge_ok
    summary = ("✅ Đạt — " if ok else "⚠️ Cần rà soát — ") + "; ".join(parts)
    return {"rule": rule, "judge": judge,
            "verdict": {"ok": ok, "score": score, "summary": summary}}
