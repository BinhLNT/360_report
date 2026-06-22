# Hệ thống Báo cáo Đánh giá 360° (chế độ Batch)

Tự động hoá đánh giá 360° ở **quy mô lớn (500+ nhân viên)**: tính điểm từ dữ liệu
thô → sinh **"File thứ 4"** (Excel) để AI điền nhận xét + người duyệt rà soát →
xuất **báo cáo PDF hàng loạt** theo template, có **bộ lọc**.

> **Tích hợp AI (LLM/Agent) — xem [`AI_FEATURES.md`](AI_FEATURES.md).** Hệ thống có
> 3 tính năng AI thật, gọi trực tiếp LLM (OpenAI-compatible, mặc định `gpt-oss-120b`):
> **(A)** tự động điền 16 trường nhận xét vào "File thứ 4"; **(B)** trợ lý hỏi-đáp HR
> (agent + tool use); **(C)** kiểm chứng nội dung AI bám số liệu (guardrail chống ảo
> giác). Cấu hình khoá API trong `.env` (xem `.env.example`). Khi chưa có khoá, hệ
> thống vẫn chạy đầy đủ ở chế độ rule-based (offline).

---

## 1. Cài đặt

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium     # tải Chromium 1 lần (xuất PDF)
```

Thư viện chính: `pandas`, `openpyxl`, `jinja2`, `matplotlib`, `playwright`.

---

## 2. Dữ liệu đầu vào (`data/`)

3 file (CSV **UTF-8**), đặt tên theo `config.INPUT_*`:

| File | Vai trò |
|---|---|
| `...(Chi tiet).csv` | Chi tiết: 1 dòng / tiêu chí / người đánh giá. **Nguồn tính điểm.** |
| `...(Tong hop).csv` | Tổng hợp: metadata + ý kiến chung |
| `...(Tong hop tieu chi).csv` | Điểm theo từng hành vi × nhóm rater (tham chiếu) |

> Lưu file thẳng vào `data/` (đọc trực tiếp từ đĩa — không giới hạn dung lượng,
> file ~20MB chạy ~17s). Khi xuất từ Excel, chọn **"CSV UTF-8"** để không vỡ dấu.

---

## 3. Giao diện web (khuyến nghị — trực quan, không cần gõ lệnh)

```bash
.venv\Scripts\python.exe webapp.py
```
Mở trình duyệt: **http://127.0.0.1:8000**. Trên dashboard:
1. **Bước 1** — bấm *“Tính điểm & Sinh File thứ 4”* (có thanh tiến độ); tải về File thứ 4.
2. **Bước 2** — bấm *“🤖 Tự điền AI”* để AI tự điền 16 cột nhận xét (xem [AI_FEATURES.md](AI_FEATURES.md)). Rà soát/duyệt là **tuỳ chọn**: sửa trong Excel + đặt “Đã duyệt” rồi *Tải lên File thứ 4 đã duyệt*.
3. **Bước 3** — chọn **bộ lọc** (Bộ phận / Cấp bậc / Xếp loại / Chức danh / chỉ Đã duyệt) → bảng nhân viên lọc trực tiếp → bấm *“Xuất báo cáo PDF”* → xem/tải PDF (hoặc tải toàn bộ .zip).

Bấm *“Xem thử”* trên từng dòng để xem nhanh báo cáo ngay cả khi chưa xuất PDF.

## 4. Quy trình bằng dòng lệnh (CLI)

### Bước 1 — Sinh "File thứ 4"
```bash
.venv\Scripts\python.exe batch_main.py
```
Tạo `output/360_AI_input_full.xlsx` — **File thứ 4**: định danh + KẾT QUẢ + ma trận
24 hành vi × 4 khối rater (TỔNG / Cấp trên / Đồng nghiệp / Cấp dưới) + Khuyến nghị
+ **16 cột AI** (trống) + 4 cột rà soát.

→ Điền 16 cột AI bằng **AI tự động** (chạy `webapp.py`, nút *“Tự điền AI”* — xem
[AI_FEATURES.md](AI_FEATURES.md)); rồi rà soát, đặt **Trạng thái rà soát = "Đã duyệt"**.

### Bước 2 — Xuất báo cáo PDF hàng loạt (có bộ lọc)
```bash
.venv\Scripts\python.exe batch_report.py                      # tất cả
.venv\Scripts\python.exe batch_report.py --cap-bac T2 --rating "Tốt,Xuất sắc"
.venv\Scripts\python.exe batch_report.py --bo-phan "Khối Công nghệ" --only-approved
.venv\Scripts\python.exe batch_report.py --no-pdf --limit 5   # xem nhanh HTML
```
Kết quả: `output/reports/BAOCAO_<MaNV>.pdf` (+ `.html`) và `_index.csv`.

**Bộ lọc:** `--bo-phan` · `--chuc-danh` · `--cap-bac` · `--rating` · `--only-approved`
(khớp chuỗi con, không phân biệt dấu; nhiều giá trị ngăn bằng `,`).
*(Manager/Team chưa hỗ trợ — không có cột nguồn trong dữ liệu.)*

---

## 5. Công thức tính điểm

```
Điểm 1 người đánh giá = (30 × Phẩm chất + 70 × Năng lực) / 100
Điểm 1 nhóm quan hệ   = trung bình điểm người ĐÃ HOÀN THÀNH trong nhóm
Tổng 360°             = trung bình các nhóm quan hệ CÓ dữ liệu  (thang 1–5)
```
Trạng thái "đã xong" nhận cả **"Đã đánh giá"** và **"Hoàn thành"**. Điểm tính từ
Chi tiết đã đối chiếu khớp 100% với file "Tổng hợp tiêu chí".

---

## 6. Cấu trúc mã nguồn

| File | Vai trò |
|---|---|
| `config.py` | Hằng số: tên file, trọng số, 10 nhóm + 24 hành vi, cột File thứ 4, ngưỡng |
| `data_loader.py` | Đọc CSV theo VỊ TRÍ cột (chịu banner + cột trùng tên) |
| `score_calculator.py` | **Lõi tính điểm** 360° + phân loại tiêu chí (khớp tiền tố) |
| `structured_data.py` | Lắp structured data cho 1 nhân viên |
| `batch_builder.py` | Tính điểm toàn bộ NV + sinh File thứ 4 (qua competency_exporter) |
| `competency_exporter.py` | Sinh "File thứ 4" (Excel wide, bám format gốc) |
| `file4_reader.py` | Đọc ngược File thứ 4 (nội dung AI + trạng thái duyệt) |
| `report_content.py` | Map cột AI → nội dung template (fallback mặc định theo luật) |
| `content_provider.py` | Sinh nội dung định tính mặc định theo luật |
| `chart_generator.py` | 4 biểu đồ matplotlib → base64 |
| `report_renderer.py` | Render HTML (Jinja2) |
| `pdf_playwright.py` | HTML → PDF (headless Chromium, mở 1 lần cho cả lô) |
| `batch_main.py` | CLI Bước 1 |
| `batch_report.py` | CLI Bước 2 (render hàng loạt + bộ lọc) |
| `webapp.py` | **Giao diện web (Flask)** — dashboard điều khiển toàn bộ quy trình |
| `ai_client.py` | Lớp gọi LLM dùng chung (OpenAI-compatible) — xem [AI_FEATURES.md](AI_FEATURES.md) |
| `ai_engine.py` | **AI tự động điền** 16 cột nhận xét vào File thứ 4 |
| `ai_qa.py` | **Trợ lý hỏi-đáp HR** (agent + tool use) |
| `ai_review.py` | **Kiểm chứng** nội dung AI bám số liệu (guardrail) |
| `templates/report_template.html` | Template báo cáo (6 phần) |
| `templates/dashboard.html` | Giao diện dashboard |
| `utils.py` | Tiện ích chung |
