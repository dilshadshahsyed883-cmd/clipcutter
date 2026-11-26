#!/usr/bin/env bash
# Compare release inputs, excluding Web, desktop and documentation changes.
# Caller pins the reviewed commit; the remote must be the canonical repo.
set -Eeuo pipefail
[[ "$#" == 2 && "$1" =~ ^[a-f0-9]{40}$ ]] || { echo 'Expected approved SHA and remote' >&2; exit 1; }
SHA="$1"; REPO="$2"
ROOT="$(git rev-parse --show-toplevel)"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || { echo 'Checkout SHA mismatch' >&2; exit 1; }
APPROVED_TREE="$(git -C "$ROOT" rev-parse --verify "$SHA:ClipCutterGPU")"
[[ "$(git -C "$ROOT" cat-file -t "$APPROVED_TREE")" == tree ]]
# Fetch main without changing the pinned checkout. Works with shallow Actions clones.
git -C "$ROOT" fetch --quiet --no-tags --depth=1 "$REPO" refs/heads/main
MAIN_SHA="$(git -C "$ROOT" rev-parse --verify FETCH_HEAD)"
MAIN_TREE="$(git -C "$ROOT" rev-parse --verify "$MAIN_SHA:ClipCutterGPU")"
[[ "$(git -C "$ROOT" cat-file -t "$MAIN_TREE")" == tree ]]
# Documentation and release notes are not Docker inputs. Include workflow/build
# policy scripts so an old candidate cannot publish after a relevant change.
if ! git -C "$ROOT" diff --quiet "$SHA" "$MAIN_SHA" -- \
  ClipCutterGPU/Dockerfile \
  ClipCutterGPU/.dockerignore \
  ClipCutterGPU/requirements.txt \
  ClipCutterGPU/worker \
  ClipCutterGPU/tests \
  ClipCutterGPU/build-candidate.sh \
  ClipCutterGPU/check-main-gpu-tree.sh \
  ClipCutterGPU/prepare-models.py \
  ClipCutterGPU/verify-private-package.py \
  ClipCutterGPU/prepare-seed-models.sh \
  .github/workflows/clipcutter-gpu-candidate.yml \
  .github/workflows/clipcutter-gpu-source-tests.yml; then
  echo 'GPU release inputs changed on main; use the new main candidate' >&2
  exit 1
fi
printf 'GPU_TREE_VERIFIED=%s APPROVED_SHA=%s CURRENT_MAIN=%s\n' "$APPROVED_TREE" "$SHA" "$MAIN_SHA"
