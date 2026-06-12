# -*- coding: utf-8 -*-
"""
report_content.py
=================
Chuyển nội dung từ "File thứ 4" (đã rà soát) thành cấu trúc `content` cho template.

- Nếu nhân viên ĐÃ có nội dung AI trong File 4 -> dùng nội dung đó.
- Nếu CHƯA (cột AI còn trống) -> tự sinh nội dung mặc định theo luật
  (content_provider) để báo cáo vẫn đầy đủ. Khi AI điền xong, chạy lại là tự cập nhật.

Giữ nguyên các key template cũ (executive_summary, start_stop_continue, analysis,
development_tips, ai_note) + bổ sung khối `ai` chứa 11 trường AI mở rộng.
"""

import content_provider


def _lines(text):
    """Tách 1 ô nhiều dòng thành list gạch đầu dòng (bỏ ký tự bullet/đánh số đầu)."""
    if not text:
        return []
    items = []
    for raw in str(text).replace("\r", "\n").split("\n"):
        s = raw.strip().lstrip("-•*–—").strip()
        # bỏ tiền tố đánh số "1. ", "2) "
        while s[:2].isdigit() if len(s) >= 2 else False:
            break
        if s and s[0].isdigit():
            j = 1
            while j < len(s) and s[j].isdigit():
                j += 1
            if j < len(s) and s[j] in ".)":
                s = s[j + 1:].strip()
        if s:
            items.append(s)
    return items


def build_content(structured, file4_record):
    """
    Trả về (content_dict, source) với source ∈ {'ai', 'default'}.
    """
    from file4_reader import has_ai_content

    if file4_record and has_ai_content(file4_record):
        return _from_ai(structured, file4_record), "ai"
    # fallback: nội dung mặc định theo luật (đảm bảo báo cáo đầy đủ ngay)
    base = content_provider.build_default_content(structured)
    base["ai"] = None
    base["meta"] = {"nhom_nhan_tai": "", "muc_do_san_sang_thang_tien": "", "tom_tat_mot_dong": ""}
    return base, "default"


def _from_ai(structured, rec):
    """Dựng content từ các trường AI trong File 4."""
    ai = rec.get("ai", {})

    def g(key):
        return (ai.get(key, "") or "").strip()

    content = {
        # --- các phần template cũ ánh xạ từ trường AI ---
        "executive_summary": g("nhan_xet_tong_quan"),
        "start_stop_continue": {
            "continue": _lines(g("nen_tiep_tuc")),
            "start": _lines(g("nen_bat_dau")),
            "stop": _lines(g("nen_dung")) or ["(Không ghi nhận hành vi cần dừng.)"],
        },
        "analysis": g("phan_tich_goc_nhin"),
        "development_tips": {},   # phần gợi ý theo luật để trống — đã có khối AI riêng
        "ai_note": g("ai_note") or
                   "Nội dung do AI tổng hợp từ số liệu 360°, đã được rà soát; vui lòng dùng cho mục đích phát triển.",
        # --- khối AI mở rộng (Phần 6 template) ---
        "ai": {
            "diem_manh": _lines(g("diem_manh")),
            "diem_can_cai_thien": _lines(g("diem_can_cai_thien")),
            "tiem_nang_phat_trien": g("tiem_nang_phat_trien"),
            "khuyen_nghi_dao_tao": _lines(g("khuyen_nghi_dao_tao")),
            "lo_trinh_90_ngay": _lines(g("lo_trinh_90_ngay")),
            "dinh_huong_vai_tro": g("dinh_huong_vai_tro"),
            "canh_bao_rui_ro": g("canh_bao_rui_ro"),
            "khuyen_nghi": rec.get("khuyen_nghi", "").strip(),
        },
        # --- meta hiển thị ở trang bìa ---
        "meta": {
            "nhom_nhan_tai": g("nhom_nhan_tai"),
            "muc_do_san_sang_thang_tien": g("muc_do_san_sang_thang_tien"),
            "tom_tat_mot_dong": g("tom_tat_mot_dong"),
        },
    }
    return content
