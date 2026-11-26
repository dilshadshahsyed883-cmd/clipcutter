# Step 3 foundation candidate

Source reference: Concat Web main snapshot 2802e1ea5d7bfbea09fdfb40e74569ccf94bbd94. Ported standalone admin routes/security, login and admin templates, read-only host dashboard metrics and assets, shared sidebar styling, logout behavior and source-level admin regression tests. Changed independent ClipCutter namespace, cookies, origin, service identity and two authenticated Studio tabs; removed Concat/uploader providers and runtime dependencies. Studio tabs are intentionally non-processing placeholders. Dashboard retains reference host service list plus ClipCutter service; verify list against actual VPS. Metrics failures return unavailable rather than fabricated CPU/RAM zeros.

Run from ClipCutterWeb/ in an isolated Python 3.11+ environment:
```
python -m pip install -r requirements.txt
python -m compileall -q app run.py tests deploy/init-local-admin.py
python -m unittest discover -s tests -v
```

No tests have been executed in the connector editing environment. Browser parity, deployment helper and host checks remain outstanding. No EXE builds or GitHub Actions workflows. Do not merge until source tests and review pass.
