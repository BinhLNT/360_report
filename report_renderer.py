# -*- coding: utf-8 -*-
"""
report_renderer.py
==================
Ghép structured data + nội dung định tính + biểu đồ base64 vào template Jinja2,
xuất ra file .html, rồi cố gắng xuất .pdf bằng WeasyPrint.

Lưu ý môi trường WINDOWS: WeasyPrint cần thư viện GTK/Pango native để xuất PDF.
Nếu máy chưa cài, hàm xuất PDF sẽ KHÔNG làm vỡ chương trình — chỉ in cảnh báo và
hướng dẫn cài đặt; file HTML vẫn được tạo đầy đủ.
"""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config


# ---------------------------------------------------------------------------
# Bộ lọc Jinja2
# ---------------------------------------------------------------------------
def _fmt_score(value, decimals=config.DISPLAY_DECIMALS):
    """Hiển thị điểm: None -> 'N/A', số -> làm tròn."""
    if value is None or value == "":
        return config.NA_TEXT
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def _signed(value, decimals=config.DISPLAY_DECIMALS):
    """Hiển thị số có dấu (+/-)."""
    if value is None:
        return config.NA_TEXT
    return f"{float(value):+.{decimals}f}"


def _make_env():
    """Tạo môi trường Jinja2 trỏ tới thư mục templates."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, config.TEMPLATE_DIR)
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "htm"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["fmt"] = _fmt_score
    env.filters["signed"] = _signed
    return env


# ---------------------------------------------------------------------------
# Render HTML + PDF
# ---------------------------------------------------------------------------
def render_report(structured, content, content_source, charts, out_dir, ma_nv):
    """
    Render báo cáo. Trả về (html_path, pdf_path|None).
    """
    os.makedirs(out_dir, exist_ok=True)
    env = _make_env()
    template = env.get_template(config.TEMPLATE_FILE)

    html = template.render(
        s=structured,
        c=content,
        content_source=content_source,
        charts=charts,
        rel_order=structured["relationship_order"],
        rel_display=structured["relationship_display"],
    )

    # 1. Ghi HTML.
    html_path = os.path.join(out_dir, config.OUT_HTML.format(ma_nv=ma_nv))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 2. Thử xuất PDF (không làm vỡ chương trình nếu thiếu GTK).
    pdf_path = _try_export_pdf(html, out_dir, ma_nv)

    return html_path, pdf_path


def _try_export_pdf(html, out_dir, ma_nv):
    """Xuất PDF bằng WeasyPrint. Trả về đường dẫn hoặc None nếu thất bại."""
    pdf_path = os.path.join(out_dir, config.OUT_PDF.format(ma_nv=ma_nv))
    try:
        from weasyprint import HTML  # import trong hàm để lỗi GTK không chặn cả module
        HTML(string=html, base_url=out_dir).write_pdf(pdf_path)
        return pdf_path
    except Exception as exc:  # noqa: BLE001 - chủ đích bắt rộng để không vỡ pipeline
        print("[CẢNH BÁO] Không xuất được PDF bằng WeasyPrint:")
        print(f"          {type(exc).__name__}: {exc}")
        print("          Trên Windows, WeasyPrint cần thư viện GTK3/Pango native.")
        print("          Cài GTK3 Runtime (https://github.com/tschoonj/"
              "GTK-for-Windows-Runtime-Environment-Installer/releases) rồi chạy lại.")
        print(f"          => Đã tạo đầy đủ file HTML, có thể mở bằng trình duyệt: "
              f"{config.OUT_HTML.format(ma_nv=ma_nv)}")
        return None
