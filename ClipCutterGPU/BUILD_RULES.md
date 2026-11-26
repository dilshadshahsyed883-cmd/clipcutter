# ClipCutter GPU candidate — Concat build rules

Reference: concat/main 84bcb11b72263caa6ad9c021d5d07f4dff53cc46, .github/workflows/concat-salad-candidate.yml and tools/release_image_smoke.py.

- Separate image: ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-candidate:<full-main-SHA>. No latest tag, no overwrite/reuse of existing published SHA tag, no Concat package changes.
- Build from reviewed exact canonical main and a clean checkout. Git archive includes only ClipCutterGPU; no Web service, desktop, private inputs, model weights or credentials in context. linux/amd64; revision/source OCI labels and embedded source SHA.
- Build validation: import/compile, exact source hashes inside image, request contracts, synthetic CPU extraction and verified output, liveness and authenticated capabilities, honest not-ready status without GPU. Any failure blocks publication.
- Root policy now allows non-EXE workflows. GitHub Actions runs the same candidate build gates on PRs without publishing, and on GPU-source changes merged to main or manual dispatch on main. GHCR publication occurs only after smoke tests succeed. No EXE, Salad deployment or billing action.
- The main-only workflow authenticates GHCR with its scoped packages-write GITHUB_TOKEN, checks for existing tag, then pushes that exact image and records the registry repo digest plus image ID/source SHA/smoke JSON. A manual builder still requires explicit publication approval. Deploy by digest only after approval. Tag immutability is procedural unless registry policy enforces it. Never publish from a failed smoke test or reuse an existing SHA tag.
- The base is version-tagged, not digest-pinned, and transitive packages are not fully hash locked yet. Record resolved base and dependency versions during first real build; no reproducibility claim until those are pinned. Dependency and CUDA compatibility remain untested.
- GPU acceptance is separate: compatible authorized SCRFD/ArcFace weights staged read-only at /models with SHA-256 verification, license confirmation, real GPU warmup and actual media acceptance. No automatic or unlicensed weight download. Do not mark ready just from container launch; no GPU tested in CPU image smoke.
- API port 8080. Liveness /health/live; readiness /health/ready (also /health); authenticated /api/capabilities. Local CLI only at this stage; Step 7 adds private job transfer, authenticated dispatch and return, lifecycle and retention controls. Optional analyzer reference/profile input is explicitly rejected until supported; grouping results are anonymous and exclude raw embeddings and crops.

Manual build after merge, on a separate builder (not the existing VPS):
```bash
git clone https://github.com/dilshadshahsyed883-cmd/clipcutter.git
cd clipcutter
git checkout --detach <approved-main-sha>
bash ClipCutterGPU/build-candidate.sh <approved-main-sha>
```

This script does not publish by itself. The reviewed main-only workflow handles publication after CANDIDATE_BUILD=PASS. Build machine must have Docker, registry and PyPI access. No GPU is needed for the synthetic CPU gates; real CUDA tests require a GPU.
