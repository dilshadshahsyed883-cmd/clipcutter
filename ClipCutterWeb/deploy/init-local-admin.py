#!/usr/bin/env python3
"""One-time, manual VPS terminal provisioning; never pass passwords in argv.

Creates only /etc/clipcutter-web/clipcutter-web.env. Existing private configuration
is never overwritten. Do not run as part of GitHub Actions or CI.
"""
from __future__ import annotations
import getpass
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import stat
import sys

ROOT = Path("/etc/clipcutter-web")
ENV = ROOT / "clipcutter-web.env"


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run the private bootstrap with sudo on the VPS")
    if not ROOT.is_dir() or ROOT.is_symlink() or ROOT.stat().st_uid != 0:
        raise SystemExit("ClipCutter private config directory is not root-owned")
    if ENV.exists() or ENV.is_symlink():
        raise SystemExit("Existing ClipCutter private config will not be overwritten")
    username = input("ClipCutter admin username [admin]: ").strip() or "admin"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", username) or username == "__default__":
        raise SystemExit("Invalid local admin username")
    password = getpass.getpass("Choose a new ClipCutter admin password (6+ chars): ")
    confirmation = getpass.getpass("Confirm password: ")
    if (not hmac.compare_digest(password, confirmation) or
        not 6 <= len(password) <= 1024 or
        any(ord(char) < 32 for char in password)):
        raise SystemExit("Password mismatch or insufficient strength")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=16384, r=8, p=1, dklen=32)
    encoded = "scrypt$16384$8$1$" + salt.hex() + "$" + digest.hex()
    session_secret = secrets.token_urlsafe(48)
    port = input("Verified free loopback port: ").strip()
    if not port.isdecimal() or not 1024 <= int(port) <= 65535 or int(port) == 18873:
        raise SystemExit("Invalid or reserved port")
    lines = [
        "CLIPCUTTER_AUTH_MODE=local-admin",
        "CLIPCUTTER_ADMIN_USERNAME=" + username,
        "CLIPCUTTER_ADMIN_PASSWORD_HASH=" + encoded,
        "CLIPCUTTER_ADMIN_SESSION_SECRET=" + session_secret,
        "CLIPCUTTER_WEB_SECURITY_DB=/var/lib/clipcutter-web/security.sqlite3",
        "CLIPCUTTER_WEB_DATA_ROOT=/var/lib/clipcutter-web",
        "CLIPCUTTER_WEB_PUBLIC_ORIGIN=https://clip.scenebuilder.online",
        "CLIPCUTTER_WEB_HOST=127.0.0.1",
        "CLIPCUTTER_WEB_PORT=" + port,
    ]
    content = ("\n".join(lines) + "\n").encode()
    # O_EXCL and O_NOFOLLOW prevent racing an existing private environment.
    fd = os.open(str(ENV), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        ENV.unlink(missing_ok=True)
        raise
    print("LOCAL_ADMIN_ENV=CREATED_MODE_0600")
    print("ADMIN_USERNAME=" + username)
    print("SECRETS=NOT_DISPLAYED")
    print("SERVICE=NOT_STARTED")


if __name__ == "__main__":
    main()
