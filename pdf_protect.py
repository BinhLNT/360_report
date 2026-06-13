# -*- coding: utf-8 -*-
"""
pdf_protect.py
==============
MÃ HOÁ BÁO CÁO PDF để CHỈ NGƯỜI NHẬN mở được.

Cơ chế: đặt MẬT KHẨU MỞ FILE (AES-256, qpdf R=6) cho từng PDF.
  - user password : mật khẩu RIÊNG của từng nhân viên (mở đúng báo cáo của mình).
  - owner password : mật khẩu CHỦ của HR/Admin (mở được MỌI báo cáo, full quyền).

Mật khẩu user sinh theo `config.PDF_PASSWORD_SCHEME`:
  - "derived" : HMAC-SHA256(secret_key, ma_nv) -> chuỗi dễ đọc, KHÔNG đoán được,
                tái tạo lại y hệt nếu giữ nguyên khoá (KHUYẾN NGHỊ).
  - "ma_nv"   : dùng chính mã nhân viên (đơn giản, yếu).
  - "random"  : ngẫu nhiên mạnh mỗi lần (chỉ tra được qua manifest).

Khoá bí mật & mật khẩu chủ ưu tiên lấy từ BIẾN MÔI TRƯỜNG (REPORT_SECRET_KEY /
REPORT_OWNER_PASSWORD) để không phải lưu trong mã nguồn.
"""

import csv
import functools
import hashlib
import hmac
import json
import os
import secrets

import config

# Bảng ký tự dễ đọc (bỏ các ký tự dễ nhầm: 0/O, 1/l/I) cho mật khẩu sinh tự động.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"

# File chứa BÍ MẬT cục bộ (khoá HMAC + mật khẩu admin) — KHÔNG commit (đã .gitignore).
SECRETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            config.SECRETS_LOCAL_FILE)


@functools.lru_cache(maxsize=1)
def _local_secrets():
    """Đọc secrets.local.json nếu có (cache 1 lần). Trả về {} nếu thiếu/lỗi.
    LƯU Ý: cache theo tiến trình — sửa file xong cần khởi động lại server."""
    try:
        with open(SECRETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _secret_key():
    """Khoá bí mật cho HMAC. Ưu tiên: env REPORT_SECRET_KEY -> file local -> config."""
    return (os.environ.get("REPORT_SECRET_KEY")
            or _local_secrets().get("REPORT_SECRET_KEY")
            or config.PDF_SECRET_KEY)


def _encode(digest, length):
    """Ánh xạ các byte digest sang bảng ký tự dễ đọc, lấy `length` ký tự đầu."""
    return "".join(_ALPHABET[b % len(_ALPHABET)] for b in digest)[:length]


def derive_password(ma_nv, length=None):
    """Mật khẩu suy diễn (deterministic) từ khoá bí mật + mã NV. KHÔNG đoán được
    nếu không biết khoá; cùng khoá + cùng mã NV luôn cho cùng mật khẩu."""
    length = length or config.PDF_PASSWORD_LENGTH
    digest = hmac.new(_secret_key().encode("utf-8"),
                      str(ma_nv).encode("utf-8"), hashlib.sha256).digest()
    return _encode(digest, length)


def random_password(length=None):
    """Mật khẩu ngẫu nhiên mạnh (mỗi lần gọi khác nhau)."""
    length = length or config.PDF_PASSWORD_LENGTH
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def password_for(ma_nv):
    """Sinh MẬT KHẨU MỞ FILE (user password) cho 1 nhân viên theo scheme cấu hình."""
    scheme = config.PDF_PASSWORD_SCHEME
    if scheme == "ma_nv":
        return str(ma_nv)
    if scheme == "random":
        return random_password()
    return derive_password(ma_nv)   # mặc định: "derived"


def owner_password():
    """Mật khẩu CHỦ (HR/Admin) mở được mọi báo cáo.
    Ưu tiên: env REPORT_OWNER_PASSWORD -> file local -> config -> suy từ khoá bí mật."""
    return (os.environ.get("REPORT_OWNER_PASSWORD")
            or _local_secrets().get("REPORT_OWNER_PASSWORD")
            or config.PDF_OWNER_PASSWORD
            or derive_password("__OWNER__", max(12, config.PDF_PASSWORD_LENGTH)))


def encrypt_pdf_inplace(path, user_pw, owner_pw=None):
    """Mã hoá file PDF tại chỗ (AES-256). Cần user_pw HOẶC owner_pw để mở.

    Ghi ra file tạm rồi thay thế nguyên tử để không hỏng file gốc nếu lỗi.
    """
    import pikepdf
    owner_pw = owner_pw or owner_password()
    tmp = path + ".enc.tmp"
    with pikepdf.open(path) as pdf:
        pdf.save(tmp, encryption=pikepdf.Encryption(
            user=user_pw, owner=owner_pw, R=6,   # R=6 = AES-256
        ))
    os.replace(tmp, path)
    return path


def write_manifest(rows, path):
    """Ghi file manifest (mã NV <-> mật khẩu) để HR phát cho từng người.
    rows: list[{ma_nv, ho_ten, password}]. File này TUYỆT MẬT."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ma_nv", "ho_ten", "password"])
        w.writeheader()
        w.writerows(rows)
    return path
