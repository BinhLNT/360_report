# -*- coding: utf-8 -*-
"""
ai_engine.py  —  TÍNH NĂNG A: TỰ ĐỘNG ĐIỀN NỘI DUNG AI
======================================================
Đóng "vòng lặp thủ công" trước đây (sinh prompt → dán sang LLM → tải CSV về →
nạp lại) thành MỘT lệnh gọi API tự động.

Với mỗi nhân viên, module:
  1. Dựng "ngữ cảnh grounding" gọn từ structured data (điểm số, hành vi, ý kiến).
  2. Gọi LLM (gpt-oss-120b qua ai_client) yêu cầu trả về JSON 16 trường AI.
  3. Chuẩn hoá & ràng buộc enum, ghép thành CSV (ma_nv + 16 cột) — ĐÚNG định dạng
     mà competency_exporter.merge_ai_csv() đang nhận → ghi thẳng vào File thứ 4.

Có sẵn đường "offline" (rule-based, không gọi API) để chạy/demo khi chưa có key.

Kỹ thuật AI Engineer thể hiện: prompt engineering, structured output (JSON),
ràng buộc enum, xử lý song song hàng loạt, chống bịa số liệu (grounding context).
"""

import csv
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import ai_client
import competency_exporter

# Giá trị hợp lệ cho 2 trường enum (phải KHỚP CHÍNH XÁC để tag báo cáo hoạt động).
ENUM_SAN_SANG = ["Sẵn sàng ngay", "Sẵn sàng 1–2 năm", "Chưa sẵn sàng"]
ENUM_NHAN_TAI = ["Ngôi sao", "Tiềm năng cao", "Vững vàng", "Cần hỗ trợ"]


def field_keys():
    """16 key cột AI theo đúng thứ tự cấu hình."""
    return [k for k, _l, _d in config.AI_FIELDS]


# ===========================================================================
# 1. NGỮ CẢNH GROUNDING cho 1 nhân viên
# ===========================================================================
def _fmt(v):
    if v is None:
        return config.NA_TEXT
    return f"{float(v):.{config.DISPLAY_DECIMALS}f}"


def build_employee_context(structured, max_comments=30):
    """Chuyển structured data của 1 NV thành đoạn văn bản số liệu (để LLM bám vào)."""
    emp = structured["employee"]
    lines = []
    lines.append("THÔNG TIN NHÂN VIÊN")
    lines.append(f"- Mã: {emp['ma_nv']} | Họ tên: {emp['ho_ten']}")
    lines.append(f"- Chức danh: {emp.get('chuc_danh','')} | Bộ phận: {emp.get('bo_phan','')} "
                 f"| Cấp bậc: {emp.get('cap_bac','')}")
    lines.append(f"- Tổng điểm 360°: {_fmt(structured['total_360'])}/5.00 "
                 f"— Xếp loại: {structured['badge']['label']}")
    comp = structured["completion"]
    lines.append(f"- Số người đã hoàn thành đánh giá: {comp['completed']}/{comp['total']}")

    ga = structured["group_averages"]
    grp = []
    for rel in structured["relationship_order"]:
        g = ga.get(rel)
        if g:
            n = g.get("n_completed")
            cnt = f" ({n} người)" if n is not None else ""
            grp.append(f"{g['label']} {_fmt(g['score'])}{cnt}")
    if grp:
        lines.append("- Điểm theo nhóm quan hệ: " + "; ".join(grp))

    subs = [s for s in structured["subcompetencies"] if s.get("others") is not None]
    if subs:
        lines.append("")
        lines.append("ĐIỂM 10 NHÓM TIÊU CHÍ (điểm tổng hợp others):")
        for s in sorted(subs, key=lambda x: x["others"], reverse=True):
            lines.append(f"- {s['label']}: {_fmt(s['others'])}")

    if structured.get("top5"):
        lines.append("")
        lines.append("HÀNH VI MẠNH NHẤT:")
        for b in structured["top5"]:
            lines.append(f"- {b['behavior']} [{b['label']}]: {_fmt(b['score'])}")
    if structured.get("bottom5"):
        lines.append("")
        lines.append("HÀNH VI YẾU NHẤT:")
        for b in structured["bottom5"]:
            lines.append(f"- {b['behavior']} [{b['label']}]: {_fmt(b['score'])}")

    if structured.get("gaps"):
        lines.append("")
        lines.append("CHÊNH LỆCH GÓC NHÌN GIỮA CÁC NHÓM (lớn → nhỏ):")
        for g in structured["gaps"][:3]:
            lines.append(f"- {g['subcomp_label']}: {_fmt(g.get('a'))} vs {_fmt(g.get('b'))} "
                         f"(Δ={_fmt(g.get('delta'))})")

    comments = structured.get("all_comments") or []
    if comments:
        lines.append("")
        lines.append("Ý KIẾN NGUYÊN VĂN (ẩn danh theo nhóm — KHÔNG bịa thêm ngoài các ý này):")
        for c in comments[:max_comments]:
            txt = (c.get("text") or "").replace("\n", " ").strip()
            if txt:
                lines.append(f"  [{c.get('rel','')}] {txt}")
        if len(comments) > max_comments:
            lines.append(f"  (... và {len(comments) - max_comments} ý kiến khác)")
    return "\n".join(lines)


# ===========================================================================
# 2. PROMPT + GỌI LLM
# ===========================================================================
def _system_prompt():
    field_lines = "\n".join(
        f'  - "{key}" ({label}): {desc}' for key, label, desc in config.AI_FIELDS
    )
    keys_json = ", ".join(f'"{k}"' for k in field_keys())
    return f"""Bạn là chuyên gia Phát triển Tổ chức (OD) & Nhân sự (HRBP). Nhiệm vụ: viết phần
VĂN BẢN ĐỊNH TÍNH cho BÁO CÁO ĐÁNH GIÁ 360° của MỘT nhân viên, dựa HOÀN TOÀN vào
số liệu định lượng và ý kiến nguyên văn được cung cấp.

NGUYÊN TẮC BẮT BUỘC:
1. TUYỆT ĐỐI KHÔNG bịa số liệu, sự kiện, tên người ngoài dữ liệu đã cho.
2. KHI NHẮC TỚI ĐIỂM SỐ: chỉ dùng ĐÚNG con số có trong dữ liệu (sao chép nguyên).
   KHÔNG tự nghĩ ra cặp điểm so sánh, không làm tròn khác, không tạo số mới.
   Riêng "phan_tich_goc_nhin": CHỈ dựa vào mục "CHÊNH LỆCH GÓC NHÌN" đã cho; nếu mục
   đó trống thì nói "chưa đủ dữ liệu", KHÔNG bịa cặp số chênh lệch.
3. Viết bằng TIẾNG VIỆT, giọng chuyên nghiệp, trung lập, mang tính xây dựng.
4. Ẩn danh — không gắn nhận xét tiêu cực cho cá nhân/nhóm cụ thể.
5. Báo cáo phục vụ PHÁT TRIỂN CÁ NHÂN, không dùng đơn lẻ cho khen thưởng/kỷ luật.
6. Nếu dữ liệu ít người đánh giá, hãy nêu rõ tính tham khảo.

CÁC TRƯỜNG CẦN SINH (mỗi trường là một chuỗi văn bản):
{field_lines}

QUY TẮC ĐỊNH DẠNG ĐẦU RA:
- Trả về DUY NHẤT một JSON object có ĐÚNG các khoá sau (không thừa, không thiếu):
  {{{keys_json}}}
- Mỗi giá trị là chuỗi tiếng Việt. Với trường dạng danh sách (điểm mạnh, nên bắt đầu…),
  ghi mỗi ý trên MỘT DÒNG MỚI trong chuỗi (ngăn bằng ký tự xuống dòng \\n), không đánh số.
- "muc_do_san_sang_thang_tien" PHẢI là một trong: {" / ".join(ENUM_SAN_SANG)}.
- "nhom_nhan_tai" PHẢI là một trong: {" / ".join(ENUM_NHAN_TAI)}.
- CHỈ in JSON object, KHÔNG in phần suy luận/giải thích, KHÔNG kèm chữ nào ngoài
  JSON, KHÔNG bọc trong ```. """


def generate_fields(structured, *, temperature=None):
    """Gọi LLM sinh 16 trường AI cho 1 nhân viên. Trả về dict 16 key (đã chuẩn hoá)."""
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": "DỮ LIỆU NHÂN VIÊN:\n\n" + build_employee_context(structured)},
    ]
    # reasoning_effort="low": tác vụ điền trường có cấu trúc đơn giản — mức thấp
    # nhanh & rẻ hơn nhiều, lại ÍT "tự suy diễn" thêm số liệu (giảm bịa).
    data = ai_client.chat_json(messages, temperature=temperature, max_tokens=6000,
                               reasoning_effort="low")
    if not isinstance(data, dict):
        raise ValueError("LLM không trả về JSON object cho nội dung AI.")
    return _coerce(data, structured)


# ===========================================================================
# 3. CHUẨN HOÁ & RÀNG BUỘC ENUM
# ===========================================================================
def _norm(s):
    return (s or "").strip().lower()


def _snap_enum(value, allowed, default):
    v = _norm(value)
    if not v:
        return default
    for a in allowed:
        if _norm(a) == v:
            return a
    for a in allowed:                       # khớp lỏng (chứa nhau)
        if _norm(a) in v or v in _norm(a):
            return a
    return default


def _coerce(data, structured):
    """Đảm bảo đủ 16 key (chuỗi), ràng buộc 2 trường enum về giá trị hợp lệ.

    Lưới an toàn (hybrid): trường nào LLM để TRỐNG sẽ được đắp bằng nội dung
    rule-based từ số liệu — báo cáo luôn đủ 16 trường, vẫn bám dữ liệu thật.
    """
    out = {}
    fallback = None
    for k in field_keys():
        val = data.get(k, "")
        val = "" if val is None else str(val).strip()
        if not val:
            if fallback is None:
                fallback = rule_based_fields(structured)
            val = fallback.get(k, "")
        out[k] = val
    out["muc_do_san_sang_thang_tien"] = _snap_enum(
        out["muc_do_san_sang_thang_tien"], ENUM_SAN_SANG, _default_san_sang(structured))
    out["nhom_nhan_tai"] = _snap_enum(
        out["nhom_nhan_tai"], ENUM_NHAN_TAI, _default_nhan_tai(structured))
    return out


def _default_san_sang(structured):
    t = structured.get("total_360")
    if t is None:
        return "Chưa sẵn sàng"
    if t >= 4.5:
        return "Sẵn sàng ngay"
    if t >= 4.0:
        return "Sẵn sàng 1–2 năm"
    return "Chưa sẵn sàng"


def _default_nhan_tai(structured):
    t = structured.get("total_360")
    if t is None:
        return "Cần hỗ trợ"
    if t >= 4.5:
        return "Ngôi sao"
    if t >= 4.0:
        return "Tiềm năng cao"
    if t >= 3.5:
        return "Vững vàng"
    return "Cần hỗ trợ"


# ===========================================================================
# 4. ĐƯỜNG OFFLINE (rule-based, KHÔNG gọi API) — để chạy/demo khi chưa có key
# ===========================================================================
def _sorted_subs(structured, reverse=False):
    subs = [s for s in structured["subcompetencies"] if s.get("others") is not None]
    return sorted(subs, key=lambda s: s["others"], reverse=reverse)


def rule_based_fields(structured):
    """Sinh 16 trường theo LUẬT từ số liệu (baseline không AI)."""
    emp = structured["employee"]
    total = structured["total_360"]
    badge = structured["badge"]["label"]
    top = _sorted_subs(structured, reverse=True)[:3]
    low = _sorted_subs(structured)[:3]
    san_sang = _default_san_sang(structured)
    nhan_tai = _default_nhan_tai(structured)

    diem_manh = "\n".join(f"Nhóm {s['label']}: điểm {_fmt(s['others'])}" for s in top) \
        or "Chưa đủ dữ liệu để xác định điểm mạnh nổi bật."
    diem_yeu = "\n".join(f"Nhóm {s['label']}: điểm {_fmt(s['others'])}" for s in low) \
        or "Chưa đủ dữ liệu để xác định điểm cần cải thiện."
    nen_tiep_tuc = "\n".join(f"Duy trì thế mạnh ở {s['label']}." for s in top) \
        or "Tiếp tục duy trì các điểm mạnh hiện có."
    nen_bat_dau = "\n".join(f"Tập trung cải thiện nhóm {s['label']}." for s in low) \
        or "Chủ động xin phản hồi để xác định ưu tiên phát triển."

    tips = []
    for s in low:
        lib = config.DEV_TIPS.get(s.get("key"))
        if lib:
            tips.extend(list(lib)[:2])
    khuyen_nghi = "\n".join(tips) or "Tham gia chương trình phát triển năng lực phù hợp nhóm điểm thấp."

    gap = (structured.get("gaps") or [None])[0]
    if gap:
        phan_tich = (f"Chênh lệch góc nhìn lớn nhất ở nhóm {gap['subcomp_label']}: "
                     f"{_fmt(gap.get('a'))} so với {_fmt(gap.get('b'))} (Δ={_fmt(gap.get('delta'))}). "
                     "Nên đối thoại để thống nhất kỳ vọng giữa các nhóm.")
    else:
        phan_tich = "Chưa đủ dữ liệu từ ≥2 nhóm rater để phân tích chênh lệch góc nhìn."

    tiem_nang = ("Cao" if (total or 0) >= 4.3 else "Trung bình" if (total or 0) >= 3.7 else "Thấp")
    return {
        "nhan_xet_tong_quan": (
            f"Tổng điểm 360° đạt {_fmt(total)}/5.00 (xếp loại: {badge}), tổng hợp từ "
            f"{structured['completion']['completed']}/{structured['completion']['total']} người đánh giá. "
            f"Điểm mạnh nổi bật ở {', '.join(s['label'] for s in top) or '—'}."),
        "diem_manh": diem_manh,
        "diem_can_cai_thien": diem_yeu,
        "nen_tiep_tuc": nen_tiep_tuc,
        "nen_bat_dau": nen_bat_dau,
        "nen_dung": "Chưa ghi nhận hành vi cần dừng từ phản hồi định tính.",
        "phan_tich_goc_nhin": phan_tich,
        "tiem_nang_phat_trien": f"{tiem_nang} — đánh giá dựa trên tổng điểm và phân bố theo nhóm.",
        "khuyen_nghi_dao_tao": khuyen_nghi,
        "lo_trinh_90_ngay": ("\n".join(
            f"Cải thiện {s['label']}: đặt 1 mục tiêu đo lường được trong 90 ngày." for s in low[:2])
            or "Thiết lập 2–3 mục tiêu phát triển đo lường được cho kỳ tới."),
        "muc_do_san_sang_thang_tien": san_sang,
        "dinh_huong_vai_tro": (
            f"Phù hợp tiếp tục phát triển ở vai trò {emp.get('chuc_danh','hiện tại')}, "
            f"phát huy thế mạnh {', '.join(s['label'] for s in top[:2]) or 'hiện có'}."),
        "canh_bao_rui_ro": "Không ghi nhận" if (total or 0) >= 3.5 else
                           "Điểm tổng dưới mong đợi — cần theo dõi và hỗ trợ kịp thời.",
        "nhom_nhan_tai": nhan_tai,
        "tom_tat_mot_dong": f"{emp['ho_ten']} — {badge}, {_fmt(total)}/5.00, nhóm {nhan_tai}.",
        "ai_note": ("Nội dung sinh TỰ ĐỘNG theo luật từ số liệu (chế độ offline, không gọi LLM). "
                    "Cần OD/HRBP rà soát trước khi dùng."),
    }


# ===========================================================================
# 5. SINH HÀNG LOẠT + GHI VÀO FILE THỨ 4
# ===========================================================================
def _select(structured_list, only_ma):
    if not only_ma:
        return list(structured_list)
    sel = {str(m).strip() for m in only_ma}
    return [s for s in structured_list if s["employee"]["ma_nv"] in sel]


def generate_for_list(structured_list, *, only_ma=None, offline=False,
                      progress_cb=None, max_workers=None):
    """
    Sinh nội dung AI cho danh sách NV. Trả về (rows, stats).
      rows  : list[dict] mỗi dict = {"ma_nv":.., <16 key>}
      stats : {"ok":n, "failed":n, "errors":[(ma_nv,msg)...], "offline":bool}
    """
    targets = _select(structured_list, only_ma)
    total = len(targets)
    rows, errors = [], []
    done = {"n": 0}

    def _emit():
        if progress_cb:
            progress_cb(done["n"], total)

    def _one(structured):
        ma = structured["employee"]["ma_nv"]
        if offline:
            return ma, rule_based_fields(structured), None
        try:
            return ma, generate_fields(structured), None
        except Exception as exc:                       # noqa: BLE001
            return ma, None, f"{type(exc).__name__}: {exc}"

    if offline:
        # Tuần tự cho nhanh & ổn định (không tốn I/O mạng).
        for s in targets:
            ma, fields, err = _one(s)
            done["n"] += 1
            if fields is not None:
                rows.append({"ma_nv": ma, **fields})
            else:
                errors.append((ma, err))
            _emit()
    else:
        workers = max_workers or ai_client.settings()["max_workers"]
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = [ex.submit(_one, s) for s in targets]
            for fut in as_completed(futs):
                ma, fields, err = fut.result()
                done["n"] += 1
                if fields is not None:
                    rows.append({"ma_nv": ma, **fields})
                else:
                    errors.append((ma, err))
                _emit()

    return rows, {"ok": len(rows), "failed": len(errors), "errors": errors, "offline": offline,
                  "total": total}


def rows_to_csv(rows, path):
    """Ghi rows ra CSV UTF-8 (header = ma_nv + 16 key) — đúng định dạng merge_ai_csv nhận."""
    header = ["ma_nv"] + field_keys()
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def autofill_file4(file4_path, structured_list, *, only_ma=None, only_missing=False,
                   offline=False, progress_cb=None, csv_out=None):
    """
    Sinh nội dung AI cho (nhóm) NV rồi GHI THẲNG vào cột AI của File thứ 4.
    Trả về stats gộp (sinh + merge). csv_out (nếu có) = nơi lưu CSV kết quả để tải về.

    only_missing=True: BỎ QUA nhân viên đã có nội dung AI trong File thứ 4 hiện tại
    (tiết kiệm chi phí khi chạy lại / điền tăng dần — không trả tiền lại cho người cũ).
    """
    if not os.path.isfile(file4_path):
        raise FileNotFoundError("Chưa có File thứ 4 — hãy chạy Bước 1 trước khi tự động điền AI.")

    skipped_filled = 0
    if only_missing:
        import file4_reader                       # tránh phụ thuộc vòng lúc import
        recs = file4_reader.read_file4(file4_path)
        filled = {ma for ma, r in recs.items() if file4_reader.has_ai_content(r)}
        base = ([str(m).strip() for m in only_ma] if only_ma
                else [s["employee"]["ma_nv"] for s in structured_list])
        only_ma = [m for m in base if m not in filled]
        skipped_filled = len(base) - len(only_ma)
        if not only_ma:
            return {"ok": 0, "failed": 0, "errors": [], "offline": offline, "total": 0,
                    "updated": 0, "csv_path": None, "skipped_filled": skipped_filled,
                    "usage": ai_client.usage_snapshot()}

    rows, stats = generate_for_list(
        structured_list, only_ma=only_ma, offline=offline, progress_cb=progress_cb)
    stats["skipped_filled"] = skipped_filled
    if not rows:
        return {**stats, "updated": 0, "csv_path": None}

    if csv_out:
        rows_to_csv(rows, csv_out)
        csv_path = csv_out
        merge_res = competency_exporter.merge_ai_csv(file4_path, csv_path)
    else:
        fd, tmp = tempfile.mkstemp(suffix=".csv", prefix="ai_autofill_")
        os.close(fd)
        try:
            rows_to_csv(rows, tmp)
            merge_res = competency_exporter.merge_ai_csv(file4_path, tmp)
            csv_path = None
        finally:
            if os.path.isfile(tmp):
                os.remove(tmp)
    return {**stats, "updated": merge_res.get("updated", 0), "csv_path": csv_path,
            "usage": ai_client.usage_snapshot()}
