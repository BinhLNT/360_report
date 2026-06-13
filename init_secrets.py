# -*- coding: utf-8 -*-
"""
init_secrets.py
===============
Tạo file BÍ MẬT cục bộ `secrets.local.json` (đã .gitignore) chứa:
  - REPORT_SECRET_KEY     : khoá HMAC để suy ra mật khẩu MỞ FILE của TỪNG nhân viên.
  - REPORT_OWNER_PASSWORD : mật khẩu CHỦ (HR/Admin) mở được MỌI báo cáo.

CÁCH DÙNG:
  python init_secrets.py            # tạo nếu chưa có (KHÔNG ghi đè)
  python init_secrets.py --force    # tạo mới, GHI ĐÈ (mật khẩu cũ sẽ đổi hết!)
  python init_secrets.py --show     # chỉ in mật khẩu admin hiện tại

LƯU Ý: sau khi đổi khoá, mật khẩu của mọi báo cáo sẽ KHÁC -> phải XUẤT LẠI báo
cáo + manifest. File này TUYỆT MẬT, không commit, không gửi cho ai.
"""

import argparse
import json
import os
import secrets
import sys

import config
import utils

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"  # bỏ ký tự dễ nhầm

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), config.SECRETS_LOCAL_FILE)


def _readable(n):
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def generate():
    return {
        "REPORT_SECRET_KEY": secrets.token_urlsafe(32),   # khoá HMAC (mạnh)
        "REPORT_OWNER_PASSWORD": _readable(16),           # mật khẩu admin (dễ đọc)
    }


def main(argv=None):
    utils.force_utf8_console()
    p = argparse.ArgumentParser(description="Tạo/giữ file bí mật secrets.local.json")
    p.add_argument("--force", action="store_true", help="Ghi đè (đổi toàn bộ mật khẩu)")
    p.add_argument("--show", action="store_true", help="Chỉ in mật khẩu admin hiện tại")
    a = p.parse_args(argv)

    if a.show:
        if not os.path.isfile(PATH):
            print(f"[!] Chưa có {PATH}. Chạy 'python init_secrets.py' để tạo.")
            sys.exit(1)
        data = json.load(open(PATH, encoding="utf-8"))
        print(f"Mật khẩu ADMIN: {data.get('REPORT_OWNER_PASSWORD', '(không có)')}")
        return

    if os.path.isfile(PATH) and not a.force:
        print(f"[=] Đã tồn tại {PATH} — giữ nguyên (dùng --force để tạo mới).")
        data = json.load(open(PATH, encoding="utf-8"))
        print(f"    Mật khẩu ADMIN hiện tại: {data.get('REPORT_OWNER_PASSWORD', '(không có)')}")
        return

    data = generate()
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Đã ghi {PATH} (đã .gitignore — KHÔNG commit).")
    print(f"     KHOÁ BÍ MẬT  : {data['REPORT_SECRET_KEY']}")
    print(f"     MẬT KHẨU ADMIN: {data['REPORT_OWNER_PASSWORD']}")
    if a.force:
        print("     ! Đã đổi khoá -> hãy XUẤT LẠI báo cáo + manifest (mật khẩu cũ không còn đúng).")


if __name__ == "__main__":
    main()
