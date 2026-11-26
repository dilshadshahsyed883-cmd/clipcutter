# ClipCutter Web — VPS basic setup record

Date: 2026-11-26. Owner executed the commands manually on the VPS and provided terminal output in the setup conversation. This is an observed preparation record, not a deployed application or a live health test. Follow [CONTROL_ARCHITECTURE.md](CONTROL_ARCHITECTURE.md) for the approved deployment policy.

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

### Proposed environment contract (already provisioned on host)

```dotenv
CLIPCUTTER_HOST=127.0.0.1
CLIPCUTTER_PORT=18874
CLIPCUTTER_DOMAIN=clip.scenebuilder.online
CLIPCUTTER_DATA_DIR=/var/lib/clipcutter-web
CLIPCUTTER_SESSION_SECRET=<generated on host; not recorded>
```

Application implementation must match or explicitly migrate these names. Preserve the generated secret and persistent state across releases.

### Installed systemd unit (record of supplied command)

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

This is a proposed entrypoint/runtime contract, not proof that run.py, a release virtualenv or the current symlink exists. Verify compatibility with the implemented backend before starting. Release code and runtime must be immutable to the service user.

## DNS and TLS

DNS resolves correctly on the VPS. Existing certificates for app.scenebuilder.online and concat.scenebuilder.online were valid at initial inspection. A separate ClipCutter certificate was successfully issued and verified on 2026-11-26.

- Nginx HTTP-only ACME site created at `/etc/nginx/sites-available/clipcutter-web`, enabled via `/etc/nginx/sites-enabled/clipcutter-web`. Syntax check and reload succeeded.
- Port 80 serves `/.well-known/acme-challenge/` from `/var/www/clipcutter-acme`; other requests return 404. Preserve the challenge location during future HTTPS cutover.
- Issuance command: `sudo certbot certonly --webroot -w /var/www/clipcutter-acme --cert-name clip.scenebuilder.online -d clip.scenebuilder.online`.
- Verified certificate name and domain: clip.scenebuilder.online; ECDSA; expiry 2027-02-24 11:38:54 UTC.
- Certificate: `/etc/letsencrypt/live/clip.scenebuilder.online/fullchain.pem`; private key: `/etc/letsencrypt/live/clip.scenebuilder.online/privkey.pem`. Never copy key contents into Git.
- Certbot reported scheduled automatic renewal. Renewal dry-run and future Nginx reload behavior have not been verified.
- Public HTTPS, TLS reverse proxy and backend deployment remain pending. Recheck existing services and Nginx health after changes; no post-issuance Concat health output was supplied.

Do not request a duplicate certificate unnecessarily. Reuse the existing valid certificate at guarded HTTPS cutover.

## Remaining work (not completed)

1. Implement and test the standalone ClipCutterWeb application, Dashboard, Admin & Security, two processing tabs, queue and worker integration per approved scope.
2. Implement and review ClipCutter-specific guarded deployment helper, bootstrap, release staging and rollback. Proposed helper path: /usr/local/sbin/clipcutter-web-deploy. Do not reuse or invoke Concat's helper. No helper was installed during VPS preparation.
3. Verify exact approved main SHA, source-level tests, archive digest, host capacity, free port and existing service health; stage only ClipCutterWeb under /srv/clipcutter-web/releases/<SHA>. Preserve persistent data and use verified atomic current symlink, independent admin initialization, health identity and anonymous access denial. Enable/start only when the reviewed release procedure allows it.
4. After successful loopback verification, perform separate guarded Nginx reverse proxy and HTTPS cutover, using the already issued dedicated certificate and updating only the ClipCutter site configuration. Preserve the HTTP ACME challenge, verify certificate validity and renewal, nginx -t, public HTTPS and existing sites. Roll back only ClipCutter changes on failure.
5. Verify worker and queue behavior independently before production GPU usage.

No EXE build, GitHub Actions build/deploy workflow, remote SSH automation, changes to existing Concat/Scene services, or paid GPU provisioning are authorized by this record. Basic VPS preparation complete; application deployment and public activation pending.
