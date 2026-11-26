#!/usr/bin/env bash
# Separate, manual HTTPS activation only after successful loopback stage.
set -Eeuo pipefail
set +x
umask 077
fail(){ echo "BLOCKED: $*" >&2; exit 1; }
[[ "$EUID" == 0 && "$#" == 2 ]] || fail 'sudo bash nginx-cutover.sh activate|rollback <staged-SHA>'
MODE="$1"; SHA="$2"
[[ "$MODE" =~ ^(activate|rollback)$ && "$SHA" =~ ^[a-f0-9]{40}$ ]] || fail 'Invalid mode or SHA'
HOST=clip.scenebuilder.online
SITE=/etc/nginx/sites-available/clipcutter-web.conf
LINK=/etc/nginx/sites-enabled/clipcutter-web.conf
MARK=/etc/clipcutter-web/nginx-managed.sha256
ROOT=/srv/clipcutter-web
CERT=/etc/letsencrypt/live/clip.scenebuilder.online/fullchain.pem
KEY=/etc/letsencrypt/live/clip.scenebuilder.online/privkey.pem
exec 8>/run/lock/clipcutter-web-release.lock
flock -n 8 || fail 'ClipCutter release/cutover already running'
[[ "$(readlink -f "$ROOT/current")" == "$ROOT/releases/$SHA" ]] || fail 'Staged SHA mismatch'
nginx -t >/dev/null 2>&1 || fail 'Nginx invalid'
if [[ "$MODE" == rollback ]]; then
  [[ -f "$MARK" && ! -L "$MARK" && "$(stat -c '%U:%a' "$MARK")" == root:600 ]] || fail 'No managed marker'
  read -r hash pinned < "$MARK"
  [[ "$pinned" == "$SHA" && -f "$SITE" && ! -L "$SITE" && -L "$LINK" && "$(readlink -f "$LINK")" == "$SITE" && "$(sha256sum "$SITE" | awk '{print $1}')" == "$hash" ]] || fail 'Managed route drift'
  # Keep the site file until syntax and reload succeed; restore link on failure.
  rm "$LINK"
  if ! nginx -t || ! systemctl reload nginx; then
    ln -s "$SITE" "$LINK"; nginx -t && systemctl reload nginx || true
    fail 'Rollback failed; original route restored if possible'
  fi
  rm "$SITE" "$MARK"
  echo 'CLIPCUTTER_ROUTE_ROLLED_BACK'
  exit 0
fi
for p in "$SITE" "$LINK" "$MARK"; do
  [[ ! -e "$p" && ! -L "$p" ]] || fail 'Existing ClipCutter path; do not overwrite'
done
[[ -d /etc/nginx/sites-available && -d /etc/nginx/sites-enabled ]] || fail 'Expected Nginx layout missing'
nginx -T 2>/dev/null | python3 -c 'import re,sys; t=re.sub(r"#[^\n]*","",sys.stdin.read()); sys.exit(0 if re.search(r"include\s+/etc/nginx/sites-enabled/\*\s*;",t) and not any("clip.scenebuilder.online" in x.split() for x in re.findall(r"server_name\s+([^;]+);",t)) else 1)' || fail 'Missing include or existing hostname conflict'
[[ "$(getent ahostsv4 "$HOST" | awk '{print $1}' | sort -u)" == 137.74.162.143 ]] || fail 'DNS mismatch'
[[ -r "$CERT" && -r "$KEY" ]] || fail 'Obtain verified host-specific certificate separately'
openssl x509 -in "$CERT" -noout -checkhost "$HOST" | grep -q 'does match certificate' || fail 'Certificate hostname mismatch'
openssl x509 -in "$CERT" -noout -checkend 604800 || fail 'Certificate expires soon'
[[ "$(openssl x509 -in "$CERT" -pubkey -noout | sha256sum)" == "$(openssl pkey -in "$KEY" -pubout | sha256sum)" ]] || fail 'Certificate/key mismatch'
PORT="$(python3 "$ROOT/current/deploy/check-env.py")"
systemctl is-active --quiet clipcutter-web.service || fail 'ClipCutter service inactive'
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/healthz" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)=={"ok":True,"service":"clipcutter-web"} else 1)'
baseline(){ curl -sS --max-time 12 -o /dev/null -w '%{http_code}' "https://$1/"; }
APP_BEFORE="$(baseline app.scenebuilder.online)"
CONCAT_BEFORE="$(baseline concat.scenebuilder.online)"
[[ "$APP_BEFORE" =~ ^[234][0-9]{2}$ && "$CONCAT_BEFORE" =~ ^[234][0-9]{2}$ ]] || fail 'Existing sites not reachable'
CREATED=0; FINISHED=0; LINKED=0; MARKED=0
cleanup(){
  rc=$?
  trap - EXIT
  if (( FINISHED == 0 && CREATED == 1 )); then
    if (( LINKED == 1 )); then rm -f "$LINK"; fi
    if (( MARKED == 1 )); then rm -f "$MARK"; fi
    rm -f "$SITE"
    nginx -t && systemctl reload nginx || echo 'NGINX_RESTORE_FAILED' >&2
  fi
  exit "$rc"
}
trap cleanup EXIT
( set -o noclobber; : > "$SITE" )
CREATED=1
cat > "$SITE" <<CONF
server {
    listen 80;
    server_name clip.scenebuilder.online;
    return 301 https://clip.scenebuilder.online\$request_uri;
}
server {
    listen 443 ssl;
    server_name clip.scenebuilder.online;
    ssl_certificate $CERT;
    ssl_certificate_key $KEY;
    access_log off;
    add_header X-Content-Type-Options nosniff always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    client_max_body_size 4m;
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Auth-User "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Is-Admin "";
    }
}
CONF
chmod 0644 "$SITE"
ln -s "$SITE" "$LINK"; LINKED=1
nginx -t
systemctl reload nginx
curl -fsS --max-time 10 --resolve "$HOST:443:127.0.0.1" "https://$HOST/healthz" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)=={"ok":True,"service":"clipcutter-web"} else 1)'
for p in /dashboard /admin /api/v1/session; do
  [[ "$(curl -sS --max-time 10 --resolve "$HOST:443:127.0.0.1" -o /dev/null -w '%{http_code}' "https://$HOST$p")" == 401 ]] || fail 'HTTPS anonymous check failed'
done
[[ "$(curl -sS --max-time 10 --resolve "$HOST:443:127.0.0.1" -o /dev/null -w '%{http_code}' "https://$HOST/auth/login")" == 200 ]] || fail 'HTTPS login unavailable'
[[ "$(baseline app.scenebuilder.online)" == "$APP_BEFORE" && "$(baseline concat.scenebuilder.online)" == "$CONCAT_BEFORE" ]] || fail 'Existing site response changed'
( set -o noclobber; printf '%s %s\n' "$(sha256sum "$SITE" | awk '{print $1}')" "$SHA" > "$MARK" ); MARKED=1
FINISHED=1
echo 'CLIPCUTTER_HTTPS_ROUTE=PASS'
