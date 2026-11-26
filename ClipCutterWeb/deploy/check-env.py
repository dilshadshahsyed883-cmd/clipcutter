"""Validate private host configuration without printing secrets."""
import os
from pathlib import Path
import re
import stat

ENV = Path("/etc/clipcutter-web/clipcutter-web.env")
def port():
    if ENV.is_symlink() or not ENV.is_file():
        raise SystemExit("Private ClipCutter configuration missing")
    st = ENV.stat()
    if st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1:
        raise SystemExit("Unsafe private environment permissions")
    values = {}
    for line in ENV.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key in values or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
            raise SystemExit("Invalid private environment format")
        values[key] = value
    fixed = {
        "CLIPCUTTER_AUTH_MODE": "local-admin",
        "CLIPCUTTER_WEB_PUBLIC_ORIGIN": "https://clip.scenebuilder.online",
        "CLIPCUTTER_WEB_HOST": "127.0.0.1",
        "CLIPCUTTER_WEB_SECURITY_DB": "/var/lib/clipcutter-web/security.sqlite3",
        "CLIPCUTTER_WEB_DATA_ROOT": "/var/lib/clipcutter-web",
    }
    for key, value in fixed.items():
        if values.get(key) != value:
            raise SystemExit("Unexpected private environment identity")
    required = set(fixed) | {"CLIPCUTTER_ADMIN_USERNAME", "CLIPCUTTER_ADMIN_PASSWORD_HASH",
        "CLIPCUTTER_ADMIN_SESSION_SECRET", "CLIPCUTTER_WEB_PORT"}
    if set(values) != required:
        raise SystemExit("Missing or unexpected private configuration keys")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", values["CLIPCUTTER_ADMIN_USERNAME"]):
        raise SystemExit("Invalid admin username")
    if not re.fullmatch(r"scrypt\$16384\$8\$1\$[a-f0-9]{32}\$[a-f0-9]{64}", values["CLIPCUTTER_ADMIN_PASSWORD_HASH"]):
        raise SystemExit("Invalid password hash")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,200}", values["CLIPCUTTER_ADMIN_SESSION_SECRET"]):
        raise SystemExit("Invalid admin secret")
    p = values["CLIPCUTTER_WEB_PORT"]
    if not re.fullmatch(r"[1-9][0-9]{3,4}", p) or not 1024 <= int(p) <= 65535 or int(p) == 18873:
        raise SystemExit("Invalid or reserved loopback port")
    return int(p)

if __name__ == "__main__":
    print(port())
