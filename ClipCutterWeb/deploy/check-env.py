"""Validate private host configuration without printing secrets."""
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

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
    return validate(values)

def validate(values):
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
    gpu = {"CLIPCUTTER_SCHEDULER_ENABLED", "CLIPCUTTER_LIFECYCLE_ENABLED",
        "CLIPCUTTER_APPROVED_OWNER", "CLIPCUTTER_APPROVED_SALAD_GROUP",
        "CLIPCUTTER_APPROVED_WORKER_GATEWAY", "CLIPCUTTER_APPROVED_WORKER_SHA",
        "CLIPCUTTER_APPROVED_GPU_IMAGE"}
    optional = {"CLIPCUTTER_SALAD_API_KEY", "CLIPCUTTER_WORKER_API_TOKEN",
        "CLIPCUTTER_YOUTUBE_DISPATCH_ENABLED", "CLIPCUTTER_DRIVE_DELIVERY_ENABLED",
        "CLIPCUTTER_APPROVED_DRIVE_OUTPUT_FOLDERS", "CLIPCUTTER_DRIVE_DELIVERY_REMOTE"}
    if not required <= set(values) or set(values) - required - gpu - optional:
        raise SystemExit("Missing or unexpected private configuration keys")
    for key in ("CLIPCUTTER_SCHEDULER_ENABLED", "CLIPCUTTER_LIFECYCLE_ENABLED",
                "CLIPCUTTER_YOUTUBE_DISPATCH_ENABLED", "CLIPCUTTER_DRIVE_DELIVERY_ENABLED"):
        if key in values and values[key] not in ("0", "1"):
            raise SystemExit("Invalid private feature flag")
    if gpu & set(values):
        if not gpu <= set(values):
            raise SystemExit("Incomplete private GPU configuration")
        if values["CLIPCUTTER_APPROVED_OWNER"].casefold() != values["CLIPCUTTER_ADMIN_USERNAME"].casefold():
            raise SystemExit("GPU owner must match configured admin")
        slug = r"[a-z][a-z0-9-]{0,61}[a-z0-9]"
        if not re.fullmatch(r"/organizations/"+slug+r"/projects/"+slug+r"/containers/clipcutter-gpu", values["CLIPCUTTER_APPROVED_SALAD_GROUP"]):
            raise SystemExit("Invalid approved ClipCutter group")
        gateway = values["CLIPCUTTER_APPROVED_WORKER_GATEWAY"]
        try:
            u = urlsplit(gateway)
            valid = (u.scheme == "https" and u.hostname and u.hostname.endswith(".salad.cloud")
                     and u.username is None and u.password is None and u.port in (None,443)
                     and u.path in ("","/") and not u.query and not u.fragment
                     and not any(ch.isspace() for ch in gateway))
        except ValueError:
            valid = False
        if not valid:
            raise SystemExit("Invalid approved worker gateway")
        if not re.fullmatch(r"[a-f0-9]{40}", values["CLIPCUTTER_APPROVED_WORKER_SHA"]):
            raise SystemExit("Invalid approved worker SHA")
        if not re.fullmatch(r"ghcr\.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test@sha256:[a-f0-9]{64}", values["CLIPCUTTER_APPROVED_GPU_IMAGE"]):
            raise SystemExit("Invalid approved GPU digest")
    if "CLIPCUTTER_WORKER_API_TOKEN" in values and len(values["CLIPCUTTER_WORKER_API_TOKEN"]) < 32:
        raise SystemExit("Invalid private worker token")
    if "CLIPCUTTER_SALAD_API_KEY" in values and not values["CLIPCUTTER_SALAD_API_KEY"]:
        raise SystemExit("Missing private Salad API key")
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
