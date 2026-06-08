# -*- coding: utf-8 -*-
"""
config.py
=========
Tập trung TẤT CẢ hằng số / cấu hình của hệ thống báo cáo 360° tại một nơi
để dễ bảo trì: tên file, encoding, công thức trọng số, mapping tiêu chí,
ngưỡng đánh giá, thư viện gợi ý phát triển (development tips)...

LƯU Ý: file này KHÔNG gọi bất kỳ AI API nào. Mọi nội dung "tip" là thư viện
tĩnh do con người biên soạn, hệ thống chỉ chọn lọc theo điểm số.
"""

# ---------------------------------------------------------------------------
# 1. TÊN FILE & ENCODING
# ---------------------------------------------------------------------------
# Tên 2 file đầu vào (đặt trong thư mục data/). Đổi tại đây nếu tên file khác.
INPUT_CHI_TIET = "360 data raw(Chi tiet-raw).csv"      # File chi tiết theo tiêu chí
INPUT_TONG_HOP = "360 data raw(Tong-hop-raw).csv"      # File tổng hợp gốc (metadata + ý kiến)

# CSV của hệ thống xuất ra từ Excel/Google Sheet thường là UTF-8 có BOM.
# 'utf-8-sig' đọc/ghi đúng cả khi có hoặc không có BOM.
ENCODING = "utf-8-sig"

# ---------------------------------------------------------------------------
# 2. CÔNG THỨC TRỌNG SỐ
# ---------------------------------------------------------------------------
# Điểm 1 người đánh giá = 30% Phẩm chất + 70% Năng lực.
# (Trọng số nhóm được lấy động từ cột "Trọng số nhóm mục tiêu" trong dữ liệu,
#  các hằng số dưới đây chỉ dùng để hiển thị / fallback.)
WEIGHT_PHAM_CHAT = 30
WEIGHT_NANG_LUC = 70

# Thang điểm đánh giá (dùng cho biểu đồ radar / heatmap).
SCORE_MIN = 1.0
SCORE_MAX = 5.0

# Ngưỡng tham chiếu cho ma trận đồng thuận (Phần 3 báo cáo).
CONSENSUS_THRESHOLD = 3.75

# Số chữ số thập phân hiển thị trên báo cáo.
DISPLAY_DECIMALS = 2

# ---------------------------------------------------------------------------
# 3. NHÓM MỤC TIÊU (group) – Phẩm chất / Năng lực
# ---------------------------------------------------------------------------
GROUP_PHAM_CHAT = "PHAM_CHAT"
GROUP_NANG_LUC = "NANG_LUC"

GROUP_DISPLAY = {
    GROUP_PHAM_CHAT: "PHẨM CHẤT LÃNH ĐẠO | LEADERSHIP QUALITIES",
    GROUP_NANG_LUC: "NĂNG LỰC LÃNH ĐẠO | LEADERSHIP ABILITY",
}

# ---------------------------------------------------------------------------
# 4. NHÓM QUAN HỆ (rater group) – Cấp trên / Đồng cấp / Cấp dưới
# ---------------------------------------------------------------------------
# Key nội bộ -> nhãn hiển thị + tên cột trong file Tổng hợp.
REL_CAP_TREN = "cap_tren"
REL_DONG_CAP = "dong_cap"
REL_CAP_DUOI = "cap_duoi"

# Thứ tự hiển thị các nhóm quan hệ.
RELATIONSHIP_ORDER = [REL_CAP_TREN, REL_DONG_CAP, REL_CAP_DUOI]

RELATIONSHIP_DISPLAY = {
    REL_CAP_TREN: "Cấp trên",
    REL_DONG_CAP: "Đồng cấp",
    REL_CAP_DUOI: "Cấp dưới",
}

# Substring (chữ thường, không dấu cũng nhận diện được nhờ hàm normalize)
# dùng để map giá trị cột "Mối quan hệ" -> key nội bộ.
RELATIONSHIP_KEYWORDS = {
    REL_CAP_TREN: ["cap tren", "quan ly", "supervisor", "lanh dao truc tiep"],
    REL_CAP_DUOI: ["cap duoi", "subordinate", "nhan vien"],
    REL_DONG_CAP: ["dong nghiep", "dong cap", "doi tac", "collegue", "colleague", "peer"],
}

# Tên cột điểm trung bình trong file Tổng hợp (match theo substring để
# chịu được sai khác khoảng trắng / hoa thường).
TONGHOP_SCORE_COL_KEYWORDS = {
    REL_CAP_TREN: "điểm trung bình (cấp trên)",
    REL_DONG_CAP: "điểm trung bình (đồng cấp)",
    REL_CAP_DUOI: "điểm trung bình (cấp dưới)",
}
TONGHOP_TOTAL_COL_KEYWORD = "tổng điểm đánh giá 360"
TONGHOP_STATUS_COL_KEYWORD = "trạng thái"
TONGHOP_OPINION_COL_KEYWORD = "ý kiến chung"
TONGHOP_EMP_COL_KEYWORD = "mã nhân viên"

# Giá trị ghi khi một nhóm quan hệ không có ai hoàn thành đánh giá.
NA_TEXT = "N/A"

# ---------------------------------------------------------------------------
# 5. 10 NHÓM TIÊU CHÍ CON (sub-competency) – dùng cho radar / heatmap / gap
# ---------------------------------------------------------------------------
# Mỗi phần tử: (key, nhãn hiển thị ngắn, nhóm cha, [từ khoá nhận diện]).
# Hệ thống phân loại 1 dòng "Tên mục tiêu" vào đúng nhóm con bằng cách so khớp
# từ khoá (ưu tiên khớp sớm theo thứ tự danh sách).
SUBCOMPETENCIES = [
    ("khat_vong",  "Khát vọng",            GROUP_PHAM_CHAT, ["khát vọng", "nghĩ lớn", "think big"]),
    ("ban_linh",   "Bản lĩnh",             GROUP_PHAM_CHAT, ["bản lĩnh"]),
    ("quyet_liet", "Quyết liệt",           GROUP_PHAM_CHAT, ["quyết liệt"]),
    ("sang_tao",   "Sáng tạo",             GROUP_PHAM_CHAT, ["sáng tạo"]),
    ("ky_luat",    "Kỷ luật",              GROUP_PHAM_CHAT, ["kỷ luật"]),
    ("tu_duy",     "Tư duy & Học hỏi",     GROUP_NANG_LUC,  ["tư duy và học hỏi", "năng lực tư duy"]),
    ("con_nguoi",  "Quản lý con người",    GROUP_NANG_LUC,  ["quản lý con người", "phát triển đội ngũ"]),
    ("ke_hoach",   "Quản trị kế hoạch",    GROUP_NANG_LUC,  ["quản trị kế hoạch"]),
    ("to_chuc",    "Quản trị tổ chức",     GROUP_NANG_LUC,  ["quản trị và phát triển tổ chức", "quản trị tổ chức", "phát triển tổ chức"]),
    ("chuyen_mon", "Quản trị chuyên môn",  GROUP_NANG_LUC,  ["quản trị chuyên môn"]),
]

# ---------------------------------------------------------------------------
# 6. NGƯỠNG XẾP LOẠI TỔNG ĐIỂM 360 (badge trên báo cáo)
# ---------------------------------------------------------------------------
# Danh sách (ngưỡng tối thiểu, nhãn, màu). Duyệt từ cao xuống thấp.
BADGE_LEVELS = [
    (4.50, "Xuất sắc",            "#2E7D32"),
    (4.00, "Tốt / Vượt mong đợi", "#388E3C"),
    (3.50, "Đạt / Khá",           "#1F4E79"),
    (2.50, "Cần cải thiện",       "#ED7D31"),
    (0.00, "Dưới mong đợi",       "#C00000"),
]

# ---------------------------------------------------------------------------
# 7. THƯ VIỆN GỢI Ý PHÁT TRIỂN (tĩnh, do con người biên soạn)
# ---------------------------------------------------------------------------
# Map theo key nhóm tiêu chí con -> danh sách tip. Báo cáo sẽ tự lấy tip cho
# các nhóm điểm thấp nhất. KHÔNG có AI ở đây.
DEV_TIPS = {
    "khat_vong": [
        "Đặt mục tiêu thách thức hơn (stretch goals) cho bản thân và đội ngũ theo từng quý.",
        "Chủ động đề xuất 1–2 sáng kiến tạo giá trị vượt trội cho tổ chức trong kỳ tới.",
    ],
    "ban_linh": [
        "Luyện tập đưa ra quyết định dứt khoát trong tình huống áp lực, có ghi nhận bài học.",
        "Chủ động nhận việc khó, tránh né tránh/đùn đẩy; công khai cam kết trách nhiệm.",
    ],
    "quyet_liet": [
        "Thiết lập cơ chế bám sát tiến độ (daily/weekly check-in) cho các mục tiêu trọng yếu.",
        "Xử lý đến cùng các vấn đề phát sinh thay vì để tồn đọng; lập danh sách 'việc tồn'.",
    ],
    "sang_tao": [
        "Dành thời gian thử nghiệm ý tưởng/công nghệ mới, chấp nhận thất bại có kiểm soát.",
        "Tổ chức buổi brainstorm định kỳ để khuyến khích giải pháp khác biệt từ đội ngũ.",
    ],
    "ky_luat": [
        "Chuẩn hoá việc tuân thủ quy định bằng checklist và rà soát định kỳ.",
        "Giữ chữ tín: lời nói đi đôi với việc làm; minh bạch trong cam kết với đội ngũ.",
    ],
    "tu_duy": [
        "Ra quyết định dựa trên dữ liệu/bằng chứng đáng tin cậy, hạn chế cảm tính.",
        "Rèn tư duy đơn giản hoá: chia nhỏ vấn đề lớn thành phần dễ xử lý.",
    ],
    "con_nguoi": [
        "Lên kế hoạch coaching 1:1 định kỳ, mỗi nhân sự chủ chốt tối thiểu 1 lần/tháng.",
        "Xây dựng kế hoạch kế thừa (succession) cho 2–3 vị trí trọng yếu trong nhóm.",
    ],
    "ke_hoach": [
        "Chuyển tầm nhìn thành kế hoạch theo khung OKR, gắn nguồn lực rõ ràng cho từng mục tiêu.",
        "Rà soát rủi ro & kịch bản dự phòng (scenario planning) cho các kế hoạch quan trọng.",
    ],
    "to_chuc": [
        "Rà soát cơ cấu tổ chức & phân quyền (RACI) để loại bỏ chồng chéo, tăng tốc ra quyết định.",
        "Đầu tư xây dựng văn hoá & cơ chế phối hợp liên phòng ban thông qua các nghi thức định kỳ.",
    ],
    "chuyen_mon": [
        "Cập nhật và ứng dụng công nghệ/AI mới: chọn 1 quy trình để số hoá thử nghiệm trong quý tới.",
        "Chuẩn hoá và giám sát quy trình chuyên môn bằng bộ chỉ số chất lượng (SLA/KPI) rõ ràng.",
    ],
}

# ---------------------------------------------------------------------------
# 8. NỘI DUNG ĐỊNH TÍNH MẶC ĐỊNH (fallback khi chưa có nội dung từ Claude)
# ---------------------------------------------------------------------------
# Nhãn các phần trong báo cáo (để render template thống nhất).
SSC_LABELS = {
    "continue": "✅ CONTINUE – Tiếp tục phát huy",
    "start": "➤ START – Bắt đầu làm",
    "stop": "✋ STOP – Cân nhắc dừng",
}

# Tên các file output (sẽ được format với mã nhân viên).
OUT_TONGHOP = "Tong-hop-raw_{ma_nv}.csv"
OUT_PROMPT = "prompt_{ma_nv}.txt"
OUT_STRUCTURED = "structured_{ma_nv}.json"
OUT_CONTENT = "claude_content_{ma_nv}.json"   # file nội dung do Claude sinh (người dùng dán vào)
OUT_HTML = "BAOCAO_{ma_nv}.html"
OUT_PDF = "BAOCAO_{ma_nv}.pdf"

# Tên template Jinja2.
TEMPLATE_DIR = "templates"
TEMPLATE_FILE = "report_template.html"
