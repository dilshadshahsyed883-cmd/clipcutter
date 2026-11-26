# Private testing registry (approved source plan)

The owner stated testing use and approved a private image. The existing GitHub repository is public. Keep it unchanged; never commit model files or credentials. The existing published model-free candidate remains unchanged. Reserve ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test for testing-only model-inclusive images.

## Account-side setup — pending
1. On an authorized builder, seed the new package with a copy of the previous model-free candidate digest sha256:4af797585d1572a2743799bbed8e6a3e211d93e63d720a0344afcb4a0e7fa237 (no GPU build needed), only if the package does not already exist. Verify the source digest first. First-time GHCR packages normally default private; confirm actual visibility in package settings and restrict package access. Do not seed with licensed weights.
2. Confirm package owner, visibility PRIVATE, explicit access and repository Actions access. A public repository is not equivalent to a public package. Never make the model-containing package public.
3. Create a least-privilege classic PAT with read:packages for Salad registry pull. Store only in Salad registry authentication. Use a separately managed owner-scoped read:packages token in the secure builder environment as CLIPCUTTER_PACKAGE_VERIFY_TOKEN (GitHub secret if CI is selected); no tokens in Git, chat or logs. Keep worker API token distinct.
4. Before model-inclusive build, supply authorized exact PC files at CLIPCUTTER_AUTHORIZED_MODEL_DIR, set approved exact SHA and rights confirmation only after verifying research-use and private cloud packaging permission. Public InsightFace buffalo_l models are for non-commercial research, not automatically licensed for commercial deployment or redistribution. No model URLs or downloaded weights in build logs/artifacts.
5. Final build job remains disabled until source finalization, model authorization and private package are all confirmed. CI supply of authorized files still requires a secure method. Verify privacy before Docker build, immediately before push, and after push. Publish immutable SHA/digest, then configure Salad by digest while stopped. Do not start paid GPU without approval.

Refs: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry and https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility ; https://github.com/deepinsight/insightface/blob/master/README.md .

## Manual model-supply preflight

`ClipCutter GPU private preflight (no build)` can be dispatched on main. It verifies
`CLIPCUTTER_PACKAGE_VERIFY_TOKEN` against actual private package metadata, then
stages exactly the two pinned model files in a private runner temporary directory.
For an owner-supplied public Drive ZIP, enter its file ID in `model_drive_id`;
no Drive credentials are used. Alternatively supply a temporary HTTPS archive URL
in the `CLIPCUTTER_MODEL_ZIP_URL` repository secret. Do not paste signed URLs in
workflow inputs. Transfer errors omit URLs and the ZIP and staged files are
removed on completion. Neither preflight nor source merges build or publish.
The existing candidate workflow remains disabled pending finalization and rights
confirmation; model supply alone is not a packaging-license determination.

Local validation: the supplied 176,792,439-byte archive passed exact model
size/SHA256 checks using the staging helper. Unexpected ZIP paths and insecure
URL schemes/embedded credentials were rejected; failed staging was cleaned.
Both workflow YAML files parsed successfully. Docker and CUDA were not run.
