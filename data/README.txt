THƯ MỤC DỮ LIỆU ĐẦU VÀO
=======================

Đặt 3 file CSV (UTF-8) vào đây, đặt tên khớp với config.INPUT_* :

  - ...(Chi tiet).csv             -> Chi tiết theo tiêu chí (NGUỒN tính điểm)
  - ...(Tong hop).csv             -> Tổng hợp metadata + ý kiến chung
  - ...(Tong hop tieu chi).csv    -> Điểm theo từng hành vi × nhóm rater (tham chiếu)

LƯU Ý:
  - Khi xuất từ Excel, chọn định dạng "CSV UTF-8 (Comma delimited)" để KHÔNG
    vỡ dấu tiếng Việt (tránh "CSV thường/ANSI" -> ra dấu '?').
  - File lớn (vài chục MB) cứ để thẳng vào đây; hệ thống đọc trực tiếp từ đĩa.

CHẠY:
  1) python batch_main.py     -> sinh output/360_AI_input_full.xlsx + prompt_chung.txt
  2) (điền cột AI + rà soát trong file Excel)
  3) python batch_report.py   -> xuất báo cáo PDF hàng loạt vào output/reports/
