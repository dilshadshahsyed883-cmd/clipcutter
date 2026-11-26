#!/usr/bin/env bash
# Compare only the GPU build context, not the changing monorepo HEAD.
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
[[ "$MAIN_TREE" == "$APPROVED_TREE" ]] || { echo 'GPU source changed on main; approve a new GPU build' >&2; exit 1; }
printf 'GPU_TREE_VERIFIED=%s APPROVED_SHA=%s CURRENT_MAIN=%s\n' "$APPROVED_TREE" "$SHA" "$MAIN_SHA"
