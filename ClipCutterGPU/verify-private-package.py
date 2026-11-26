"""Fail closed unless the dedicated test package already exists and is private."""
import json
import os
import urllib.request
import urllib.error

OWNER = "dilshadshahsyed883-cmd"
PACKAGE = "clipcutter-gpu-private-test"
URL = "https://api.github.com/user/packages/container/" + PACKAGE

def verify(token):
    if not token or any(x in token for x in "\r\n"):
        raise RuntimeError("Package verification credential missing or invalid")
    req = urllib.request.Request(URL, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "clipcutter-private-release-check",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        raise RuntimeError("Private package metadata unavailable; publication blocked") from None
    if not isinstance(result, dict) or result.get("name") != PACKAGE or result.get("visibility") != "private" or result.get("owner", {}).get("login", "").lower() != OWNER:
        raise RuntimeError("Expected owner-scoped private testing package; publication blocked")
    print("PRIVATE_TEST_PACKAGE=VERIFIED")

if __name__ == "__main__":
    verify(os.environ.get("CLIPCUTTER_PACKAGE_VERIFY_TOKEN", ""))
