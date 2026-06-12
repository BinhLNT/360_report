# -*- coding: utf-8 -*-
"""
pdf_playwright.py
=================
Xuất PDF từ HTML bằng headless Chromium (Playwright) — ổn định cho CSS/biểu đồ
phức tạp, không cần GTK như WeasyPrint.

Tối ưu BATCH: mở trình duyệt MỘT LẦN rồi render nhiều báo cáo (dùng làm context
manager). Ảnh biểu đồ nhúng base64 nên không cần tải mạng.

    with PdfRenderer() as r:
        for html, path in jobs:
            r.render(html, path)
"""


class PdfRenderer:
    def __init__(self, scale=1.0):
        self._scale = scale
        self._pw = None
        self._browser = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        return self

    def render(self, html, pdf_path):
        """Render 1 chuỗi HTML -> file PDF. Trả về pdf_path."""
        page = self._browser.new_page()
        try:
            page.set_content(html, wait_until="load")
            page.emulate_media(media="print")
            page.pdf(
                path=pdf_path,
                print_background=True,
                prefer_css_page_size=True,   # tôn trọng @page trong CSS template
                scale=self._scale,
            )
        finally:
            page.close()
        return pdf_path

    def __exit__(self, exc_type, exc, tb):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        return False


def html_to_pdf(html, pdf_path):
    """Tiện ích xuất 1 file lẻ (mở/đóng trình duyệt 1 lần)."""
    with PdfRenderer() as r:
        return r.render(html, pdf_path)
