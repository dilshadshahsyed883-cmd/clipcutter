# Revised Step 4 and Step 5 — web only

Owner clarified that ClipCutter Web is the Concat-style VPS control plane, not a processing engine. This branch starts from main b7ae1894dac0de1909a7bbc36a188cda02a986f2, deliberately excludes the separate experimental worker PR #3, and preserves its source without merging it. No models, FFmpeg processing, CUDA, ONNX, desktop core imports, GPU image or worker provisioning in this PR.

## Implemented source
- Exactly two Studio tabs. Extractor: source, reference images, manual A/B ranges, scan and cut options, framing, output, audio, optional strict duration. Analyzer: source, optional reference inputs, sample interval, similarity, background/static face controls and ignore regions. Settings are requested options only, not evidence a future worker supports them.
- Drive file/ZIP/folder input links and optional output folder. No external links fetched yet. Owner-scoped SQLite request ledger, persisted request IDs, retry-safe creation, conflicts on changed payload, cancellation before intake and polling of stored status. No synthetic progress.
- Owner-protected output listing, download and inline MP4 access; internal transition and receipt interface checks allowed state, size and SHA-256 before publishing. No public worker receiver or untrusted status callback.
- All browser changes authenticated; mutations require CSRF. No external service account secrets or copied credentials.
- Source regression tests include both contracts, isolation, idempotency, cancellation, unverified output exclusion and verified receipt. Execute source tests before merge. Browser behavior and real delivery need later acceptance.

## Remaining boundaries
Step 6: independently implement/build the single GPU worker image; validate its contract compatibility, model licenses and actual processing. Step 7: Drive intake/verification and verified output delivery, authenticated worker transport, persistent scheduler and Concat-style SaladCloud lifecycle. Implement profile/result retention and deletion before enabling biometric input. Step 8: full end-to-end acceptance. Step 9: guarded deployment to the existing VPS, including migration of its previously provisioned environment/unit and adoption of its existing HTTPS placeholder. No deployment performed here.

This is the web request/control source candidate, not a working production processing pipeline. The Drive link controls intentionally save requests in awaiting_input until the intake integration is available.
