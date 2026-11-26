#!/usr/bin/env bash
# Manual isolated Docker builder only. No VPS/Salad provisioning and no automatic push.
set -Eeuo pipefail
set +x
umask 077
[[ "$#" == 1 && "$1" =~ ^[a-f0-9]{40}$ ]] || { echo "Usage: bash ClipCutterGPU/build-candidate.sh <approved-main-sha>" >&2; exit 1; }
SHA="$1"
# Owner must explicitly approve final SHA and lawful redistribution before this build.
[[ "${CLIPCUTTER_FINAL_APPROVED_SHA:-}" == "$SHA" && "${CLIPCUTTER_MODEL_REDISTRIBUTION_AUTHORIZED:-}" == 1 ]] || { echo "Final build and model rights approval required" >&2; exit 1; }
[[ -n "${CLIPCUTTER_AUTHORIZED_MODEL_DIR:-}" ]] || { echo "Authorized local model directory required" >&2; exit 1; }
# Do not even build licensed model layers until the dedicated package is verified private.
python3 "$(dirname "$0")/verify-private-package.py"

REPO="https://github.com/dilshadshahsyed883-cmd/clipcutter.git"
ROOT="$(git rev-parse --show-toplevel)"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || { echo "Checkout SHA mismatch"; exit 1; }
if [[ "${GITHUB_ACTIONS:-}" == true && "${GITHUB_EVENT_NAME:-}" == pull_request ]]; then
  [[ "${GITHUB_SHA:-}" == "$SHA" ]] || { echo "PR checkout mismatch"; exit 1; }
else
  [[ "$(git ls-remote --exit-code "$REPO" refs/heads/main | awk '{print $1}')" == "$SHA" ]] || { echo "Approved SHA must match remote main"; exit 1; }
fi
[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]] || { echo "Clean checkout required"; exit 1; }
for c in docker python3 openssl; do command -v "$c" >/dev/null; done
IMAGE="ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test:$SHA"
WORK="$(mktemp -d)"
REPORT="$(mktemp -d "${TMPDIR:-/tmp}/clipcutter-image-report.XXXXXXXX")"
NAME="clipcutter-smoke-$(openssl rand -hex 8)"
cleanup(){ docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf -- "$WORK"; }
trap cleanup EXIT
mkdir "$WORK/src"
if git -C "$ROOT" ls-tree -r "$SHA" ClipCutterGPU/ | grep -E '^(120000|160000) ' ; then echo "Unexpected symlink or submodule"; exit 1; fi
git -C "$ROOT" archive "$SHA:ClipCutterGPU" | tar -xf - -C "$WORK/src"
# External authorized files only. Never commit weights or credentials.
python3 "$WORK/src/worker/model_pins.py" "$CLIPCUTTER_AUTHORIZED_MODEL_DIR"
mkdir "$WORK/src/models"
for model in det_10g.onnx w600k_r50.onnx; do
  install -m 0444 "$CLIPCUTTER_AUTHORIZED_MODEL_DIR/$model" "$WORK/src/models/$model"
done
python3 "$WORK/src/worker/model_pins.py" "$WORK/src/models"
# The mount is read-only and must be readable by nonroot UID 10001 in the container.
chmod 0755 "$WORK" "$WORK/src"
chmod -R a+rX "$WORK/src"
docker build --platform linux/amd64 --build-arg SOURCE_SHA="$SHA" \
  --label "org.opencontainers.image.source=$REPO" --label "org.opencontainers.image.revision=$SHA" \
  -t "$IMAGE" "$WORK/src"
docker run --rm --network none --entrypoint python -e EXPECTED_SOURCE_SHA="$SHA" \
  -v "$WORK/src:/src:ro" "$IMAGE" -m tests.smoke > "$REPORT/image-smoke.json"
docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE" | grep -Fx "$SHA"
export SMOKE_TOKEN="$(openssl rand -hex 32)" EXPECTED_SOURCE_SHA="$SHA"
docker run -d --name "$NAME" -p 127.0.0.1::8080 -e CLIPCUTTER_WORKER_API_TOKEN="$SMOKE_TOKEN" "$IMAGE"
export SMOKE_BASE="http://$(docker port "$NAME" 8080/tcp | head -n1)"
python3 "$WORK/src/tests/http_smoke.py"
docker image inspect --format '{{.Id}}' "$IMAGE" > "$REPORT/image-id.txt"
printf '%s\n' "$IMAGE" > "$REPORT/image-tag.txt"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'image=%s\nreport=%s\n' "$IMAGE" "$REPORT" >> "$GITHUB_OUTPUT"
fi
echo "CANDIDATE_BUILD=PASS TAG=$IMAGE REPORT=$REPORT"
echo "Physical GPU, model provisioning and remote transport not verified; no image pushed."
