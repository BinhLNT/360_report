THƯ MỤC DỮ LIỆU ĐẦU VÀO
=======================

Hệ thống cần 2 file CSV (xem tên chuẩn trong config.py):

  - 360 data raw(Chi tiet-raw).csv
  - 360 data raw(Tong-hop-raw).csv

CÓ 2 CÁCH ĐƯA DỮ LIỆU VÀO:

1) GIAO DIỆN WEB (khuyến nghị) — KHÔNG cần đặt file vào đây trước:
   python webapp.py   ->  http://127.0.0.1:8000
   Ở Bước 1, TẢI LÊN trực tiếp 2 file CSV; hệ thống sẽ tự lưu vào thư mục này.

2) DÒNG LỆNH — đặt sẵn 2 file vào thư mục này rồi chạy:
   python main.py --ma-nv 015

DEMO NHANH (chưa có file thật): sinh dữ liệu mẫu nhân viên 015:
   python data/make_sample_data.py
   (hoặc bấm "Tạo dữ liệu mẫu" trên giao diện web)
