# Clipcutter

Independent Windows desktop video intelligence application based on Clipivo V2.2 and the MIT-licensed upstream Clipivo v0.7.7 source. The current V2.3 implementation is a **work in progress**, saved here at the owner's request. Fixes and further validation are deferred.

## Current development restriction

Owner instruction recorded on 26 November 2026:

- Do not trigger any EXE build, including the existing local `BUILD_EXE.bat` script or any manual/automatic CI build.
- Do not create or add a GitHub Actions EXE/build workflow, or enable automatic executable builds.
- Keep current work limited to source code, documentation, fixes and source-level testing when requested. Tests must not invoke EXE packaging.
- Existing build scripts are retained as inactive source; their presence and older build instructions do not authorize execution.
- This restriction overrides earlier packaging/build plans and remains in force until the owner explicitly changes it.

## Source

- `Clipivo_V2/`: the clean source launcher and `_internal` tree (including documentation, licenses, reports, tests and inactive development scripts).
- `Clipivo_V2/_internal/studio/`: Qt integration, person analysis, footage index, replacement review/rendering, CapCut adapter and clip picker.
- `docs/APPROVED_SCOPE.md`: original requested scope plus follow-up requirements.
- `docs/STATUS.md`: implementation and verification boundaries at this checkpoint.

Keep the whole `Clipivo_V2` folder together. This repository currently contains runnable-source development work, **not a compiled Windows EXE or a verified final release**. See `Clipivo_V2/_internal/docs/README.md` for setup.

All further work belongs in this repository. Rajudesktop supplied the CapCut draft-writing logic; Concat supplied the relevant clip-selection logic. Neither application is a runtime dependency. No changes were merged into either source repository.

## PC testing ZIP

Source ZIP and extracted app default to `%LOCALAPPDATA%\ClipivoV2`, not Downloads. See [PC testing ZIP method](docs/PC_TEST_ZIP_METHOD.md) for the archive layout, exact directories and setup requirements. This is a documented requirement; executable builds remain prohibited.

The source folder is location-independent; only the default delivery location is AppData. Runtime, caches, models and persistent data are outside the source tree.
