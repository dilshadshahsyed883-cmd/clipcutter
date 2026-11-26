# ClipCutter Web

Status: planning only; implementation and deployment pending.

## Approved scope

Independent web application at `clip.scenebuilder.online`, within `ClipCutterWeb/` on the existing clipcutter repository. Exactly two primary tabs: Clip Extractor and Person Analyzer. Use the working Clipivo V2.3.1 desktop implementation as the functional reference; preserve extractor compatibility and reuse suitable headless processing logic after inspection. No Replacement Studio, CapCut integration or other standalone tabs.

## Isolation

Keep web frontend, backend, core adapters, tests, documentation and deployment configuration in this directory. Do not modify the desktop application, archived releases, Concat Web or existing GPU worker for this initial scope. No EXE builds or GitHub Actions build workflows. The web service must run independently of the Windows desktop runtime. Keep runtime dependencies, models, media, job records, secrets and person data outside Git; secure access, isolate user data, and provide deletion controls for biometric data. Verify model licensing before deployment.

## Proposed deployment

DNS A record supplied by owner: `clip.scenebuilder.online` -> `137.74.162.143`, TTL 300. DNS propagation, VPS resources, available ports, reverse proxy, HTTPS, authentication and CPU/GPU processing compatibility must be verified before deployment. Use separate persistent storage and a separate background job queue; preserve existing services. Do not assume a GPU is available on the VPS.

## Next steps

1. Inspect current desktop extractor and analyzer implementations and inventory headless dependencies.
2. Define web UI and API contracts for the two tabs, including persistent person profiles, bounded previews, progress, cancellation and output verification.
3. Implement and test the isolated web application on a development branch before deployment.
4. Verify VPS capacity and configure an independent service and HTTPS without affecting existing hosts.

This file establishes scope only; it does not implement or deploy the application.
