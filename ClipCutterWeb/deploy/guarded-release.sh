#!/usr/bin/env bash
# Manual VPS terminal only. No public ingress changes or other service control.
set -Eeuo pipefail
set +x
umask 077
fail(){ printf 'BLOCKED: %s\n' "$*" >&2; exit 1; }
[[ "$EUID" == 0 && "$#" == 2 ]] || fail 'sudo clipcutter-web-deploy <40-hex-main-SHA> bootstrap|preflight|stage'
SHA="$1"; MODE="$2"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail 'Exact SHA required'
[[ "$MODE" =~ ^(bootstrap|preflight|stage)$ ]] || fail 'Unknown mode'
REPO=https://github.com/dilshadshahsyed883-cmd/clipcutter.git
ROOT=/srv/clipcutter-web
DATA=/var/lib/clipcutter-web
CONF=/etc/clipcutter-web
BACKUPS=/var/backups/clipcutter-web
UNIT=/etc/systemd/system/clipcutter-web.service
HELPER=/usr/local/sbin/clipcutter-web-deploy
USER_NAME=clipcutterweb
for c in git python3 tar systemctl nginx curl flock runuser install ss sha256sum; do
  command -v "$c" >/dev/null || fail "Missing prerequisite $c"
done
exec 8>/run/lock/clipcutter-web-release.lock
flock -n 8 || fail 'ClipCutter release/cutover already running'
nginx -t >/dev/null 2>&1 || fail 'Existing Nginx invalid'
export GIT_TERMINAL_PROMPT=0
remote_main(){ git ls-remote --exit-code "$REPO" refs/heads/main | awk '{print $1}'; }
[[ "$(remote_main)" == "$SHA" ]] || fail 'Approved SHA does not match remote main'
WORK="$(mktemp -d /root/clipcutter-release.XXXXXXXX)"
STAGE=''; OLD=''; PROMOTED=0; DONE=0
cleanup(){
  local rc=$?
  trap - EXIT
  if (( PROMOTED == 1 && DONE == 0 )); then
    if [[ -n "$OLD" && -d "$OLD" ]]; then
      ln -s "$OLD" "$ROOT/.rollback-$SHA" && mv -Tf "$ROOT/.rollback-$SHA" "$ROOT/current" && systemctl restart clipcutter-web.service || echo 'ROLLBACK_SERVICE_FAILED' >&2
    else
      systemctl stop clipcutter-web.service || echo 'ROLLBACK_STOP_FAILED' >&2
      rm -f "$ROOT/current"
    fi
    echo 'CLIPCUTTER_ONLY_ROLLBACK_ATTEMPTED' >&2
  fi
  if [[ -n "$STAGE" && "$STAGE" == "$ROOT/releases/$SHA" && "$DONE" == 0 ]]; then
    # Keep failed candidate for inspection; no persistent state is removed.
    echo "FAILED_CANDIDATE_RETAINED=$STAGE" >&2
  fi
  rm -rf -- "$WORK"
  exit "$rc"
}
trap cleanup EXIT
git clone --quiet --depth 1 --branch main "$REPO" "$WORK/source"
[[ "$(git -C "$WORK/source" rev-parse HEAD)" == "$SHA" ]] || fail 'Clone SHA mismatch'
git -C "$WORK/source" ls-tree -r "$SHA" ClipCutterWeb/ > "$WORK/tree"
[[ -s "$WORK/tree" ]] || fail 'Web subtree missing'
if grep -Eq '^(120000|160000) ' "$WORK/tree"; then fail 'Symlink/submodule in web release'; fi
git -C "$WORK/source" archive --format=tar "$SHA:ClipCutterWeb" > "$WORK/web.tar"
DIGEST="$(sha256sum "$WORK/web.tar" | awk '{print $1}')"
mkdir "$WORK/web"
tar -xf "$WORK/web.tar" -C "$WORK/web" --no-same-owner
SRC="$WORK/web"
for f in run.py requirements.txt deploy/clipcutter-web.service deploy/guarded-release.sh deploy/check-env.py deploy/init-local-admin.py; do
  [[ -f "$SRC/$f" ]] || fail "Missing release file $f"
done
bash -n "$SRC/deploy/guarded-release.sh"
bash -n "$SRC/deploy/nginx-cutover.sh"
safe_dir(){
  local p="$1" owner="$2" mode="$3"
  if [[ -e "$p" || -L "$p" ]]; then
    [[ -d "$p" && ! -L "$p" && "$(stat -c '%U:%a' "$p")" == "$owner:$mode" ]] || fail "Unsafe directory $p"
  else
    install -d -o "$owner" -g "$(id -gn "$owner")" -m "$mode" "$p"
  fi
}
if [[ "$MODE" == bootstrap ]]; then
  if ! id "$USER_NAME" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$DATA" --shell /usr/sbin/nologin "$USER_NAME"
  fi
  [[ "$(id -u "$USER_NAME")" != 0 && "$(getent passwd "$USER_NAME" | cut -d: -f6)" == "$DATA" ]] || fail 'Unexpected service identity'
  safe_dir "$ROOT" root 755
  safe_dir "$ROOT/releases" root 755
  safe_dir "$DATA" "$USER_NAME" 700
  safe_dir "$CONF" root 700
  safe_dir "$BACKUPS" root 700
  for p in "$UNIT" "$HELPER"; do
    [[ ! -L "$p" ]] || fail 'Unsafe existing service/helper link'
  done
  if [[ -e "$UNIT" ]]; then cmp -s "$UNIT" "$SRC/deploy/clipcutter-web.service" || fail 'Existing unit differs; manual review required'
  else install -o root -g root -m 0644 "$SRC/deploy/clipcutter-web.service" "$UNIT"; fi
  if [[ -e "$HELPER" ]]; then cmp -s "$HELPER" "$SRC/deploy/guarded-release.sh" || fail 'Existing helper differs; manual review required'
  else install -o root -g root -m 0750 "$SRC/deploy/guarded-release.sh" "$HELPER"; fi
  systemctl daemon-reload
  echo 'BOOTSTRAP=PASS SERVICE_NOT_STARTED'
  echo 'Provision independent private admin via pinned deploy/init-local-admin.py before preflight.'
  DONE=1; exit 0
fi
for p in "$ROOT" "$ROOT/releases" "$DATA" "$CONF" "$BACKUPS"; do
  [[ -d "$p" && ! -L "$p" ]] || fail "Missing safe bootstrap path $p"
done
[[ "$(stat -c '%U:%a' "$ROOT")" == root:755 && "$(stat -c '%U:%a' "$ROOT/releases")" == root:755 && "$(stat -c '%U:%a' "$CONF")" == root:700 && "$(stat -c '%U:%a' "$BACKUPS")" == root:700 && "$(stat -c '%U:%a' "$DATA")" == "$USER_NAME:700" ]] || fail 'Bootstrap directory permissions changed'
[[ -f "$UNIT" && ! -L "$UNIT" && "$(stat -c '%U:%a' "$UNIT")" == root:644 ]] || fail 'Private systemd unit not installed'
cmp -s "$UNIT" "$SRC/deploy/clipcutter-web.service" || fail 'Unit changed; review separately'
[[ -f "$HELPER" && ! -L "$HELPER" && "$(stat -c '%U:%a' "$HELPER")" == root:750 ]] || fail 'Private deploy helper missing'
PORT="$(python3 "$SRC/deploy/check-env.py")"
if [[ -L "$ROOT/current" ]]; then
  OLD="$(readlink -f "$ROOT/current")"
  [[ "$OLD" =~ ^/srv/clipcutter-web/releases/[0-9a-f]{40}$ && -d "$OLD" ]] || fail 'Unexpected current release'
elif [[ -e "$ROOT/current" ]]; then fail 'Current must be a symlink'; fi
if systemctl is-active --quiet clipcutter-web.service; then
  [[ -n "$OLD" ]] || fail 'Unexpected running service without selected release'
  curl -fsS --max-time 8 "http://127.0.0.1:$PORT/healthz" | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x=={"ok":True,"service":"clipcutter-web"}' || fail 'Configured port does not identify active ClipCutter'
else
  [[ -z "$(ss -H -ltn "sport = :$PORT")" ]] || fail 'Configured loopback port occupied'
fi
echo "PREFLIGHT=PASS SHA=$SHA ARCHIVE_SHA256=$DIGEST"
if [[ "$MODE" == preflight ]]; then DONE=1; exit 0; fi
STAGE="$ROOT/releases/$SHA"
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] || fail 'Candidate already exists; inspect rather than overwrite'
install -d -o root -g root -m 0755 "$STAGE"
tar -xf "$WORK/web.tar" -C "$STAGE" --no-same-owner
find "$STAGE" -type d -exec chmod 0755 {} +
find "$STAGE" -type f -exec chmod 0644 {} +
# Install only in this release-specific virtual environment; never into system Python.
install -d -o "$USER_NAME" -g "$(id -gn "$USER_NAME")" -m 0755 "$STAGE/.venv"
runuser -u "$USER_NAME" -- env -i PATH=/usr/bin:/bin HOME="$DATA" python3 -m venv "$STAGE/.venv"
runuser -u "$USER_NAME" -- env -i PATH=/usr/bin:/bin HOME="$DATA" "$STAGE/.venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir -r "$STAGE/requirements.txt"
chown -hR root:root "$STAGE/.venv"
# Tests use disposable configuration, never the live environment. No EXE/CI build.
(
  cd "$STAGE"
  runuser -u "$USER_NAME" -- env -i PATH=/usr/bin:/bin HOME="$DATA" PYTHONDONTWRITEBYTECODE=1 "$STAGE/.venv/bin/python" -m unittest discover -s tests -v
)
[[ "$(remote_main)" == "$SHA" ]] || fail 'Main changed while testing; no promotion'
BACKUP="$(mktemp -d "$BACKUPS/release.XXXXXXXX")"
cp -p "$CONF/clipcutter-web.env" "$BACKUP/private-env"
cp -p "$UNIT" "$BACKUP/service"
cp -p "$HELPER" "$BACKUP/helper"
printf '%s\n' "$OLD" > "$BACKUP/previous-release"
printf '%s\n' "$DIGEST" > "$BACKUP/archive-sha256"
python3 - "$DATA" "$BACKUP" <<'PY'
from pathlib import Path
import sqlite3, sys
from urllib.parse import quote
root, backup = Path(sys.argv[1]), Path(sys.argv[2]) / "sqlite"
for source in root.rglob("*.sqlite3"):
    if source.is_symlink() or not source.is_file() or source.resolve() != source:
        raise SystemExit("Unsafe SQLite source")
    target = backup / source.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect("file:" + quote(str(source), safe="/") + "?mode=ro", uri=True, timeout=10) as old, sqlite3.connect(target) as saved:
        old.backup(saved)
    target.chmod(0o600)
print("SQLITE_BACKUP=PASS")
PY
[[ ! -e "$ROOT/.next-$SHA" && ! -L "$ROOT/.next-$SHA" ]] || fail 'Unexpected promotion link'
ln -s "$STAGE" "$ROOT/.next-$SHA"
mv -Tf "$ROOT/.next-$SHA" "$ROOT/current"
PROMOTED=1
systemctl restart clipcutter-web.service
BASE="http://127.0.0.1:$PORT"
for ((i=0;i<25;i++)); do
  if curl -fsS --max-time 2 "$BASE/healthz" | python3 -c 'import json,sys; x=json.load(sys.stdin); assert x=={"ok":True,"service":"clipcutter-web"}' 2>/dev/null; then break; fi
  sleep 1
done
curl -fsS --max-time 5 "$BASE/healthz" | python3 -c 'import json,sys; assert json.load(sys.stdin)=={"ok":True,"service":"clipcutter-web"}'
for p in /dashboard /admin /api/v1/session /studio/extractor /studio/analyzer; do
  [[ "$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "$BASE$p")" == 401 ]] || fail "Anonymous access check failed: $p"
done
[[ "$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "$BASE/auth/login")" == 200 ]] || fail 'Login unavailable'
systemctl is-active --quiet clipcutter-web.service
DONE=1
echo "STAGED_SHA=$SHA BACKUP=$BACKUP PUBLIC_NGINX=UNCHANGED"
