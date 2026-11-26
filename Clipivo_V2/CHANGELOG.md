# V2.3 extractor parity restoration — 26 November 2026

- Restore original v0.7.7 checksum-verified model discovery for Clip Extractor and Batch; isolate Person Analyzer model settings.
- Restore original upstream runtime pins, retain psutil for Studio, and reconcile existing AppData environments when requirements change.
- Preserve original face/scan UI and matching code, optional clip limits, existing data and all six tabs. Source-level verification only; actual Windows inference parity pending.

# V2.3 source runtime policy — 26 November 2026

- Enforce the existing LocalAppData source runtime path; stop if LOCALAPPDATA is unset and suppress application bytecode cache writes during source launch.
- Document that legacy source-local virtual environments are ignored, not automatically removed, and must never be included in source ZIPs. Static launcher review only; Windows launch not tested. No EXE build or workflow changes.

# V2.3 combined integration — 26 November 2026

- Integrated exact Agent 1, Agent 2 and Agent 3 source checkpoints, retaining original extractor and six workspaces.
- Confirmed-person matching contract retained; corrected old multi-person test and aligned CapCut fixtures with canonical reviewed plans.
- Prevented repeated source files across indexed scenes when source reuse is off; added capacity-aware allocation and validation.
- Moved scene matching and picker computation/footage lookup into cancellable background tasks; preserved analyzer busy/extractor transfer lifecycle and added replacement shutdown guard.
- Verified focused integrated backend tests (9 passed) and corrected identity assertions. Full regression, native Node rerun and Qt navigation remain unverified; see TEST_REPORT.md.
- No build, package, workflow change or main merge. Review PR only.

# V2.3 development checkpoint

- Reused original Clipivo Qt extractor and V2.2 analyzer services in six workspaces.
- Added replacement review/index/render services, persistent settings and encrypted embedding profiles.
- Reused Rajudesktop CapCut writer logic and adapted optional clip speed.
- Ported the relevant Concat clip-selection logic; added strict min/max controls and draft same-person gap fill.
- Saved work before further fixes/acceptance, as requested. See TEST_REPORT.md and ../docs/STATUS.md.
