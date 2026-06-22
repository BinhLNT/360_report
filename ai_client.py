# -*- coding: utf-8 -*-
"""
ai_client.py
============
Lớp gọi LLM DÙNG CHUNG cho mọi tính năng AI của hệ thống 360°
(ai_engine = tự động điền, ai_qa = trợ lý hỏi-đáp, ai_review = kiểm chứng).

Thiết kế:
  * Dùng OpenAI Python SDK (tương thích cả endpoint OpenAI-compatible phục vụ
    model open-weight như gpt-oss-120b: Groq/Together/OpenRouter/vLLM/Ollama…).
  * Cấu hình đọc từ .env: OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL,
    AI_TEMPERATURE, AI_MAX_WORKERS.
  * Bền bỉ với khác biệt giữa các nhà cung cấp: tự động bỏ tham số không được hỗ
    trợ (response_format / temperature / max_tokens) rồi gọi lại.
  * Theo dõi token đã dùng (observability) — phục vụ phần "chi phí" khi demo.

KHÔNG có key vẫn import được; chỉ khi GỌI mới báo lỗi rõ ràng (để hệ thống chạy
offline với đường rule-based vẫn ổn).
"""

import json
import re
import os
import threading

try:
    from dotenv import load_dotenv
    load_dotenv()                       # nạp .env ở thư mục dự án (nếu có)
except Exception:                        # noqa: BLE001 — thiếu python-dotenv không được làm vỡ import
    def load_dotenv(*_a, **_k):          # type: ignore
        return False

_CLIENT = None
_CLIENT_KEY = None                       # (api_key, base_url) đã dùng để dựng client
_LOCK = threading.Lock()

# Bộ đếm token tích luỹ toàn phiên (quan sát chi phí).
USAGE = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------
def _float_env(name, default):
    try:
        return float(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


def _int_env(name, default):
    try:
        return int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


def settings():
    """Đọc cấu hình hiện tại từ biến môi trường (đã nạp từ .env)."""
    return {
        "api_key": (os.getenv("OPENAI_API_KEY", "") or "").strip(),
        "base_url": (os.getenv("OPENAI_BASE_URL", "") or "").strip() or None,
        "model": (os.getenv("OPENAI_MODEL", "") or "gpt-oss-120b").strip(),
        "temperature": _float_env("AI_TEMPERATURE", 0.4),
        "max_workers": max(1, _int_env("AI_MAX_WORKERS", 4)),
        # Ghi đè reasoning effort cho MỌI lệnh gọi (low/medium/high). Để TRỐNG ->
        # dùng mức mặc định theo từng tác vụ (autofill=low, hỏi-đáp=medium...).
        "reasoning_effort": (os.getenv("OPENAI_REASONING_EFFORT", "") or "").strip() or None,
    }


def is_configured():
    """True nếu đã có API key (tính năng AI sẵn sàng gọi thật)."""
    return bool(settings()["api_key"])


def model_label():
    cfg = settings()
    where = cfg["base_url"] or "api.openai.com"
    return f"{cfg['model']} @ {where}"


def reload_env():
    """Nạp lại .env và xoá client cache — để đổi key/model không cần khởi động lại."""
    global _CLIENT, _CLIENT_KEY
    load_dotenv(override=True)
    with _LOCK:
        _CLIENT = None
        _CLIENT_KEY = None


def get_client():
    """Trả về OpenAI client (lazy, có cache). Ném RuntimeError nếu chưa có key."""
    global _CLIENT, _CLIENT_KEY
    cfg = settings()
    if not cfg["api_key"]:
        raise RuntimeError(
            "Chưa cấu hình API key cho AI. Hãy mở file .env và điền OPENAI_API_KEY "
            "(và OPENAI_BASE_URL nếu dùng nhà cung cấp khác cho gpt-oss-120b), "
            "rồi khởi động lại server."
        )
    key = (cfg["api_key"], cfg["base_url"])
    with _LOCK:
        if _CLIENT is None or _CLIENT_KEY != key:
            from openai import OpenAI            # import trễ: không có openai cũng import module này được
            kwargs = {"api_key": cfg["api_key"]}
            if cfg["base_url"]:
                kwargs["base_url"] = cfg["base_url"]
            _CLIENT = OpenAI(**kwargs)
            _CLIENT_KEY = key
        return _CLIENT


def usage_snapshot():
    """Bản sao bộ đếm token (để hiển thị/đối soát chi phí)."""
    return dict(USAGE)


def reset_usage():
    USAGE.update(calls=0, prompt_tokens=0, completion_tokens=0, total_tokens=0)


def _track(resp):
    u = getattr(resp, "usage", None)
    USAGE["calls"] += 1
    if u is not None:
        USAGE["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
        USAGE["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
        USAGE["total_tokens"] += getattr(u, "total_tokens", 0) or 0


# ---------------------------------------------------------------------------
# Gọi chat completion (lõi)
# ---------------------------------------------------------------------------
def chat(messages, *, temperature=None, max_tokens=None, response_format=None,
         tools=None, tool_choice=None, model=None, reasoning_effort=None):
    """
    Gọi chat.completions.create và trả về đối tượng response gốc (để đọc cả
    tool_calls khi cần). Tự động bỏ tham số tuỳ chọn mà nhà cung cấp không hỗ trợ.

    reasoning_effort: 'low'|'medium'|'high' cho model suy luận (gpt-oss). Env
    OPENAI_REASONING_EFFORT (nếu đặt) GHI ĐÈ giá trị truyền vào đây.
    """
    cfg = settings()
    client = get_client()
    kwargs = {"model": model or cfg["model"], "messages": messages}
    if temperature is None:
        temperature = cfg["temperature"]
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    # Reasoning effort: env ghi đè per-call; gửi theo cú pháp hợp nhất của OpenRouter.
    effort = cfg["reasoning_effort"] or reasoning_effort
    if effort:
        kwargs["extra_body"] = {"reasoning": {"effort": effort}}

    droppable = ["response_format", "extra_body", "max_tokens", "temperature"]  # bỏ dần khi bị từ chối
    attempts = 0
    while True:
        attempts += 1
        try:
            resp = client.chat.completions.create(**kwargs)
            _track(resp)
            return resp
        except Exception as exc:                  # noqa: BLE001
            msg = str(exc).lower()
            dropped = False
            for k in droppable:
                if k in kwargs and (k in msg or (k == "extra_body" and "reasoning" in msg)):
                    kwargs.pop(k)
                    dropped = True
                    break
            # Nhà cung cấp từ chối JSON mode chung chung -> bỏ response_format.
            if not dropped and "response_format" in kwargs and \
                    any(t in msg for t in ("json", "response_format", "unsupported", "not support", "400")):
                kwargs.pop("response_format")
                dropped = True
            if dropped and attempts <= 5:
                continue
            raise


def message_text(resp):
    """Lấy phần văn bản câu trả lời (bỏ qua kênh reasoning của gpt-oss)."""
    try:
        return (resp.choices[0].message.content or "").strip()
    except (AttributeError, IndexError):
        return ""


def chat_text(messages, **kw):
    return message_text(chat(messages, **kw))


def chat_json(messages, **kw):
    """Gọi LLM và parse JSON từ câu trả lời (có sửa lỗi nhẹ: bóc ``` và rác bao quanh)."""
    kw.setdefault("response_format", {"type": "json_object"})
    text = chat_text(messages, **kw)
    return loads_json(text)


# ---------------------------------------------------------------------------
# Trích & parse JSON an toàn
# ---------------------------------------------------------------------------
def _strip_code_fence(text):
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def loads_json(text):
    """Parse JSON từ chuỗi LLM trả về. Thử nguyên văn -> bóc fence -> tìm object/array."""
    t = _strip_code_fence(text)
    if not t:
        raise ValueError("LLM trả về rỗng.")
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # Tìm object {...} hoặc array [...] đầu tiên cân bằng ngoặc.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = t.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(t)):
            c = t[i]
            if c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError("Không tìm thấy JSON hợp lệ trong câu trả lời của LLM.")
