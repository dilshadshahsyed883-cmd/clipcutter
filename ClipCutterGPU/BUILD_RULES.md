# ClipCutter GPU candidate — Concat build rules

Reference: concat/main 84bcb11b72263caa6ad9c021d5d07f4dff53cc46, .github/workflows/concat-salad-candidate.yml and tools/release_image_smoke.py.

- Separate image: ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test:<full-main-SHA>. No latest tag, no overwrite/reuse of existing published SHA tag, no Concat package changes.
- Build from reviewed exact canonical main and a clean checkout. Git archive includes only ClipCutterGPU; no Web service, desktop, private inputs or credentials in context. The builder stages only the two externally supplied authorized PC model files into its temporary context after verification; never commit them to Git. linux/amd64; revision/source OCI labels and embedded source SHA.
- Build validation: import/compile, exact source hashes inside image, request contracts, synthetic CPU extraction and verified output, liveness and authenticated capabilities, honest not-ready status without GPU. Any failure blocks publication.
- Owner build hold: GPU workflow manual-only, build job disabled until explicit finalization approval. Source merges never trigger Docker builds. Future GHCR publication only after authorized model supply, exact approved SHA and smoke gates pass. No EXE, Salad deployment or billing action.
- The main-only workflow authenticates GHCR with its scoped packages-write GITHUB_TOKEN, checks for existing tag, then pushes that exact image and records the registry repo digest plus image ID/source SHA/smoke JSON. A manual builder still requires explicit publication approval. Deploy by digest only after approval. Tag immutability is procedural unless registry policy enforces it. Never publish from a failed smoke test or reuse an existing SHA tag.
- The base is version-tagged, not digest-pinned, and transitive packages are not fully hash locked yet. Record resolved base and dependency versions during first real build; no reproducibility claim until those are pinned. Dependency and CUDA compatibility remain untested.
- GPU acceptance is separate: exact authorized PC SCRFD/ArcFace weights baked into the image read-only at /models with SHA-256 verification, license confirmation, real GPU warmup and actual media acceptance. No automatic or unlicensed weight download. Do not mark ready just from container launch; no GPU tested in CPU image smoke.
- API port 8080. Liveness /health/live; readiness /health/ready (also /health); authenticated /api/capabilities. Local CLI only at this stage; Step 7 adds private job transfer, authenticated dispatch and return, lifecycle and retention controls. Optional analyzer reference/profile input is explicitly rejected until supported; grouping results are anonymous and exclude raw embeddings and crops.

Manual build ONLY after explicit owner finalization and model rights approval, on a separate builder (not existing VPS); supply CLIPCUTTER_FINAL_APPROVED_SHA, CLIPCUTTER_MODEL_REDISTRIBUTION_AUTHORIZED=1 and CLIPCUTTER_AUTHORIZED_MODEL_DIR in its secure environment:
```bash
git clone https://github.com/dilshadshahsyed883-cmd/clipcutter.git
cd clipcutter
git checkout --detach <approved-main-sha>
bash ClipCutterGPU/build-candidate.sh <approved-main-sha>
```

This script does not publish by itself. The reviewed main-only workflow handles publication after CANDIDATE_BUILD=PASS. Build machine must have Docker, registry and PyPI access. No GPU is needed for the synthetic CPU gates; real CUDA tests require a GPU.

## Private non-commercial research testing only
Owner approved a dedicated private testing image; never publish packaged models into the existing candidate package. Before building, verify dedicated GHCR package metadata is private using verify-private-package.py and a secure package-read credential. Verify again immediately before and after push. New package must first be established with a model-free seed, private visibility independently confirmed, and access restricted to approved accounts. Do not rely on repository visibility, which is public. Use exact digest for Salad, a separate read-only registry credential and separate worker token. Private visibility does not grant rights to model weights. No production or monetized use on research-only terms. Actual authorization and files, private package creation, CI model supply, transport and acceptance are still outstanding. Build remains disabled.

## Superseding owner-directed educational build exception

Owner explicitly requested the model-inclusive private educational image build
and assumes licensing responsibility. For this build, vendor written
clarification is not a blocking prerequisite; no third-party packaging rights
or commercial license are represented as verified. The manual workflow requires
an exact approved current-main SHA and private educational confirmation. The
builder uses `CLIPCUTTER_PRIVATE_EDUCATIONAL_APPROVED=1` instead of representing
redistribution rights as verified. Private package verification, pinned model
hashes, all smoke gates, immutable tags and digest verification remain required.
This supersedes historical build-disabled statements for this testing build.
No Salad start, paid GPU usage, Concat changes, EXE or VPS deployment.
