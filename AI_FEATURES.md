# Tính năng AI (LLM / Agent) — Hệ thống Báo cáo 360°

Tài liệu này mô tả phần **AI Engineer** của sản phẩm: ba tính năng dùng LLM thật,
kiến trúc, và **điểm nói khi phỏng vấn**. Trước đây "AI" chỉ là quy trình thủ công
(sinh prompt → dán sang chatbot → tải CSV về → nạp lại). Nay sản phẩm **gọi trực
tiếp LLM** và bổ sung agent + guardrail.

> Provider: **OpenAI-compatible SDK** (`openai`), model **`gpt-oss-120b`**.
> Cấu hình trong `.env`. Thiết lập đang dùng = **OpenRouter**:
> ```
> OPENAI_API_KEY=sk-or-v1-...
> OPENAI_MODEL=openai/gpt-oss-120b      # OpenRouter BẮT BUỘC tiền tố "openai/"
> OPENAI_BASE_URL=https://openrouter.ai/api/v1
> OPENAI_REASONING_EFFORT=              # trống = mặc định theo tác vụ (điền=low, hỏi-đáp=medium)
> ```
> `gpt-oss-120b` là model open-weight; `api.openai.com` KHÔNG phục vụ nó → phải trỏ
> `OPENAI_BASE_URL` tới nhà cung cấp serve gpt-oss (OpenRouter/Groq/Together/vLLM…).

---

## Kiến trúc

```
            ┌───────────────── ai_client.py ─────────────────┐
            │ OpenAI SDK · đọc .env · chat()/chat_json()      │
            │ tự bỏ tham số provider không hỗ trợ · đếm token │
            └───────┬──────────────┬───────────────┬─────────┘
                    │              │               │
        ai_engine.py (A)     ai_qa.py (B)     ai_review.py (C)
        tự động điền 16      agent hỏi-đáp     kiểm chứng grounding
        trường → File 4      (tool use)        (rule + LLM-judge)
                    │              │               │
                    └──── webapp.py (Flask routes + dashboard) ────┘
```

Dữ liệu đầu vào của AI là **structured data** sẵn có (điểm số, hành vi, ý kiến) →
LLM **không bao giờ** thấy dữ liệu thô; nó chỉ nhận ngữ cảnh số liệu đã chắt lọc
(grounding) hoặc tự truy vấn qua công cụ.

| Module | Vai trò |
|---|---|
| `ai_client.py` | Lớp gọi LLM dùng chung: cấu hình `.env`, `chat()/chat_json()`, parse JSON an toàn, **tự bỏ** `response_format`/`temperature`/`reasoning` nếu provider từ chối, **đếm token** (observability). |
| `structured_from_file4.py` | **Đọc ngược File thứ 4** (ma trận điểm 24 hành vi × 4 khối + ý kiến) → dựng lại structured grounding. Nhờ đó File thứ 4 là **đầu vào ĐỘC LẬP** (không cần file Chi tiết gốc). Tái dùng `score_calculator.top_bottom_behaviors`/`biggest_gaps` + `structured_data._make_badge` để nhất quán. |
| `ai_engine.py` | **(A)** Sinh 16 trường nhận xét cho mỗi NV → CSV (`ma_nv` + 16 cột) → ghép vào File thứ 4 bằng `merge_ai_csv` có sẵn. Có đường **offline rule-based**. |
| `ai_qa.py` | **(B)** Agent hỏi-đáp HR: 4 công cụ (`filter_employees`, `get_employee`, `aggregate`, `rank_employees`) + vòng lặp tool-calling. |
| `ai_review.py` | **(C)** Kiểm chứng: kiểm tra theo luật (enum, nhất quán nhãn↔điểm, **phát hiện số bịa**) + **LLM-as-judge** chấm grounding 0–1. |

---

## (A) Tự động điền nội dung AI — `ai_engine.py`

**Vòng lặp File thứ 4 độc lập:** Bước 1 tạo File 4 (có cột điểm + 16 cột AI trống) →
Bước 2 upload File 4 → `structured_from_file4` đọc điểm + ý kiến **NGAY TRONG File 4**
để dựng ngữ cảnh grounding (không cần file Chi tiết gốc) → LLM trả **JSON 16 trường**
→ chuẩn hoá + **ràng buộc enum** → ghi thẳng vào 16 cột AI của File 4 (`merge_ai_csv`)
→ tải về **đúng File 4 đó**, giờ các cột AI đã có nội dung.

> Đã kiểm chứng: structured đọc-ngược-từ-File-4 cho tổng điểm/xếp loại/top-bottom
> **khớp tuyệt đối** bản tính từ Chi tiết (điểm theo nhóm xấp xỉ ≤0.11 vì File 4 chỉ
> lưu điểm hành vi, không lưu điểm rater có trọng số 30/70 — không ảnh hưởng nhận xét).

**Điểm nói phỏng vấn:**
- *Structured output*: ép JSON schema 16 khoá, parse + sửa lỗi, snap enum về giá trị hợp lệ.
- *Grounding chống bịa*: prompt chỉ chứa số liệu thật + ý kiến nguyên văn; nguyên tắc "không bịa".
- *Xử lý hàng loạt*: `ThreadPoolExecutor` (`AI_MAX_WORKERS`), gom lỗi từng người không làm hỏng cả lô.
- *Tương thích nhà cung cấp*: tự hạ cấp tham số khi endpoint không hỗ trợ.
- *Tích hợp không phá vỡ*: tái dùng đúng đường merge CSV cũ → không đụng pipeline báo cáo.

- *Lưới an toàn (hybrid)*: trường nào LLM để trống được đắp bằng nội dung rule-based từ số liệu → báo cáo **luôn đủ 16 trường**.
- *Resume/idempotent*: tuỳ chọn **`only_missing`** bỏ qua người đã có nội dung Ai (chạy lại không trả tiền lại).

API: `POST /api/ai-autofill` `{ma_list?, only_missing?}` (chạy nền, có progress bar; nguồn grounding = File thứ 4 trên hệ thống).

## (B) Trợ lý hỏi-đáp HR (Agent + tool use) — `ai_qa.py`

LLM **không bị nhồi 203 NV vào prompt**. Thay vào đó nó gọi công cụ truy vấn dữ
liệu thật trong bộ nhớ, hệ thống thực thi cục bộ rồi trả kết quả — lặp tới khi đủ
thông tin. Trả về kèm **"vết" công cụ** để minh bạch.

**Điểm nói phỏng vấn:**
- *Function calling / agentic loop*: định nghĩa schema công cụ, vòng lặp `tool_calls` → thực thi → trả `role:"tool"`.
- *Co giãn & chính xác*: chỉ kéo đúng dữ liệu model cần; không vượt context; không bịa.
- *Quan sát được*: hiển thị chuỗi công cụ đã dùng (`filter_employees → rank_employees …`).

API: `POST /api/ai-ask` `{question}` → `{answer, trace, steps, usage}`.

## (C) Kiểm chứng chất lượng (Guardrail) — `ai_review.py`

Hai lớp: **(1) Rule-based** (tất định) — đủ trường, enum hợp lệ, nhãn nhân tài có
nhất quán với tổng điểm không, và **đối chiếu mọi số thập phân** trong văn bản với
tập số liệu thật để bắt số bịa. **(2) LLM-as-judge** — một lượt gọi model độc lập
chấm `grounded`/`score`/`issues`.

**Điểm nói phỏng vấn:**
- *Evaluation & anti-hallucination*: không chỉ sinh mà còn **đo lường & chốt chặn** chất lượng.
- *Defense-in-depth*: luật rẻ + tất định kết hợp LLM-judge bắt lỗi ngữ nghĩa.
- *Số khớp đúng 2 chữ số thập phân* → bắt được điểm/nhãn bịa thực sự.

API: `GET /api/ai-review/<ma_nv>` → `{rule, judge, verdict}`.

---

## Tối ưu tốc độ & chi phí (quy mô 500+ NV)

> **Lưu ý:** OpenAI **Batch API** (giảm 50%) là tính năng riêng của api.openai.com,
> **không dùng được qua OpenRouter** (cũng như đa số gateway). Vì vậy ta dùng các
> đòn bẩy thực sự hiệu quả cho gpt-oss/OpenRouter:

| Đòn bẩy | Cơ chế | Hiệu quả đo được |
|---|---|---|
| **Reasoning effort = low** | gpt-oss là model suy luận; mặc định "ngẫm" rất nhiều. Đặt effort thấp cho tác vụ điền trường (qua `extra_body.reasoning.effort`). | **~41s → ~11s / người** (≈ 4×), cắt mạnh output token. 500 NV / 4 luồng ≈ ~22 phút. |
| **`only_missing`** | Bỏ qua người đã có nội dung AI khi chạy lại | Không trả tiền lại cho người cũ; điền tăng dần an toàn |
| **Xử lý song song** | `ThreadPoolExecutor(AI_MAX_WORKERS)` | Giảm wall-clock tuyến tính theo số luồng |
| **Observability token** | `ai_client.USAGE` cộng dồn prompt/completion token | Hiển thị ngay trên dashboard để theo dõi chi phí |
| **Tự hạ cấp tham số** | `chat()` bỏ `reasoning`/`response_format`/`temperature` nếu provider 400 | Một code-path chạy được trên nhiều nhà cung cấp |

Điều chỉnh: đặt `OPENAI_REASONING_EFFORT=low|medium|high` trong `.env` để ép mức suy
luận cho mọi lệnh gọi (ghi đè mặc định theo tác vụ).

## Cấu hình & chạy

1. Copy `.env.example` → `.env`, điền `OPENAI_API_KEY` (và `OPENAI_BASE_URL` nếu
   `gpt-oss-120b` phục vụ qua nhà cung cấp khác api.openai.com).
2. `pip install -r requirements.txt` (đã thêm `openai`, `python-dotenv`).
3. Chạy `webapp.py` → dashboard:
   - **Bước 2 → "Cách C — Tự động bằng AI"**: nút *Tự điền AI (toàn bộ)* / *Người đã chọn* / *Điền nhanh (offline)*.
   - **Card "Trợ lý hỏi-đáp AI"**: gõ câu hỏi tiếng Việt.
   - **Bảng NV → "🔎 Kiểm chứng"**: soi nội dung AI của từng người.

> Chưa có khoá API? Tính năng (A) vẫn chạy bằng nút **offline (rule-based)**; (B)/(C)
> cần khoá để gọi LLM. Badge trạng thái AI hiển thị ngay trên dashboard.

## Bảo mật
- `.env` đã được `.gitignore` (không commit khoá). Chỉ commit `.env.example`.
- LLM chỉ nhận số liệu đã chắt lọc/ẩn danh theo nhóm — không gửi dữ liệu thô.
