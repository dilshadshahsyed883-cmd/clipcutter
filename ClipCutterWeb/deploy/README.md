# Manual deployment candidate (Concat Web pattern)

Do not execute on production until the exact source passes source-level tests and review, and the owner authorizes a VPS deployment. No GitHub Actions or automated SSH.

- From the VPS terminal clone the repository at reviewed exact main SHA, compare remote main and local HEAD; run the pinned `ClipCutterWeb/deploy/host-audit.sh` read-only first.
- First installation only: run pinned `sudo bash ClipCutterWeb/deploy/guarded-release.sh <SHA> bootstrap`. It creates separate directories, user, unit and helper, without starting the web service.
- Run pinned `sudo python3 ClipCutterWeb/deploy/init-local-admin.py` interactively once; choose a verified free port other than Concat's 18873. No password or secrets in chat or argv.
- Run `sudo /usr/local/sbin/clipcutter-web-deploy <SHA> preflight`, then `sudo /usr/local/sbin/clipcutter-web-deploy <SHA> stage`. Candidate source is pinned to current remote main, dependencies isolated per release, tests use disposable state, prior SQLite/config backed up and current symlink promoted only after tests. Loopback checks trigger source rollback on failure. Failed candidates are retained; never overwrite.
- Separate HTTPS activation: obtain and verify a valid certificate for the exact hostname (certificate issuance is not included), then run pinned current `deploy/nginx-cutover.sh activate <SHA>`. No overwrite of existing sites; rollback is `rollback <SHA>` for the exact managed route. Nginx is reloaded, not restarted.
- Live browser login/logout, dashboard metrics, DNS, TLS and existing sites must be verified independently. GPU/processing integration belongs to subsequent steps. This foundation helper does not yet support active production job drainage or schema migration; add those gates before future processing releases.
- The deployment source is unexecuted on VPS; do not infer live deployment from repository commits.

For source-only validation from a clean non-production checkout, run `bash ClipCutterWeb/deploy/test-source.sh` as an unprivileged user. It checks shell syntax, compiles Python and runs the regression suite in a disposable venv. No service writes or deployment. An installed helper that differs from the pinned helper is rejected; review upgrades separately.

## Reference upload capacity

Direct PC reference uploads: up to 12 JPG/PNG/WEBP images, 10 MiB per image, 120 MiB combined. The existing 16 MiB worker per-reference cap is unchanged. Hash and copy in bounded chunks. Only the exact reference upload endpoint uses a 128 MiB ingress limit and Concat-style timeouts/no proxy buffering; other endpoints retain 4 MiB. After staging the reviewed SHA on an already activated site, run `sudo bash /srv/clipcutter-web/current/deploy/nginx-upload-upgrade.sh <SHA>`. The helper validates the existing managed site hash, backs up its configuration, tests Nginx, reloads it, verifies ClipCutter and the existing sites, and restores the original configuration on failure. If the site is unmanaged or drifted, stop for manual review. No Concat config change or GPU image build.
