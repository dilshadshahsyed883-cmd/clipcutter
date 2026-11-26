# YouTube intake candidate (web only)

Terminal test on VPS succeeded with yt-dlp 2026.11.23, Deno and authenticated cookies. Web candidate adds YouTube source type on both studio tabs, canonical single-video URL validation, MP4 video-only <=1080p, owner-private staging, format/ffprobe checks, local SHA256/MD5, fixed runtime and bounded subprocess. Reference images still use Drive. No raw logs or cookie values exposed through the API. Cookie expiry/auth failures require administrator refresh; no login automation. One concurrent YouTube download across owners. Download starts on existing manual intake or separately authorized existing scheduler. Progress reports verified-file count, not a made-up byte percentage. GPU worker contract still rejects YouTube source type; do not activate GPU dispatch for it. Existing scheduler records unsupported ready jobs as failed with staged inputs retained. No changes to GPU or Concat.

## VPS setup, after review and exact-main deployment authorization

Install isolated root-owned runtime (not the ubuntu test venv), no system Python changes:
    sudo python3 -m venv /opt/clipcutter-ytdlp
    sudo /opt/clipcutter-ytdlp/bin/python -m pip install 'yt-dlp[default,deno]==2026.11.23'
    sudo /opt/clipcutter-ytdlp/bin/yt-dlp --version
    sudo /opt/clipcutter-ytdlp/bin/deno --version

Cookie file must be user-owned mode 0600, not shared with Concat, not in web release, not committed, never displayed:
    sudo install -d -o clipcutterweb -g clipcutterweb -m 0700 /var/lib/clipcutter-youtube
    sudo install -o clipcutterweb -g clipcutterweb -m 0600 /home/ubuntu/ytdlp-test/cookies.txt /var/lib/clipcutter-youtube/cookies.txt

Only use account/video access you are authorized to use. Refresh via the same install procedure from a fresh private export if authentication fails. Per-download copy is deleted during normal cleanup; interrupted staging is cleaned on retry. Verify ffprobe availability and runtime permissions. A successful configuration check does not prove cookie validity; actual authenticated download in the web service identity is pending. No automatic credential refresh, cookie upload UI, playlist, live capture, audio, alternative format or GPU dispatch. MP4 availability may differ by video. Existing 4 GiB per file, 20 GiB per job and 5 GB disk reserve apply. No paid GPU starts authorized by intake testing.
