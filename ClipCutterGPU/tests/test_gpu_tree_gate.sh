#!/usr/bin/env bash
set -Eeuo pipefail
GATE="$(cd "$(dirname "$0")/.." && pwd)/check-main-gpu-tree.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git init -q -b main "$WORK/upstream"
git -C "$WORK/upstream" config user.name Test
git -C "$WORK/upstream" config user.email test@example.invalid
mkdir "$WORK/upstream/ClipCutterGPU" "$WORK/upstream/ClipCutterWeb"
echo gpu-v1 > "$WORK/upstream/ClipCutterGPU/worker.txt"
echo web-v1 > "$WORK/upstream/ClipCutterWeb/app.txt"
git -C "$WORK/upstream" add .
git -C "$WORK/upstream" commit -qm initial
SHA="$(git -C "$WORK/upstream" rev-parse HEAD)"
git clone -q --depth=1 "file://$WORK/upstream" "$WORK/pinned"
cd "$WORK/pinned"
bash "$GATE" "$SHA" "file://$WORK/upstream"
echo web-v2 > "$WORK/upstream/ClipCutterWeb/app.txt"
git -C "$WORK/upstream" commit -qam web-only
bash "$GATE" "$SHA" "file://$WORK/upstream"
[[ "$(git rev-parse HEAD)" == "$SHA" ]]
echo gpu-v2 > "$WORK/upstream/ClipCutterGPU/worker.txt"
git -C "$WORK/upstream" commit -qam gpu-change
if bash "$GATE" "$SHA" "file://$WORK/upstream"; then echo 'GPU change incorrectly accepted' >&2; exit 1; fi
if bash "$GATE" "$SHA" "file://$WORK/missing"; then echo 'Unavailable remote incorrectly accepted' >&2; exit 1; fi
echo GPU_TREE_GATE_TESTS=PASS
