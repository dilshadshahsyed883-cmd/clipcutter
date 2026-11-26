#!/usr/bin/env bash
# Read-only host audit. No service control or config writes.
set -Eeuo pipefail
if [[ "$EUID" != 0 ]]; then echo "Run with sudo for Nginx visibility" >&2; exit 1; fi
nginx -t >/dev/null 2>&1 && echo NGINX=PASS || echo NGINX=FAIL
echo '=== DNS ==='
getent ahostsv4 clip.scenebuilder.online | awk '{print $1}' | sort -u || true
echo '=== EXISTING CLIPCUTTER ROUTE ==='
nginx -T 2>/dev/null | awk '/^[[:space:]]*server_name[[:space:]]/ && /clip\.scenebuilder\.online([[:space:];]|$)/ {print "CLIPCUTTER_ROUTE=PRESENT"}' || true
echo '=== LISTENERS ==='
ss -ltn
echo '=== RESOURCES ==='
free -m
df -h /
echo '=== SERVICE STATE ==='
systemctl show clipcutter-web.service -p LoadState -p ActiveState || true
echo 'CHANGES=NONE'
