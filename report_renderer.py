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
# Render HTML (PDF do pdf_playwright.py đảm nhận ở chế độ batch)
# ---------------------------------------------------------------------------
def build_html(structured, content, content_source, charts):
    """Render template -> chuỗi HTML. PDF được tạo riêng bằng Playwright."""
    env = _make_env()
    template = env.get_template(config.TEMPLATE_FILE)
    return template.render(
        s=structured,
        c=content,
        content_source=content_source,
        charts=charts,
        rel_order=structured["relationship_order"],
        rel_display=structured["relationship_display"],
    )
