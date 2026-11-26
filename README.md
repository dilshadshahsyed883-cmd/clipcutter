# Clipcutter

Independent Windows desktop video intelligence application based on Clipivo V2.2 and the MIT-licensed upstream Clipivo v0.7.7 source. The current V2.3 implementation is a **work in progress**, saved here at the owner's request. Fixes and further validation are deferred.

## Source

- `Clipivo_V2/`: the consolidated application, Windows launcher/build scripts, upstream and extension tests.
- `Clipivo_V2/_internal/studio/`: Qt integration, person analysis, footage index, replacement review/rendering, CapCut adapter and clip picker.
- `docs/APPROVED_SCOPE.md`: original requested scope plus follow-up requirements.
- `docs/STATUS.md`: implementation and verification boundaries at this checkpoint.

Keep the whole `Clipivo_V2` folder together. This repository currently contains runnable-source development work, **not a compiled Windows EXE or a verified final release**. See `Clipivo_V2/README.md` for setup.

All further work belongs in this repository. Rajudesktop supplied the CapCut draft-writing logic; Concat supplied the relevant clip-selection logic. Neither application is a runtime dependency. No changes were merged into either source repository.
