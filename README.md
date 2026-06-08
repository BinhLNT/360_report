# Hệ thống tạo Báo cáo Đánh giá 360°

Tự động hoá việc tạo **báo cáo đánh giá 360°** từ 2 file CSV raw: tính điểm,
xuất file tổng hợp, sinh prompt cho Claude, vẽ biểu đồ và render báo cáo
**HTML/PDF** giao diện cao cấp.

> **Không gọi bất kỳ AI API nào trong code.** Phần văn bản định tính do Claude sinh
> ra *ngoài* hệ thống (qua prompt được tạo sẵn); hệ thống chỉ *ghép* nội dung đó vào
> báo cáo. Nếu chưa có nội dung Claude, hệ thống tự sinh nội dung mặc định theo luật.

---

## 1. Cài đặt

```bash
# (đã có sẵn môi trường ảo .venv)
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Thư viện dùng: `pandas`, `jinja2`, `matplotlib`, `weasyprint` (+ stdlib:
`base64, io, os, datetime, csv, json, argparse, unicodedata, http.server`).

> **PDF trên Windows:** WeasyPrint cần thư viện GTK3/Pango native. Nếu chưa cài,
> hệ thống **vẫn xuất `.html`** bình thường và chỉ bỏ qua `.pdf` kèm cảnh báo. Cài
> GTK3 Runtime: <https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases>

---

## 2. Cách dùng nhanh

### Cách A — Giao diện web (khuyến nghị, đúng quy trình)
```bash
.venv\Scripts\python.exe webapp.py
```
Mở trình duyệt: **http://127.0.0.1:8000**. Giao diện chia thành **3 bước**:

1. **Tải lên 2 file CSV** — người dùng tự **tải lên** file Chi tiết + file Tổng hợp ngay
   trên trình duyệt. Hệ thống đọc và liệt kê nhân viên để chọn (không dùng dữ liệu làm sẵn).
2. **Xuất CSV tổng hợp + prompt** — chọn mã nhân viên. Hệ thống tính điểm, xuất
   `Tong-hop-raw_<MaNV>.csv` + `prompt_<MaNV>.txt`, rồi **hiện sẵn prompt kèm nút Copy**
   để bạn dán sang Claude.
3. **Dán kết quả Claude → Báo cáo** — sau khi Claude trả về JSON, **dán JSON đó vào ô** →
   bấm *Ghép nội dung Claude → Tạo báo cáo*. Hệ thống ghép vào template và hiển thị báo cáo
   ngay trong trang, kèm nút tải HTML / CSV / JSON / PDF.

   > Chưa có file để thử? Bấm *Tạo dữ liệu mẫu*. &nbsp; Chưa có Claude? Bấm
   > *Xem nhanh (nội dung mặc định)* — hệ thống tự sinh phần định tính theo luật từ số liệu.

### Cách B — Dòng lệnh (CLI)
```bash
# Tạo dữ liệu mẫu (tùy chọn, để demo)
.venv\Scripts\python.exe data\make_sample_data.py

# Tạo báo cáo cho 1 nhân viên
.venv\Scripts\python.exe main.py --ma-nv 015
```
Tham số CLI:
| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `--ma-nv` | Mã nhân viên (bắt buộc) | — |
| `--data-dir` | Thư mục chứa 2 file CSV raw | `data` |
| `--out-dir` | Thư mục xuất kết quả | `output` |
| `--content` | File JSON nội dung từ Claude | tự tìm `output/claude_content_<MaNV>.json` |
| `--report-date` | Ngày báo cáo dd/mm/yyyy | hôm nay |

---

## 3. Dữ liệu đầu vào

Hệ thống cần đúng 2 file CSV:
- `360 data raw(Chi tiet-raw).csv` — chi tiết điểm theo từng tiêu chí, từng người đánh giá.
- `360 data raw(Tong-hop-raw).csv` — metadata + ý kiến chung (dùng làm khung format khi xuất).

- **Giao diện web:** người dùng **tải lên** 2 file ở Bước 1; hệ thống tự lưu vào `data/`.
- **CLI:** đặt 2 file vào thư mục `data/` (đổi tên trong `config.py` nếu cần).

Hệ thống tự dò dòng header (chịu được dòng "banner" phía trên) và đọc cột **theo vị trí**
để an toàn với các cột trùng tên.

---

## 4. Kết quả đầu ra (`output/`)

| File | Mô tả |
|---|---|
| `Tong-hop-raw_<MaNV>.csv` | File tổng hợp **giữ đúng format gốc**, ghi đè 4 cột điểm + trạng thái + ý kiến đã tính lại |
| `structured_<MaNV>.json` | Toàn bộ số liệu đã tính (nguồn dữ liệu cho template & prompt) |
| `prompt_<MaNV>.txt` | Prompt chi tiết để đưa cho Claude sinh phần văn bản định tính |
| `BAOCAO_<MaNV>.html` | Báo cáo hoàn chỉnh (mở bằng trình duyệt) |
| `BAOCAO_<MaNV>.pdf` | Bản PDF (nếu môi trường có GTK) |

---

## 5. Quy trình kết hợp Claude (2 bước)

**Trên giao diện web (dễ nhất):** làm theo 2 bước ở mục 2A — Bước 1 sinh prompt, Bước 2
dán JSON Claude trả về vào ô có sẵn. Không cần tạo file thủ công.

**Trên dòng lệnh:**
1. `python main.py --ma-nv <MaNV>` (hoặc gọi `main.prepare(...)`) → có `output/prompt_<MaNV>.txt`.
2. Dán prompt cho **Claude** → Claude trả về 1 object JSON.
3. Lưu JSON đó vào `output/claude_content_<MaNV>.json`.
4. Chạy lại `main.py --ma-nv <MaNV>` → báo cáo dùng nội dung Claude (thay nội dung mặc định).

> Về kiến trúc, pipeline được tách 2 hàm: `main.prepare()` (đọc → tính → xuất CSV +
> prompt) và `main.finalize()` (ghép nội dung → render). `main.run()` chạy gộp cả hai cho
> CLI một phát. Giao diện web gọi `prepare()` ở Bước 1 và `finalize()` ở Bước 2.

Schema JSON: xem cuối file prompt sinh ra.

---

## 6. Công thức tính điểm

```
Điểm 1 nhóm (Phẩm chất/Năng lực) = Σ(ĐIỂM × Hệ số) / Σ(Hệ số)
Điểm 1 người đánh giá           = (30 × Phẩm chất + 70 × Năng lực) / 100
Điểm 1 nhóm quan hệ             = trung bình điểm những người ĐÃ ĐÁNH GIÁ trong nhóm
Tổng 360°                       = trung bình các nhóm quan hệ CÓ dữ liệu
```
Đã đối chiếu khớp 100% với số liệu mẫu: Đồng cấp `3.9125`, Cấp dưới `4.24307598`,
Tổng `4.07778799`.

---

## 7. Cấu trúc mã nguồn (modular)

| File | Vai trò |
|---|---|
| `config.py` | Toàn bộ hằng số: tên file, trọng số, mapping tiêu chí, ngưỡng, thư viện tips |
| `data_loader.py` | Đọc 2 file CSV (xử lý BOM, banner, cột trùng tên) |
| `score_calculator.py` | **Lõi tính điểm** 360° + phân loại tiêu chí, top/bottom, gap |
| `structured_data.py` | Lắp ráp structured data (nguồn sự thật duy nhất) |
| `tonghop_exporter.py` | Xuất `Tong-hop-raw_<MaNV>.csv` đúng format gốc (theo vị trí) |
| `prompt_generator.py` | Sinh `prompt_<MaNV>.txt` cho Claude |
| `content_provider.py` | Nạp nội dung Claude (JSON) hoặc sinh nội dung mặc định theo luật |
| `chart_generator.py` | Vẽ 4 biểu đồ matplotlib → base64 |
| `report_renderer.py` | Render HTML (Jinja2) + xuất PDF (WeasyPrint, có fallback) |
| `templates/report_template.html` | Template báo cáo (Jinja2) |
| `main.py` | Điểm vào CLI, điều phối toàn bộ pipeline |
| `webapp.py` | Giao diện web test (stdlib `http.server` + Jinja2) |
| `data/make_sample_data.py` | Tiện ích sinh dữ liệu mẫu để demo |
