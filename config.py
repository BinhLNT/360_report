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
INPUT_CHI_TIET = "Report_360_MASKED_v2(Chi tiet).csv"           # File chi tiết theo tiêu chí
INPUT_TONG_HOP = "Report_360_MASKED_v2(Tong hop).csv"           # File tổng hợp gốc (metadata + ý kiến)

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

# ===========================================================================
# 9. CHẾ ĐỘ BATCH (>= 500 nhân viên) — "FILE THỨ 4" + PROMPT CHUNG
# ===========================================================================
# Quy trình mới: thay vì 1 prompt/người, hệ thống tính điểm cho TOÀN BỘ nhân
# viên rồi sinh:
#   (1) 1 PROMPT CHUNG (prompt_chung.txt) dùng cho mọi nhân viên.
#   (2) "FILE THỨ 4" dạng Excel: mỗi nhân viên 1 dòng = cột dữ liệu gốc + cột
#       AI (để Claude điền) + cột quy trình rà soát của con người.
# Sau khi con người rà soát/duyệt, dữ liệu này được ghép vào template để xuất
# báo cáo PDF hàng loạt (có bộ lọc).

OUT_BATCH_XLSX = "360_AI_input.xlsx"          # "File thứ 4" (skeleton để AI điền)
OUT_COMMON_PROMPT = "prompt_chung.txt"        # 1 prompt dùng chung cho toàn bộ
BATCH_SHEET_NAME = "BaoCao_360"               # tên sheet chính trong file thứ 4

# --- 9a. Cột DỮ LIỆU GỐC / CONTEXT (read-only đối với người rà soát) ---------
# (key nội bộ, nhãn hiển thị trên Excel). Các cột chuc_danh/bo_phan/cap_bac/
# manager/team/xep_loai đồng thời là TIÊU CHÍ LỌC khi xuất PDF.
SOURCE_FIELDS = [
    ("ma_nv",         "Mã nhân viên"),
    ("ho_ten",        "Họ và tên"),
    ("chuc_danh",     "Chức danh"),               # filter: chức vụ
    ("bo_phan",       "Bộ phận"),                 # filter: phòng ban
    ("cap_bac",       "Cấp bậc chức danh"),       # filter: cấp bậc
    ("manager",       "Manager"),                 # filter: quản lý (cần nguồn dữ liệu)
    ("team",          "Team"),                    # filter: team (cần nguồn dữ liệu)
    ("trang_thai",    "Trạng thái"),
    ("diem_cap_tren", "Điểm TB (Cấp trên)"),
    ("diem_dong_cap", "Điểm TB (Đồng cấp)"),
    ("diem_cap_duoi", "Điểm TB (Cấp dưới)"),
    ("tong_360",      "Tổng điểm 360"),
    ("xep_loai",      "Xếp loại"),                # filter: rating
    ("du_lieu_tom_tat", "Dữ liệu đầu vào (tham chiếu cho AI)"),
]

# --- 9b. Cột AI-GENERATED (Claude điền) --------------------------------------
# (key, nhãn hiển thị, mô tả/luật để đưa vào prompt chung & schema).
AI_FIELDS = [
    ("nhan_xet_tong_quan", "Nhận xét tổng quan",
     "Tóm tắt điều hành 2–3 câu: mức điểm tổng, xếp loại, điểm mạnh nổi bật và 1–2 lưu ý."),
    ("diem_manh", "Điểm mạnh",
     "3–5 gạch đầu dòng điểm mạnh nổi bật, có dẫn chiếu nhóm tiêu chí/điểm số."),
    ("diem_can_cai_thien", "Điểm cần cải thiện",
     "3–5 gạch đầu dòng điểm cần cải thiện, ưu tiên nhóm tiêu chí điểm thấp nhất."),
    ("nen_tiep_tuc", "Nên tiếp tục (Continue)",
     "Các hành vi/thế mạnh nên DUY TRÌ phát huy."),
    ("nen_bat_dau", "Nên bắt đầu (Start)",
     "Các hành vi nên BẮT ĐẦU làm để cải thiện."),
    ("nen_dung", "Nên dừng (Stop)",
     "Hành vi nên CÂN NHẮC DỪNG; nếu không có, ghi 1 câu trung tính."),
    ("phan_tich_goc_nhin", "Phân tích chênh lệch góc nhìn",
     "Phân tích chênh lệch giữa Cấp trên/Đồng cấp/Cấp dưới và ý nghĩa coaching."),
    ("tiem_nang_phat_trien", "Tiềm năng phát triển",
     "Đánh giá tiềm năng: Cao / Trung bình / Thấp kèm lý do ngắn dựa trên số liệu."),
    ("khuyen_nghi_dao_tao", "Khuyến nghị đào tạo",
     "Khoá học / coaching / chương trình phát triển cụ thể cho điểm yếu."),
    ("lo_trinh_90_ngay", "Lộ trình 90 ngày",
     "2–3 hành động ưu tiên, đo lường được, cho kỳ tới."),
    ("muc_do_san_sang_thang_tien", "Mức độ sẵn sàng thăng tiến",
     "CHỌN MỘT: 'Sẵn sàng ngay' / 'Sẵn sàng 1–2 năm' / 'Chưa sẵn sàng'."),
    ("dinh_huong_vai_tro", "Định hướng vai trò",
     "Vai trò / lộ trình nghề nghiệp phù hợp dựa trên thế mạnh."),
    ("canh_bao_rui_ro", "Cảnh báo rủi ro",
     "Rủi ro nghỉ việc / điểm mù nếu có; nếu không, ghi 'Không ghi nhận'."),
    ("nhom_nhan_tai", "Nhóm nhân tài",
     "CHỌN MỘT nhãn để lọc: 'Ngôi sao' / 'Tiềm năng cao' / 'Vững vàng' / 'Cần hỗ trợ'."),
    ("tom_tat_mot_dong", "Tóm tắt một dòng",
     "Đúng 1 câu tóm tắt (cho trang bìa / danh sách)."),
    ("ai_note", "Lưu ý AI",
     "1 câu: nội dung do AI tổng hợp từ số liệu, cần HRBP/OD rà soát trước khi dùng."),
]

# --- 9c. Cột QUY TRÌNH RÀ SOÁT (con người điền) ------------------------------
# (key, nhãn, danh sách giá trị hợp lệ nếu là dropdown — None nếu nhập tự do).
REVIEW_FIELDS = [
    ("trang_thai_ra_soat", "Trạng thái rà soát",
     ["Nháp", "Đã rà soát", "Đã duyệt", "Cần sửa"]),
    ("nguoi_ra_soat", "Người rà soát", None),
    ("ngay_ra_soat",  "Ngày rà soát", None),
    ("ghi_chu_ra_soat", "Ghi chú rà soát", None),
]

# Chỉ những dòng có trạng thái này mới được phép xuất báo cáo (Phase 3).
REVIEW_STATUS_APPROVED = "Đã duyệt"
REVIEW_STATUS_DEFAULT = "Nháp"

# Màu nền phân biệt nhóm cột trên Excel (ARGB, không có dấu '#').
XLSX_FILL_SOURCE = "FFF2F2F2"   # xám nhạt — cột dữ liệu gốc (không sửa)
XLSX_FILL_AI     = "FFFFF7E6"   # vàng nhạt — cột AI điền
XLSX_FILL_REVIEW = "FFE8F4EA"   # xanh nhạt — cột con người rà soát
XLSX_FILL_HEADER = "FF1F4E79"   # xanh đậm — nền hàng header

# ===========================================================================
# 10. ĐỊNH DẠNG "FILE THỨ 4" THEO MẪU "TỔNG HỢP TIÊU CHÍ" (wide format)
# ===========================================================================
# File thứ 4 BÁM ĐÚNG bố cục file "360 data raw(Sheet1).csv" của người dùng:
#   [Định danh] + [KẾT QUẢ ĐÁNH GIÁ] + 4 KHỐI RATER × 24 hành vi + [Khuyến nghị]
#   + [các cột AI] + [các cột rà soát].
# LƯU Ý: nội dung 24 hành vi dưới đây tái dựng từ bản mẫu (bị lỗi mã hoá khi
# dán). Cần ĐỐI CHIẾU lại với file gốc sạch để khớp 100% câu chữ/thứ tự.

INPUT_COMPETENCY = "Report_360_MASKED_v2(Tong hop tieu chi).csv"   # file "Tổng hợp tiêu chí"

# --- 10a. Cột định danh theo mẫu Sheet1 (key nội bộ -> nhãn hiển thị) ---------
IDENTITY_FIELDS_V2 = [
    ("ma_nv",          "Mã nhân viên"),
    ("ho_ten",         "Họ và tên"),
    ("chuc_danh",      "Chức danh"),
    ("ban_chuoi_khoi", "Bộ phận"),           # filter: phòng ban (khớp nhãn dữ liệu thật)
    ("cap_bac",        "Cấp bậc"),
    ("trang_thai",     "Trạng thái"),
]
LABEL_KET_QUA = "KẾT QUẢ ĐÁNH GIÁ"
LABEL_KHUYEN_NGHI = "Khuyến nghị"
LABEL_YKIEN = "Ý kiến đánh giá (từng người, ẩn danh)"   # gộp toàn bộ ý kiến CHUNG của người đánh giá
LABEL_DIEN_GIAI = "Diễn giải / Ý kiến theo tiêu chí (từng người, ẩn danh)"   # cột thứ 2 khối TỔNG: ý kiến PER-MỤC-TIÊU

# Token "rỗng / không đánh giá" cần BỎ khi gom ý kiến (so khớp ở dạng chữ thường,
# đã .strip()). Dùng chung cho ý kiến CHUNG và ý kiến theo từng mục tiêu.
COMMENT_JUNK_TOKENS = {"", "n/a", "nan", "#n/a", "na", "none", "null", "-", "."}

# --- 10b. 4 khối rater (banner hàng 1) -> nguồn điểm trong structured ---------
# Khớp ĐÚNG bố cục file gốc (đã đo bằng _analyze_sheet1):
#   - Khối TỔNG: 2 CỘT/hành vi (điểm + diễn giải) -> 48 cột.
#   - 3 khối rater còn lại: 1 CỘT/hành vi (điểm) -> 24 cột mỗi khối.
# (key cột, nhãn banner ĐÚNG NHƯ GỐC, key điểm trong behavior dict, số cột/hành vi).
RATER_BLOCKS = [
    ("tong",        "TỔNG ĐIỂM THEO TIÊU CHÍ", "others",   2),
    ("cap_tren",    "CẤP TRÊN",                "cap_tren", 1),
    ("dong_nghiep", "ĐỒNG NGHIỆP/ ĐỐI TÁC",    "dong_cap", 1),
    ("cap_duoi",    "CẤP DƯỚI",                "cap_duoi", 1),
]

# Tên đầy đủ nhóm năng lực ĐÚNG NHƯ FILE GỐC (dùng cho hàng 2 header File thứ 4).
COMPETENCY_DISPLAY_FULL = {
    "khat_vong":  "Khát vọng",
    "ban_linh":   "Bản lĩnh",
    "quyet_liet": "Quyết liệt",
    "sang_tao":   "Sáng tạo",
    "ky_luat":    "Kỷ luật",
    "tu_duy":     "Năng lực tư duy và học hỏi",
    "con_nguoi":  "Năng lực Quản lý con người & phát triển đội ngũ",
    "ke_hoach":   "Năng lực Quản trị kế hoạch",
    "to_chuc":    "Năng lực Quản trị và phát triển tổ chức",
    "chuyen_mon": "Năng lực Quản trị chuyên môn (Đánh giá theo chuyên môn CBLĐ đảm trách)",
}

# --- 10c. 24 hành vi (mục tiêu) theo thứ tự file gốc --------------------------
# (subcomp_key khớp SUBCOMPETENCIES, mô tả đầy đủ hành vi). 2-2-2-2-2-3-3-2-3-3.
BEHAVIORS = [
    ("khat_vong",  "Nghĩ lớn – Mơ lớn – Không bao giờ thỏa mãn với những thành tựu đã đạt được. Truyền cảm hứng cho đội ngũ dám chinh phục và kiên trì theo đuổi những đỉnh cao mới."),
    ("khat_vong",  "Chủ động đề xuất, dẫn dắt và kiên trì thực thi các sáng kiến, chương trình, với mục tiêu tạo ra giá trị vượt trội cho tổ chức và cộng đồng."),
    ("ban_linh",   "Thể hiện rõ nét vai trò thủ lĩnh, đứng mũi chịu sào. Dám nhận việc khó, không đùn đẩy, né tránh trách nhiệm."),
    ("ban_linh",   "Giữ vững lập trường đúng đắn trước áp lực; không khoan nhượng với những hành vi sai trái, chất lượng công việc yếu kém. Thẳng thắn nhận sai, sẵn sàng sửa sai và hành động đến cùng để xử lý triệt để các vấn đề phát sinh."),
    ("quyet_liet", "Đặt mục tiêu cao, đòi hỏi kết quả vượt trội, tạo áp lực để đẩy nhanh tốc độ."),
    ("quyet_liet", "Mạnh mẽ, khẩn trương triển khai và bám sát mục tiêu trong công việc - cụ thể đến từng chi tiết. Xử lý đến cùng mọi khó khăn phát sinh để đạt được hiệu quả cao trong công việc."),
    ("sang_tao",   "Dám nghĩ khác biệt, không quyết định theo kinh nghiệm lối mòn của quá khứ, hoặc định kiến bảo thủ, thường xuyên đưa ra sáng kiến, giải pháp mới nhằm tối ưu chi phí, nâng cao hiệu quả."),
    ("sang_tao",   "Sẵn sàng thay đổi, vận dụng linh hoạt thông tin và tri thức mới vào thử nghiệm các ý tưởng mới để thúc đẩy đổi mới và bứt phá trong quyết định quản trị, thiết kế sản phẩm và tiêu chuẩn dịch vụ."),
    ("ky_luat",    "Nghiêm túc tuân thủ pháp luật, quy định và chuẩn mực đạo đức."),
    ("ky_luat",    "Giữ chữ Tín, lời nói đi đôi với việc làm, công bằng, minh bạch. Không thỏa hiệp, không ngại va chạm, không bị tư tưởng \"thương quân\" lấn át, đấu tranh với những việc làm thiếu trách nhiệm, vô kỷ luật."),
    ("tu_duy",     "Tư duy Hệ thống, Khoa học, Logic và tập trung vào gốc rễ vấn đề: Nhìn xa trông rộng, phân tích đa chiều, tập trung xử lý gốc rễ vấn đề và ra quyết định dựa trên dữ liệu, bằng chứng đáng tin cậy, tránh cảm tính."),
    ("tu_duy",     "Tư duy đơn giản hóa: Tiếp cận vấn đề một cách đơn giản, biết chia tách và hóa giải vấn đề lớn, phức tạp thành những phần nhỏ, đơn giản, dễ xử lý. Tìm ra và áp dụng giải pháp đơn giản nhất để giải quyết vấn đề."),
    ("tu_duy",     "Học hỏi mạnh mẽ, có thể chuyển biến kiến thức, thông tin vào các ứng dụng cụ thể trong các quyết định trong quản trị và tổ chức công việc."),
    ("con_nguoi",  "Phát hiện, thu hút và giữ chân người tài."),
    ("con_nguoi",  "Dẫn dắt, đào tạo, kèm cặp, huấn luyện phát triển đội ngũ. Bố trí đúng người đúng việc thông qua ủy quyền và trao quyền."),
    ("con_nguoi",  "Truyền lửa, chuyển tải thông điệp, tạo động lực lớn cho đội ngũ."),
    ("ke_hoach",   "Chuyển đổi từ tầm nhìn chiến lược thành các mục tiêu cụ thể và xây dựng kế hoạch hành động để đạt được các mục tiêu đó."),
    ("ke_hoach",   "Lập kế hoạch khả thi, phân bổ nguồn lực hiệu quả, kiểm soát sát tiến độ, chất lượng và kết quả công việc; chủ động điều chỉnh, xử lý các tình huống phát sinh kịp thời để đảm bảo đạt mục tiêu."),
    ("to_chuc",    "Quy hoạch và tổ chức hệ thống quản trị, quy định quy chế và cơ chế kiểm soát khoa học, mạch lạc, tinh gọn, hiệu quả."),
    ("to_chuc",    "Tổ chức bộ máy, tổ chức công việc tổng thể, tinh gọn, hiệu quả, xử lý mâu thuẫn, phối hợp các bộ phận để thực hiện công việc và có thể thu hút, kết nối nguồn lực nội bộ và đối tác bên ngoài."),
    ("to_chuc",    "Xây dựng văn hóa mạnh, môi trường làm việc đoàn kết, văn minh, kỷ luật, khuyến khích đổi mới, sáng tạo, hướng đến kết quả cuối cùng."),
    ("chuyen_mon", "Am hiểu sâu kiến thức lĩnh vực phụ trách, biết vận dụng để giải quyết công việc hiệu quả; thường xuyên cập nhật xu thế, phát triển chuyên môn gắn với yêu cầu mục tiêu phát triển của tổ chức."),
    ("chuyen_mon", "Xây dựng, giám sát quy trình, tiêu chuẩn chuyên môn nhằm tối ưu hiệu suất công việc."),
    ("chuyen_mon", "Ứng dụng công nghệ mới (đặc biệt là AI) và các sáng kiến và giải pháp mới để nâng cao hiệu quả công việc."),
]

# Tên file thứ 4 ở định dạng wide (mẫu Sheet1).
OUT_BATCH_XLSX_WIDE = "360_AI_input_full.xlsx"
