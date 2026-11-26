#!/usr/bin/env bash
# Source-only, disposable test environment. No VPS state/service mutations.
set -Eeuo pipefail
[[ "$EUID" != 0 ]] || { echo 'Run as an unprivileged user, not root' >&2; exit 1; }
cd "$(dirname "$0")/.."
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT
for script in deploy/*.sh; do bash -n "$script"; done
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/python" -m pip install --disable-pip-version-check -r requirements.txt
PYTHONPYCACHEPREFIX="$WORK/cache" "$WORK/venv/bin/python" -m compileall -q app worker run.py tests deploy
env -i PATH=/usr/bin:/bin HOME="$WORK" PYTHONDONTWRITEBYTECODE=1 "$WORK/venv/bin/python" -m unittest discover -s tests -v
echo 'SOURCE_TESTS=PASS'
