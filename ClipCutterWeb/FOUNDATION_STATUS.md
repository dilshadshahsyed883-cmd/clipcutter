# Step 3 foundation candidate

Source reference: Concat Web main snapshot 2802e1ea5d7bfbea09fdfb40e74569ccf94bbd94. Ported standalone admin routes/security, login and admin templates, read-only host dashboard metrics and assets, shared sidebar styling, logout behavior and source-level admin regression tests. Changed independent ClipCutter namespace, cookies, origin, service identity and two authenticated Studio tabs; removed Concat/uploader providers and runtime dependencies. Studio tabs are intentionally non-processing placeholders. Dashboard retains reference host service list plus ClipCutter service; verify list against actual VPS. Metrics failures return unavailable rather than fabricated CPU/RAM zeros.

Run from ClipCutterWeb/ in an isolated Python 3.11+ environment:
```
python -m pip install -r requirements.txt
python -m compileall -q app run.py tests deploy/init-local-admin.py
python -m unittest discover -s tests -v
```

## Source verification — 26 November 2026

GitHub connector retrieved the exact PR head `8068092d04fbe7c870f01f783ca3e00ac9f1a1f0` despite the local clone transport failure. Retrieved source files were checked against Git blob hashes; only the intentional metrics fix and regression test differ.

- Linux Python 3.12, unprivileged disposable virtual environment, actual requirements.txt installation.
- `bash deploy/test-source.sh`: PASS. Bash syntax checks for all four deployment scripts, Python compilation, and 15 unittest cases passed.
- Original 14 tests also passed before the fix.
- Fixed OS-name parsing: the previous character class excluded the letter n and truncated Linux names. Added quoted/unquoted os-release regression coverage.
- Authentication, CSRF, throttling, revocation, persistent sessions, owner isolation, protected pages and metrics failure handling are covered by source tests. Successful metrics API data uses a fixture; tests do not establish actual VPS readings.
- Expected RuntimeError: probe traceback is the deliberate metrics-unavailable test, which passes.

Guarded manual VPS bootstrap/preflight/stage, private configuration checks, rollback and independent Nginx cutover remain source candidates. Their syntax was checked, but systemd operations, real backups, release rollback, DNS, TLS and live browser parity have not been exercised. Studio tabs remain non-processing placeholders. No VPS mutation, desktop changes, EXE builds or workflows were performed. PR remains draft; main merge and deployment remain pending.
