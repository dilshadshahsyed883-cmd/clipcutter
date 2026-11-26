# ClipCutter Web — VPS basic setup record

Date: 2026-11-26. Owner executed the commands manually on the VPS and provided terminal output in the setup conversation. This record covers observed preparation and the first successful live foundation deployment. Evidence is owner-supplied terminal output and a browser screenshot; it does not establish end-to-end processing readiness. Follow [CONTROL_ARCHITECTURE.md](CONTROL_ARCHITECTURE.md) for the approved deployment policy.

## Verified host and capacity

| Item | Observed |
|---|---|
| Host | vps-01a23801 |
| OS | Ubuntu 24.04.4 LTS, x86_64 |
| IPv4 / DNS A resolution | 137.74.162.143; getent resolved clip.scenebuilder.online to this address |
| CPU | 4 cores |
| Memory | 7.6 GiB total, 3.6 GiB available at inspection; no swap |
| Root filesystem | 72G total, 42G available |
| ClipCutter proposed bind | 127.0.0.1:18874; no listener at inspection |
| Existing Concat | 127.0.0.1:18873; concat-web.service active at preflight |
| Dependencies | Python 3.12.3, Git 2.43.0, FFmpeg 6.1.1; Python venv creation passed |
| Other tools | git, curl, tar, sha256sum, flock, openssl, certbot present |
| Nginx | syntax check passed; no clip.scenebuilder.online match in effective config at preflight |

Capacity and port checks are snapshots, not reservations or load-test results. Recheck before deploying; heavy processing belongs on the independent GPU worker. OS reported updates and restart required, plus one zombie process. No system upgrade or reboot was performed; schedule maintenance separately.

## Completed host preparation

- Dedicated system account and group `clipcutterweb` created, UID 993 / GID 984, non-login shell, home `/var/lib/clipcutter-web`.
- Root-owned 0755 directories: `/srv/clipcutter-web`, `/srv/clipcutter-web/releases`.
- Service-owned 0700 directories: `/var/lib/clipcutter-web` and its `jobs`, `input`, `output`, `logs`, `profiles` subdirectories.
- Root-owned 0700 directories: `/etc/clipcutter-web`, `/var/backups/clipcutter-web`.
- Environment file `/etc/clipcutter-web/clipcutter-web.env` created; terminal stat confirmed root:root, mode 0600. A random 32-byte hex session secret was generated on the host; never print, copy or commit its value.
- Systemd unit `/etc/systemd/system/clipcutter-web.service` created, daemon-reload executed. Reported `LoadState=loaded`, `ActiveState=inactive`, `UnitFileState=disabled`. Do not start or enable until a reviewed release is staged and prerequisites pass.

### Historical initial environment contract (superseded by admin bootstrap)

```dotenv
CLIPCUTTER_HOST=127.0.0.1
CLIPCUTTER_PORT=18874
CLIPCUTTER_DOMAIN=clip.scenebuilder.online
CLIPCUTTER_DATA_DIR=/var/lib/clipcutter-web
CLIPCUTTER_SESSION_SECRET=<generated on host; not recorded>
```

The initial file was privately backed up during the first admin bootstrap and replaced with the foundation's actual environment contract below. Preserve the active credentials, session secret and persistent state across releases.

### Historical initial systemd unit (superseded by repository unit)

```ini
[Unit]
Description=ClipCutter Web
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=clipcutterweb
Group=clipcutterweb
WorkingDirectory=/srv/clipcutter-web/current
EnvironmentFile=/etc/clipcutter-web/clipcutter-web.env
ExecStart=/srv/clipcutter-web/current/.venv/bin/python run.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/clipcutter-web
UMask=0077

[Install]
WantedBy=multi-user.target
```

The initial unit was backed up and replaced with the exact repository unit during bootstrap.

## DNS and TLS

DNS resolves correctly on the VPS. Existing certificates for app.scenebuilder.online and concat.scenebuilder.online were valid at initial inspection. A separate ClipCutter certificate was successfully issued and verified on 2026-11-26.

- Nginx HTTP-only ACME site created at `/etc/nginx/sites-available/clipcutter-web`, enabled via `/etc/nginx/sites-enabled/clipcutter-web`. Syntax check and reload succeeded.
- Port 80 initially served `/.well-known/acme-challenge/` from `/var/www/clipcutter-acme` and returned 404 for other requests. The subsequent HTTPS placeholder activation preserved the ACME location and changed other HTTP requests to a 301 redirect to `https://clip.scenebuilder.online$request_uri`.
- Issuance command: `sudo certbot certonly --webroot -w /var/www/clipcutter-acme --cert-name clip.scenebuilder.online -d clip.scenebuilder.online`.
- Verified certificate name and domain: clip.scenebuilder.online; ECDSA; expiry 2027-02-24 11:38:54 UTC.
- Certificate: `/etc/letsencrypt/live/clip.scenebuilder.online/fullchain.pem`; private key: `/etc/letsencrypt/live/clip.scenebuilder.online/privkey.pem`. Never copy key contents into Git.
- Certbot reported scheduled automatic renewal. Renewal dry-run and future Nginx reload behavior have not been verified.
- Owner authorized temporary HTTPS activation on 2026-11-26 before backend deployment. The dedicated Nginx site was backed up under `/var/backups/clipcutter-web/nginx.*` and updated with a port 443 SSL server for `clip.scenebuilder.online`, using the existing certificate and TLS 1.2/1.3. Its root location initially returned a static HTTP 200 HTML page titled ClipCutter Web — Coming Soon. The placeholder was subsequently replaced by the live reverse proxy.
- Owner supplied successful `nginx -t`, reload and `HTTPS ACTIVATED` output, followed by another successful `nginx -t` and `active` output. Subsequent VPS `curl -I https://clip.scenebuilder.online` succeeded with HTTP/1.1 200 OK, nginx/1.24.0, text/html, Content-Length 263 at 2026-11-26 12:41:33 UTC. HTTPS response and certificate trust verified from the VPS. HTTP 301 redirect to the exact HTTPS hostname was also verified at 12:40:40 UTC.
- The backend and reverse proxy were subsequently activated as recorded below.

Do not request a duplicate certificate unnecessarily. The existing certificate remains in use.

## First live foundation release — 2026-11-26

- Approved staged source SHA: `b7ae1894dac0de1909a7bbc36a188cda02a986f2`. The clone and remote main matched during preparation. This is the deployed SHA, not necessarily the latest repository main.
- Repository systemd unit `ClipCutterWeb/deploy/clipcutter-web.service` replaced the initial unit after a private backup. Entry point now uses absolute run.py path. Bootstrap returned `BOOTSTRAP=PASS SERVICE_NOT_STARTED`.
- Canonical helper installed root-owned at `/usr/local/sbin/clipcutter-web-deploy`, from repository `deploy/guarded-release.sh`. Command order: `<exact-main-SHA> preflight`, then `<exact-main-SHA> stage`. No Concat helper was used.
- Initial private environment was moved to a root-only backup, then `init-local-admin.py` created the replacement environment and `check-env.py` returned 18874. Admin username is independently configured; credentials and secret values are not recorded here.
- Active environment contract: `CLIPCUTTER_AUTH_MODE=local-admin`, `CLIPCUTTER_ADMIN_USERNAME`, `CLIPCUTTER_ADMIN_PASSWORD_HASH`, `CLIPCUTTER_ADMIN_SESSION_SECRET`, `CLIPCUTTER_WEB_SECURITY_DB=/var/lib/clipcutter-web/security.sqlite3`, `CLIPCUTTER_WEB_DATA_ROOT=/var/lib/clipcutter-web`, `CLIPCUTTER_WEB_PUBLIC_ORIGIN=https://clip.scenebuilder.online`, `CLIPCUTTER_WEB_HOST=127.0.0.1`, `CLIPCUTTER_WEB_PORT=18874`. Mode 0600; do not print values of secrets.
- Guarded preflight passed. Stage installed dependencies, passed 15/15 source tests, reported `SQLITE_BACKUP=PASS`, and returned `STAGED_SHA=b7ae1894dac0de1909a7bbc36a188cda02a986f2 BACKUP=/var/backups/clipcutter-web/release.N098Ct9L PUBLIC_NGINX=UNCHANGED`. The intentional mocked metrics failure test passed; initial connection refusal during service startup recovered. Preflight and stage archive SHA256 outputs differed; archive digest determinism is not established.
- Current release path: `/srv/clipcutter-web/releases/b7ae1894dac0de1909a7bbc36a188cda02a986f2`. Service reported active. Loopback health returned `{"ok":true,"service":"clipcutter-web"}`. Concat service remained active.

## Live HTTPS cutover

The repository's new-site cutover script rejects an already existing hostname. A separate manual, ClipCutter-only guarded adoption was therefore used for the existing no-extension Nginx site file.

- First attempt: public health returned non-JSON, triggering restoration of the backed-up placeholder and Nginx reload. Root cause unconfirmed.
- Second attempt: locked release/cutover, verified local backend, backed up existing configuration, replaced only the static Coming Soon location with proxy_pass to 127.0.0.1:18874; preserved HTTP redirect, ACME webroot, certificate and TLS configuration. Uses forwarded host/proto/IP, clears auth identity headers, disables access logging, and limits request body to 4m.
- Nginx syntax and reload succeeded; retry-based local TLS check using --resolve and --noproxy passed exact backend health JSON, anonymous 401 for /dashboard, /admin and /api/v1/session, and 200 for /auth/login. Concat service active. Terminal reported HTTPS REVERSE PROXY PASS.
- Owner browser screenshot at approximately 12:54 UTC shows authenticated https://clip.scenebuilder.online/dashboard, sidebar Dashboard / ClipCutter Studio / Admin, signed-in identity, sign out control, auto refresh 10 sec, VPS Online, service health 10/10, CPU 0% at sample (4 cores), RAM 53% (4.0/7.6 GB), storage 42.5%, free storage 41.2 GB, load average 0.48 and uptime 40d 20h 56m. These are displayed snapshot values, not independently audited telemetry. Successful browser login and dashboard rendering confirmed; live logout/revocation and other pages not individually verified.

## Remaining work

1. Confirm systemd UnitFileState; service is running but boot enablement has not been verified. Enable only with owner approval. Verify certificate renewal dry-run and Nginx reload hook separately.
2. Add reviewed existing-site adoption procedure and reproducible archive/dependency integrity checks to repository release tooling; do not create a conflicting Nginx site. For future processing releases add safe job drainage and migration/rollback gates. Do not assume full data rollback from code rollback.
3. Test browser logout, session revocation, admin settings and both Studio tabs. Verify host service allowlist and existing sites independently.
4. Implement/test Clip Extractor, Person Analyzer, persistent queue and independent SaladCloud GPU integration. The deployed foundation Studio processing pages are placeholders; no live media processing or GPU acceptance has been demonstrated.

No EXE build, GitHub Actions build/deploy workflow, remote SSH automation, modifications to Concat/Scene service configuration, or paid GPU provisioning were performed as part of this record. Basic VPS setup, foundation deployment, live HTTPS and authenticated Dashboard are complete.
