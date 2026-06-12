# -*- coding: utf-8 -*-
"""
utils.py
========
Tiện ích dùng chung cho các điểm vào (entry point) chế độ batch.
"""

import sys


def force_utf8_console():
    """Ép stdout/stderr về UTF-8 để in được tiếng Việt trên console Windows
    (mặc định Windows dùng codepage cp125x không encode được ký tự dựng sẵn)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
