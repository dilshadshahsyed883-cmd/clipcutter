# ClipCutter GPU candidate — Concat build rules

Reference: concat/main 84bcb11b72263caa6ad9c021d5d07f4dff53cc46, .github/workflows/concat-salad-candidate.yml and tools/release_image_smoke.py.

- Separate image: ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-candidate:<full-main-SHA>. No latest tag, no overwrite/reuse of existing published SHA tag, no Concat package changes.
- Build from reviewed exact canonical main and a clean checkout. Git archive includes only ClipCutterGPU; no Web service, desktop, private inputs, model weights or credentials in context. linux/amd64; revision/source OCI labels and embedded source SHA.
- Build validation: import/compile, exact source hashes inside image, request contracts, synthetic CPU extraction and verified output, liveness and authenticated capabilities, honest not-ready status without GPU. Any failure blocks publication.
- Candidate build is manual on a separate Docker-capable builder. The existing repository restriction prohibits new GitHub Actions build workflows; the Concat workflow's equivalent manual gates are provided instead. No EXE, CI workflow, automatic publish, deployment or Salad billing action.
- After successful build and review, explicitly authenticate GHCR using a package-write credential on the builder (never paste into chat), confirm tag has never been published, then push that exact image and record the registry repo digest plus image ID/source SHA/smoke JSON. Deploy by digest only after approval. Tag immutability is procedural unless registry policy enforces it. Never publish from a failed smoke test or reuse an existing SHA tag.
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

This script does not publish. Only after CANDIDATE_BUILD=PASS, review the saved reports and authorize the separate push. Build machine must have Docker, registry and PyPI access. No GPU is needed for the synthetic CPU gates; real CUDA tests require a GPU.
