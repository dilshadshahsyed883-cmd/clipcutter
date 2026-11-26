# Agent 3 — CapCut independent work checkpoint

Status: **source changes pushed; final three-agent integration NOT started**.

Base main: `1973433746a0bc72e6513b428a4ea39df1d104f4`.
Branch: `work/capcut-integration`.
CapCut/test checkpoint before this report: `4349af0264313778cee74534005e650822c0dfd7`.

## Source changes

- Inspected the copied Rajudesktop Z Builder writer and existing Clipcutter adapter, including optional constant speed and the existing `expand_plan` piece schema.
- Validated approved rows, exact gap-fill coverage, contiguous target boundaries, source trims against approved ranges and probed duration, supported 0.67–1.5x speed, reference dimensions/FPS and total coverage.
- Preserved editable native video segments, including all physical pieces; used microsecond endpoint differences instead of rounding each clip to milliseconds. Video replacement clips are muted; original/external audio is a separate editable track. None creates no audio track. Original media without an audio stream remains silent. External audio without a stream, shorter audio requiring padding, and nonzero stream offsets are blocked rather than silently altered.
- Fixed video/audio material cache aliasing when both use the same source file. Native segment speed and speed-material references are verified independently.
- Verify the staged project before publication: top-level/nested timeline JSON and backups, main timeline ID, target/source timing, segment counts, copied media paths, source material ranges, speed references, audio volume, duration and canvas/FPS. Reverify after publication before launch. New draft names use a random suffix and an existence check; existing drafts are not intentionally modified.
- Detect custom CapCut globalSetting draft folder, including quoted paths, and refuse an unavailable configured path unless the user specifies a manual override. Existing Settings key `capcut_drafts` is retained. Existing UI already tells users to open the draft from CapCut Home; the bridge also returns this instruction. Native playback compatibility is explicitly unverified.
- Reuse installed Node or verified official portable Windows Node. Portable installation is under persistent studio data, not the installation folder; archive SHA256 is checked against the official distribution and cached executable integrity is checked against the recorded digest.

## Testing evidence

Added `Clipivo_V2/_internal/tests/test_capcut_v23.py` (five test methods). These invoke the actual Node bridge on temporary draft folders when executed, with mocked media metadata and fixture bytes, and cover multi-piece/speed precision, original/none/external audio, same-file audio/video material separation, unique and unchanged drafts, invalid plan rejection, nested corruption, and custom folder detection. They do not test installed playback.

Executed an additional **in-memory JavaScript smoke test** using the actual fetched writer source in a V8 runtime with a simulated filesystem, path, and crypto implementation. Three exports (original/none/external) returned zero verification issues, with 3/2/3 segments respectively. All retained 2,000,000 us total duration and the first 1,123,456 us target duration; draft names differed and the existing sentinel remained unchanged. Nested corruption was detected. Bridge JavaScript parsed successfully.

**Real Node writer/real filesystem tests, Python pytest and Qt tests have NOT been run in this session.** The execution container has Node 22.16.0 but GitHub clone failed with DNS resolution error, and raw-source download was unavailable. GitHub connector source reads/writes succeeded but do not mount the checkout in that container. The in-memory smoke is not a substitute for the required real Node run or regression suite.

From an accessible checkout:
```sh
cd Clipivo_V2/_internal
python -m pytest -q tests/test_capcut_v23.py
QT_QPA_PLATFORM=offscreen python -m pytest -q tests
```
On Windows set QT_QPA_PLATFORM=offscreen using the applicable shell syntax.

## Integration gate and limitations

Agent 1 and Agent 2 branches exist but their explicitly supplied pushed completion commit SHAs were not received. Do not merge branch tips speculatively. Once both SHAs and Agent 2's documented plan schema are supplied, integrate those exact commits here, resolve conflicts, verify UI/settings/schema compatibility, run the real Node tests and complete regression/offscreen navigation checks, fix any failures and update STATUS, TEST_REPORT and CHANGELOG based on actual results.

Remaining acceptance: real Windows source launch and runtime bootstrap/custom-folder detection; real FFmpeg media and stream-duration edge cases; actual CapCut draft discovery and playback for trims, speed, audio synchronization and canvas fitting; GPU and real face inference; full Qt navigation and regression suite. Short/offset audio is intentionally rejected when exact native representation cannot be guaranteed. Probe metadata can have container-level fallback durations; installed playback is not established.

No EXE build, packaging, BUILD_EXE.bat, GitHub Actions workflow change, delegation or main merge/push was performed. Independent changes are confined to the four owned modules, new regression test and this report.
