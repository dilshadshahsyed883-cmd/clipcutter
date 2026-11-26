#!/usr/bin/env bash
# Upgrade only the existing managed ClipCutter ingress; never modify Concat.
set -Eeuo pipefail
umask 077
fail(){ echo "BLOCKED: $*" >&2; exit 1; }
[[ "$EUID" == 0 && "$#" == 1 && "$1" =~ ^[a-f0-9]{40}$ ]] || fail 'sudo bash nginx-upload-upgrade.sh <staged-SHA>'
SHA="$1"
ROOT=/srv/clipcutter-web
SITE=/etc/nginx/sites-available/clipcutter-web.conf
LINK=/etc/nginx/sites-enabled/clipcutter-web.conf
MARK=/etc/clipcutter-web/nginx-managed.sha256
HOST=clip.scenebuilder.online
exec 8>/run/lock/clipcutter-web-release.lock
flock -n 8 || fail 'ClipCutter deployment lock held'
[[ "$(readlink -f "$ROOT/current")" == "$ROOT/releases/$SHA" ]] || fail 'Staged SHA mismatch'
[[ -f "$MARK" && ! -L "$MARK" && "$(stat -c '%U:%a' "$MARK")" == root:600 ]] || fail 'Missing managed marker'
read -r HASH PINNED < "$MARK"
[[ "$PINNED" =~ ^[a-f0-9]{40}$ && -f "$SITE" && ! -L "$SITE" && -L "$LINK" && "$(readlink -f "$LINK")" == "$SITE" && "$(sha256sum "$SITE" | awk '{print $1}')" == "$HASH" ]] || fail 'Managed route drift'
nginx -t
PORT="$(python3 "$ROOT/current/deploy/check-env.py")"
[[ "$PORT" =~ ^[0-9]+$ ]] || fail 'Invalid port'
systemctl is-active --quiet clipcutter-web.service || fail 'ClipCutter service inactive'
baseline(){ curl -sS --max-time 12 -o /dev/null -w '%{http_code}' "https://$1/"; }
APP_BEFORE="$(baseline app.scenebuilder.online)"
CONCAT_BEFORE="$(baseline concat.scenebuilder.online)"
[[ "$APP_BEFORE" =~ ^[234][0-9]{2}$ && "$CONCAT_BEFORE" =~ ^[234][0-9]{2}$ ]] || fail 'Existing sites not reachable'
BACKUP="$(mktemp -d /var/backups/clipcutter-web/nginx-upload.XXXXXXXX)"
cp -p "$SITE" "$BACKUP/site"; cp -p "$MARK" "$BACKUP/marker"
python3 - "$SITE" "$ROOT/current/deploy/nginx-upload-location.conf" "$PORT" "$BACKUP/candidate" <<'PY'
from pathlib import Path
import sys
site, snippet, port, dest=sys.argv[1:]
old=Path(site).read_text()
location=Path(snippet).read_text().replace("__PORT__",port)
anchor="    client_max_body_size 4m;\n    location / {"
if location in old:
    updated=old
elif old.count(anchor)==1 and "location = /api/v1/studio/requests/upload" not in old and old.count("server_name clip.scenebuilder.online;")==2 and f"proxy_pass http://127.0.0.1:{port};" in old:
    updated=old.replace(anchor,"    client_max_body_size 4m;\n"+location+"    location / {",1)
else:
    raise SystemExit("Unexpected site layout; manual review required")
Path(dest).write_text(updated)
PY
CHANGED=0; DONE=0
cleanup(){
  rc=$?
  trap - EXIT
  if (( CHANGED == 1 && DONE == 0 )); then
    cp -p "$BACKUP/site" "$SITE"
    cp -p "$BACKUP/marker" "$MARK"
    nginx -t && systemctl reload nginx || echo NGINX_RESTORE_FAILED >&2
  fi
  exit "$rc"
}
trap cleanup EXIT
CHANGED=1
install -o root -g root -m 0644 "$BACKUP/candidate" "$SITE"
nginx -t
systemctl reload nginx
curl -fsS --max-time 10 --resolve "$HOST:443:127.0.0.1" "https://$HOST/healthz" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)=={"ok":True,"service":"clipcutter-web"} else 1)'
[[ "$(baseline app.scenebuilder.online)" == "$APP_BEFORE" && "$(baseline concat.scenebuilder.online)" == "$CONCAT_BEFORE" ]] || fail 'Existing site response changed'
printf '%s %s\n' "$(sha256sum "$SITE" | awk '{print $1}')" "$SHA" > "$MARK"
DONE=1
echo 'CLIPCUTTER_REFERENCE_UPLOAD_ROUTE=PASS'
echo "Backup: $BACKUP"
