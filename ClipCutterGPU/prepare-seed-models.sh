#!/usr/bin/env bash
# Reuse only exact verified models from the immutable private seed. Never run it.
set -Eeuo pipefail
set +x
umask 077
SEED='ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test@sha256:8b5d854270286d55401c5c633f415cf171096f92a6c2a736af33523244c0dab4'
ROOT="$(git rev-parse --show-toplevel)"
DEST="$RUNNER_TEMP/clipcutter-authorized-models"
[[ ! -e "$DEST" ]] || { echo 'Model destination already exists' >&2; exit 1; }
python3 "$ROOT/ClipCutterGPU/verify-private-package.py"
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin
CID=''
ok=0
cleanup(){
  if [[ -n "$CID" ]]; then docker rm -f "$CID" >/dev/null 2>&1 || true; fi
  docker logout ghcr.io >/dev/null 2>&1 || true
  if [[ "$ok" != 1 ]]; then rm -rf -- "$DEST"; fi
}
trap cleanup EXIT
docker pull "$SEED"
docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$SEED" | grep -Fx "$SEED"
CID="$(docker create "$SEED")"
mkdir -m 0700 "$DEST"
for name in det_10g.onnx w600k_r50.onnx; do
  docker cp "$CID:/models/$name" "$DEST/$name"
  chmod 0400 "$DEST/$name"
done
python3 "$ROOT/ClipCutterGPU/worker/model_pins.py" "$DEST"
printf 'CLIPCUTTER_AUTHORIZED_MODEL_DIR=%s\n' "$DEST" >> "$GITHUB_ENV"
ok=1
echo MODEL_SUPPLY=VERIFIED_PRIVATE_SEED
