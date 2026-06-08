# -*- coding: utf-8 -*-
"""
data/make_sample_data.py
========================
TIỆN ÍCH (tùy chọn) sinh 2 file CSV đầu vào mẫu để demo/kiểm thử hệ thống.

Dữ liệu mẫu được dựng đúng theo bộ số liệu gốc của nhân viên 015 (Ngô Văn A),
nên khi chạy báo cáo sẽ tái hiện chính xác:
    Đồng cấp = 3.9125 | Cấp dưới = 4.24307598 | Tổng 360° = 4.07778799

CÁCH DÙNG (chạy 1 lần để tạo file mẫu):
    python data/make_sample_data.py

Sau đó chạy báo cáo:
    python main.py --ma-nv 015

Nếu bạn đã có 2 file export thật, chỉ cần đặt chúng vào thư mục data/ với đúng
tên (xem config.py) — KHÔNG cần script này.
"""

import csv
import os

ENCODING = "utf-8-sig"

# Metadata chung của CBLĐ được đánh giá.
EMP = {
    "ma_nv": "015", "ho_ten": "Ngô Văn A", "chuc_danh": "ABC",
    "bo_phan": "DEF", "cap_bac": "X", "ma_bieu_mau": "M268527628665",
}

GROUP_PC = "PHẨM CHẤT LÃNH ĐẠO | LEADERSHIP QUALITIES"
GROUP_NL = "NĂNG LỰC LÃNH ĐẠO | LEADERSHIP ABILITY"

# 24 tiêu chí: (nhóm cha, trọng số nhóm, tên mục tiêu, hệ số áp dụng).
CRITERIA = [
    (GROUP_PC, 30, "Khát vọng: Nghĩ lớn – Mơ lớn – Không bao giờ thỏa mãn với thành tựu đã đạt được. Truyền cảm hứng cho đội ngũ dám chinh phục những đỉnh cao mới.", "11.76470588"),
    (GROUP_PC, 30, "Khát vọng: Chủ động đề xuất, dẫn dắt và kiên trì thực thi các sáng kiến, chương trình tạo giá trị vượt trội cho tổ chức và cộng đồng.", "11.76470588"),
    (GROUP_PC, 30, "Bản lĩnh: Thể hiện rõ nét vai trò thủ lĩnh, đứng mũi chịu sào. Dám nhận việc khó, không đùn đẩy, né tránh trách nhiệm.", "8.823529412"),
    (GROUP_PC, 30, "Bản lĩnh: Giữ vững lập trường đúng đắn trước áp lực; không khoan nhượng với hành vi sai trái. Thẳng thắn nhận sai, hành động dứt khoát xử lý triệt để vấn đề phát sinh.", "8.823529412"),
    (GROUP_PC, 30, "Quyết liệt: Đặt mục tiêu cao, đòi hỏi kết quả vượt trội, tạo áp lực để đẩy nhanh tốc độ.", "11.76470588"),
    (GROUP_PC, 30, "Quyết liệt: Mạnh mẽ, khẩn trương triển khai và bám sát mục tiêu - cụ thể đến từng chi tiết. Xử lý đến cùng mọi khó khăn phát sinh để đạt hiệu quả cao.", "11.76470588"),
    (GROUP_PC, 30, "Sáng tạo: Dám nghĩ khác biệt, không quyết định theo lối mòn; thường xuyên đưa ra sáng kiến, giải pháp mới nhằm tối ưu chi phí, nâng cao hiệu quả.", "8.823529412"),
    (GROUP_PC, 30, "Sáng tạo: Sẵn sàng thay đổi, vận dụng linh hoạt tri thức mới để thử nghiệm ý tưởng mới, thúc đẩy đổi mới và bứt phá trong quản trị, sản phẩm, dịch vụ.", "8.823529412"),
    (GROUP_PC, 30, "Kỷ luật: Nghiêm túc tuân thủ pháp luật, quy định và chuẩn mực đạo đức.", "8.823529412"),
    (GROUP_PC, 30, "Kỷ luật: Giữ chữ Tín, lời nói đi đôi với việc làm, công bằng, minh bạch; đấu tranh với những việc làm thiếu trách nhiệm, vô kỷ luật.", "8.823529412"),
    (GROUP_NL, 70, "Năng lực tư duy và học hỏi: Tư duy Hệ thống, Khoa học, Logic và tập trung vào gốc rễ vấn đề; ra quyết định dựa trên dữ liệu, bằng chứng, tránh cảm tính.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực tư duy và học hỏi: Tư duy đơn giản hóa - chia tách vấn đề lớn thành phần nhỏ dễ xử lý; tìm và áp dụng giải pháp đơn giản nhất.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực tư duy và học hỏi: Học hỏi mạnh mẽ, chuyển biến kiến thức, thông tin vào ứng dụng cụ thể trong quản trị và tổ chức công việc.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực Quản lý con người & phát triển đội ngũ: Phát hiện, thu hút và giữ chân người tài.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực Quản lý con người & phát triển đội ngũ: Dẫn dắt, đào tạo, kèm cặp, huấn luyện phát triển đội ngũ; bố trí đúng người đúng việc qua ủy quyền và trao quyền.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực Quản lý con người & phát triển đội ngũ: Truyền lửa, chuyển tải thông điệp, tạo động lực lớn cho đội ngũ.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực Quản trị kế hoạch: Chuyển đổi từ tầm nhìn chiến lược thành mục tiêu cụ thể và xây dựng kế hoạch hành động để đạt mục tiêu.", "6.25"),
    (GROUP_NL, 70, "Năng lực Quản trị kế hoạch: Lập kế hoạch khả thi, phân bổ nguồn lực hiệu quả, kiểm soát sát tiến độ - chất lượng - kết quả; chủ động xử lý tình huống phát sinh.", "6.25"),
    (GROUP_NL, 70, "Năng lực Quản trị và phát triển tổ chức: Quy hoạch và tổ chức hệ thống quản trị, quy chế và cơ chế kiểm soát khoa học, mạch lạc, tinh gọn, hiệu quả.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực Quản trị và phát triển tổ chức: Tổ chức bộ máy, tổ chức công việc tổng thể tinh gọn, hiệu quả; xử lý mâu thuẫn, phối hợp các bộ phận và kết nối nguồn lực.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực Quản trị và phát triển tổ chức: Xây dựng văn hóa mạnh, môi trường làm việc đoàn kết, văn minh, kỷ luật, khuyến khích đổi mới sáng tạo, hướng đến kết quả.", "8.333333333"),
    (GROUP_NL, 70, "Năng lực Quản trị chuyên môn: Am hiểu sâu kiến thức lĩnh vực phụ trách, vận dụng để giải quyết công việc hiệu quả; cập nhật xu thế, phát triển chuyên môn.", "4.166666667"),
    (GROUP_NL, 70, "Năng lực Quản trị chuyên môn: Xây dựng, giám sát quy trình, tiêu chuẩn chuyên môn nhằm tối ưu hiệu suất công việc.", "4.166666667"),
    (GROUP_NL, 70, "Năng lực Quản trị chuyên môn: Ứng dụng công nghệ mới (đặc biệt là AI) và các sáng kiến, giải pháp mới để nâng cao hiệu quả công việc.", "4.166666667"),
]

# Người đánh giá: meta + mảng 24 điểm (None = chưa đánh giá).
EVALUATORS = [
    {"ma_ad": "mai223", "rel": "Cấp dưới", "bm": "C928977926695", "status": "Đã đánh giá",
     "tong": "4.349999905",
     "y_kien": "Phù hợp với vị trí CV hiện tại và có tầm nhìn để đưa Dịch vụ CSKH của Tập đoàn đi theo đúng đường lối LĐ đã kỳ vọng.",
     "scores": [5,4,4,5,5,5,4,4,5,5, 4,4,4,5,4,5,5,4,4,4,4,4,4,4]},
    {"ma_ad": "hanh225", "rel": "Cấp dưới", "bm": "G471271474346", "status": "Đã đánh giá",
     "tong": "4.329999924",
     "y_kien": "CBLĐ bản lĩnh, quyết liệt.",
     "scores": [4,4,5,5,5,4,4,4,5,5, 4,4,4,5,4,4,5,4,4,4,5,5,4,4]},
    {"ma_ad": "thanh235", "rel": "Đồng nghiệp", "bm": "J211836958247", "status": "Chờ đánh giá",
     "tong": "0", "y_kien": "",
     "scores": [None]*24},
    {"ma_ad": "ha304", "rel": "Đồng nghiệp", "bm": "R243795326873", "status": "Đã đánh giá",
     "tong": "3.910000086",
     "y_kien": "Có tinh thần trách nhiệm với quyết tâm cao để phát triển tổ chức và cá nhân.",
     "scores": [4,4,4,4,4,4,4,4,4,4, 4,4,4,4,4,4,4,4,4,3,4,4,4,3]},
    {"ma_ad": "huongp4", "rel": "Cấp dưới", "bm": "X119600436910", "status": "Đã đánh giá",
     "tong": "4.210000038",
     "y_kien": "Điểm mạnh: Thể hiện rõ nét vai trò, năng lực CBLĐ: Xử lý công việc dứt khoát, gương mẫu, quyết liệt. Am hiểu sâu về lĩnh vực chuyên môn và văn hóa Tập đoàn. Luôn giữ tinh thần làm tới cùng, không né tránh, đùn đẩy. Tổ chức bộ máy, kèm cặp, huấn luyện đội ngũ cùng hướng tới các mục tiêu cao, không ngừng nâng cao hiệu quả, chất lượng công việc.",
     "scores": [5,5,5,4,4,4,4,4,4,5, 5,4,4,4,4,4,4,4,4,4,4,5,4,4]},
    {"ma_ad": "linh223", "rel": "Cấp dưới", "bm": "X230470070905", "status": "Đã đánh giá",
     "tong": "4.079999924",
     "y_kien": "Chị luôn thể hiện tinh thần trách nhiệm và vai trò dẫn dắt trong công việc; việc tăng thêm trao đổi và chia sẻ với đội ngũ trong quá trình triển khai các quyết định quản lý sẽ giúp tạo sự đồng thuận và hiệu quả cao hơn nữa.",
     "scores": [4,4,4,4,4,4,4,4,5,4, 4,4,5,4,4,4,4,4,4,4,4,4,4,4]},
]


def write_chi_tiet(path):
    """Ghi file Chi tiết (banner + header + 24 dòng/người đánh giá)."""
    header = ["Mã AD", "Mối quan hệ với người được đánh giá", "Mã biểu mẫu",
              "Trạng thái", "Tổng điểm", "Ý kiến chung", "Mã nhân viên",
              "Họ và tên", "Chức danh", "Bộ phận", "Cấp bậc chức danh",
              "Mã biểu mẫu", "Tên nhóm mục tiêu", "Trọng số nhóm mục tiêu",
              "Tên mục tiêu", "Hệ Số ÁP DỤNG", "ĐIỂM ĐÁNH GIÁ"]
    banner = ["Người đánh giá"] + [""] * 5 + ["CBLĐ được đánh giá"] + [""] * 10

    with open(path, "w", encoding=ENCODING, newline="") as f:
        w = csv.writer(f)
        w.writerow(banner)
        w.writerow(header)
        for ev in EVALUATORS:
            for i, (group, trong_so, ten_mt, he_so) in enumerate(CRITERIA):
                diem = ev["scores"][i]
                diem_txt = "N/A" if diem is None else str(diem)
                w.writerow([
                    ev["ma_ad"], ev["rel"], ev["bm"], ev["status"], ev["tong"],
                    ev["y_kien"], EMP["ma_nv"], EMP["ho_ten"], EMP["chuc_danh"],
                    EMP["bo_phan"], EMP["cap_bac"], EMP["ma_bieu_mau"],
                    group, str(trong_so), ten_mt, he_so, diem_txt,
                ])


def write_tong_hop(path):
    """Ghi file Tổng hợp (header + 1 dòng dữ liệu của nhân viên 015)."""
    header = ["Mã nhân viên", "Họ và tên", "Chức danh", "Bộ phận", "",
              "Cấp bậc chức danh", "Mã biểu mẫu", "Trạng thái",
              "ĐIỂM TRUNG BÌNH (Cấp trên)", "ĐIỂM TRUNG BÌNH (Đồng cấp)",
              " ĐIỂM TRUNG BÌNH (Cấp dưới)", "TỔNG ĐIỂM ĐÁNH GIÁ 360",
              "Ý KIẾN CHUNG", "AD", "CHECK DS Gốc", "", ""]
    # Ý kiến chung gốc = gộp các nhận xét đã hoàn thành (ngăn bằng dòng trống).
    opinions = "\n\n".join(ev["y_kien"] for ev in EVALUATORS
                           if ev["status"] == "Đã đánh giá" and ev["y_kien"])
    row = ["015", "Ngô Văn A", "ABC", "DEF", "", "T2", "M268527628665",
           "Chưa hoàn thành 5/6", "N/A", "3.9125", "4.24307598", "4.07778799",
           opinions, "#N/A", "KHOIVG", "#N/A", "#N/A"]

    with open(path, "w", encoding=ENCODING, newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerow(row)


if __name__ == "__main__":
    import sys
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    here = os.path.dirname(os.path.abspath(__file__))
    chi_tiet = os.path.join(here, "360 data raw(Chi tiet-raw).csv")
    tong_hop = os.path.join(here, "360 data raw(Tong-hop-raw).csv")
    write_chi_tiet(chi_tiet)
    write_tong_hop(tong_hop)
    print("Đã tạo dữ liệu mẫu:")
    print("  -", chi_tiet)
    print("  -", tong_hop)
