# ClipCutter GPU candidate — Concat build rules

Reference: concat/main 84bcb11b72263caa6ad9c021d5d07f4dff53cc46, .github/workflows/concat-salad-candidate.yml and tools/release_image_smoke.py.

- Separate image: ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test:<full-main-SHA>. No latest tag, no overwrite/reuse of existing published SHA tag, no Concat package changes.
- Build from reviewed exact canonical main and a clean checkout. Git archive includes only ClipCutterGPU; no Web service, desktop, private inputs or credentials in context. The builder stages only the two externally supplied authorized PC model files into its temporary context after verification; never commit them to Git. linux/amd64; revision/source OCI labels and embedded source SHA.
- Build validation: import/compile, exact source hashes inside image, request contracts, synthetic CPU extraction and verified output, liveness and authenticated capabilities, honest not-ready status without GPU. Any failure blocks publication.
- Main-only automatic private educational builds are authorized; source tests and all publication gates must pass. No automatic deployment or billing action.
- The main-only workflow authenticates GHCR with its scoped packages-write GITHUB_TOKEN, checks for existing tag, then pushes that exact image and records the registry repo digest plus image ID/source SHA/smoke JSON. A manual builder still requires explicit owner approval. Deploy by digest only after approval. Tag immutability is procedural unless registry policy enforces it. Never publish from a failed smoke test or reuse an existing SHA tag.
- The base is version-tagged, not digest-pinned, and transitive packages are not fully hash locked yet. Record resolved base and dependency versions during first real build; no reproducibility claim until those are pinned. Dependency and CUDA compatibility remain untested.
- GPU acceptance is separate: exact authorized PC SCRFD/ArcFace weights baked into the image read-only at /models with SHA-256 verification, license confirmation, real GPU warmup and actual media acceptance. No automatic or unlicensed weight download. Do not mark ready just from container launch; no GPU tested in CPU image smoke.
- API port 8080. Liveness /health/live; readiness /health/ready (also /health); authenticated /api/capabilities. Local CLI only at this stage; Step 7 adds private job transfer, authenticated dispatch and return, lifecycle and retention controls. Optional analyzer reference/profile input is explicitly rejected until supported; grouping results are anonymous and exclude raw embeddings and crops.

For an explicitly approved manual build on a separate builder (not existing VPS), supply CLIPCUTTER_FINAL_APPROVED_SHA, CLIPCUTTER_PRIVATE_EDUCATIONAL_APPROVED=1 and CLIPCUTTER_AUTHORIZED_MODEL_DIR in its secure environment:
```bash
git clone https://github.com/dilshadshahsyed883-cmd/clipcutter.git
cd clipcutter
git checkout --detach <approved-main-sha>
bash ClipCutterGPU/build-candidate.sh <approved-main-sha>
```

This script does not publish by itself. The reviewed main-only workflow handles publication after CANDIDATE_BUILD=PASS. Build machine must have Docker, registry and PyPI access. No GPU is needed for the synthetic CPU gates; real CUDA tests require a GPU.

## Private non-commercial research testing only
Owner approved a dedicated private testing image; never publish packaged models into the existing candidate package. Before building, verify dedicated GHCR package metadata is private using verify-private-package.py and a secure package-read credential. Verify again immediately before and after push. New package must first be established with a model-free seed, private visibility independently confirmed, and access restricted to approved accounts. Do not rely on repository visibility, which is public. Use exact digest for Salad, a separate read-only registry credential and separate worker token. Private visibility does not grant rights to model weights. No production or monetized use on research-only terms. Physical GPU/media acceptance and deployment remain separate. The private seed supplies exact pinned models for authorized testing.

## Current owner-approved automatic private GPU release policy

Automatic candidate builds are authorized for private, non-commercial educational testing only when GPU build inputs or GPU release workflow changes merge into main. This standing approval replaces the manual-only/each-build approval requirement and earlier build holds. Manual dispatch remains available with exact main SHA and explicit confirmation. No third-party redistribution rights or commercial license are represented as verified. No desktop EXE, Concat changes, automatic Salad deployment/start, paid GPU use, or VPS deployment.

- Build the exact main event SHA after source regression tests pass, with a clean checkout, pinned model hashes, private GHCR checks before staging and immediately before/after publication, CPU/image/HTTP smoke gates, immutable SHA tags and verified registry digest. No overwrites; check existing tags before building. Keep prior images for rollback.
- Automatic build paths: GPU Dockerfile, .dockerignore, requirements, worker/, tests/, build and model staging/verification scripts, and GPU release/source-test workflows. Documentation, release notes, Web and desktop-only changes never trigger GPU builds. In-flight builds compare these same inputs against latest main; unrelated changes do not invalidate the image. If relevant inputs change, the old candidate fails closed and a new main-event build handles the new inputs.
- Serialize builds for main; do not cancel running builds on Web changes. Pending runs may coalesce to the latest relevant main event.
- Permanent model supply: use the previously verified private GHCR seed by immutable digest, copy only the two exact pinned model files without executing the seed, and verify size/SHA256 again. Preserve that seed image. Optional owner-supplied Drive ID/HTTPS ZIP secret overrides the seed; never commit credentials or model files. Registry access or model verification failure blocks publication. No runtime download.
- Image publication is not deployment or physical GPU/media acceptance. Deployment remains separately authorized.
