"""Read-only ClipCutter Drive bridge. Run as the canonical Drive identity.
No caller paths, remotes, credentials, writes or arbitrary rclone commands.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import socketserver
import stat
import struct
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

LIMIT = 4 * 1024**3
RESERVE = 5_000_000_000
ID = re.compile(r"[A-Za-z0-9_-]{10,200}")
TYPES = {"video": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"},
         "image": {".jpg", ".jpeg", ".png", ".webp"}, "zip": {".zip"}}

def parse_link(link):
    if not isinstance(link, str) or len(link) > 2048:
        raise ValueError()
    u = urlsplit(link)
    if u.scheme != "https" or u.netloc != "drive.google.com" or u.fragment:
        raise ValueError()
    q = parse_qs(u.query)
    match = re.fullmatch(r"/(file/d|drive/(?:u/\d+/)?folders)/([A-Za-z0-9_-]{10,200})(?:/view|/edit)?/?", u.path)
    if match:
        item, folder = match[2], match[1] != "file/d"
    elif u.path in ("/open", "/uc") and len(q.get("id", [])) == 1:
        item, folder = q["id"][0], False
    else:
        raise ValueError()
    keys = q.get("resourcekey", [])
    if not ID.fullmatch(item) or len(keys) > 1 or (keys and not ID.fullmatch(keys[0])):
        raise ValueError()
    return item, folder, keys[0] if keys else ""

def hashes(path):
    sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            sha.update(chunk); md5.update(chunk)
    return sha.hexdigest(), md5.hexdigest()

class Drive:
    def __init__(self, remote, spool):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", remote):
            raise ValueError("Invalid remote")
        self.remote = remote + ":"
        self.spool = Path(spool)
    def execute(self, args, timeout):
        # Use the canonical service identity's configured rclone remote.
        with tempfile.TemporaryFile(dir=self.spool) as out:
            proc = subprocess.run(["rclone", *args], stdout=out, stderr=subprocess.DEVNULL,
                                  timeout=timeout, check=False)
            if proc.returncode or out.tell() > 16*1024**2:
                raise RuntimeError("Drive operation failed")
            out.seek(0)
            return out.read()
    def scan(self, link, kind):
        item, folder, key = parse_link(link)
        if kind not in TYPES:
            raise ValueError()
        if not folder:
            return [{"id": item, "name": "", "size": 0, "md5": "", "keys": f"{item}/{key}" if key else ""}]
        args = ["lsjson", self.remote, "--drive-root-folder-id", item, "--recursive",
                "--files-only", "--drive-skip-shortcuts", "--hash"]
        if key:
            args += ["--drive-resource-key", key]
        entries = json.loads(self.execute(args, 90))
        if not isinstance(entries, list):
            raise RuntimeError()
        result = []
        seen = set()
        for e in entries:
            name, fid = e.get("Name"), e.get("ID")
            if not isinstance(name, str) or Path(name).suffix.lower() not in TYPES[kind]:
                continue
            if not isinstance(fid, str) or not ID.fullmatch(fid) or fid in seen:
                raise ValueError()
            size = e.get("Size")
            md5 = (e.get("Hashes") or {}).get("MD5", "").lower()
            if type(size) is not int or not 0 < size <= LIMIT or not re.fullmatch(r"[a-f0-9]{32}", md5):
                raise ValueError()
            file_key = e.get("ResourceKey") or ""
            keys = ",".join(filter(None, [f"{item}/{key}" if key else "",
                        f"{fid}/{file_key}" if ID.fullmatch(file_key) else ""]))
            result.append({"id": fid, "name": name[:240], "size": size, "md5": md5, "keys": keys})
            seen.add(fid)
            if len(result) > 200:
                raise ValueError()
        return result
    def fetch(self, row, kind, directory):
        if kind not in TYPES or set(row) != {"id","name","size","md5","keys"}:
            raise ValueError()
        fid, size, md5, keys = row["id"], row["size"], row["md5"], row["keys"]
        if (not isinstance(fid, str) or not ID.fullmatch(fid) or type(size) is not int
                or not 0 <= size <= LIMIT or not isinstance(md5, str)
                or (md5 and not re.fullmatch(r"[a-f0-9]{32}", md5))
                or not isinstance(keys, str) or len(keys) > 1000
                or (keys and not all(re.fullmatch(r"[A-Za-z0-9_-]{10,200}/[A-Za-z0-9_-]{10,200}", k) for k in keys.split(",")))):
            raise ValueError()
        limit = min(LIMIT, shutil.disk_usage(directory).free - RESERVE)
        if limit < max(size, 1):
            raise RuntimeError()
        args = ["backend", "copyid", self.remote, fid, str(directory)+"/",
                "--max-transfer", f"{limit}B", "--cutoff-mode", "CAUTIOUS",
                "--multi-thread-streams", "0", "--low-level-retries", "3"]
        if keys:
            args += ["--header", "X-Goog-Drive-Resource-Keys: "+keys]
        self.execute(args, 3600)
        entries = list(directory.iterdir())
        if len(entries) != 1:
            raise ValueError()
        path = entries[0]
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or not 0 < st.st_size <= limit or path.suffix.lower() not in TYPES[kind]:
            raise ValueError()
        sha, actual_md5 = hashes(path)
        if size and (st.st_size != size or actual_md5 != md5):
            raise ValueError()
        return path, {"size": st.st_size, "sha256": sha, "md5": actual_md5, "name": path.name[:240]}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        started = False
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
                raise ValueError()
            n = int(lengths[0])
            if not 0 < n <= 16384:
                raise ValueError()
            obj = json.loads(self.rfile.read(n))
            drive = self.server.drive
            if self.path == "/v1/health" and obj == {}:
                if drive.remote.encode() not in drive.execute(["listremotes"], 30).splitlines():
                    raise RuntimeError()
                self.reply(200, {"ok": True, "protocol": 1})
            elif self.path == "/v1/scan" and set(obj) == {"link","kind"}:
                self.reply(200, {"files": drive.scan(obj["link"], obj["kind"])})
            elif self.path == "/v1/download" and set(obj) == {"row","kind"}:
                with tempfile.TemporaryDirectory(dir=drive.spool) as tmp:
                    path, meta = drive.fetch(obj["row"], obj["kind"], Path(tmp))
                    self.send_response(200)
                    self.send_header("Content-Length", str(meta["size"]))
                    self.send_header("X-File-Meta", json.dumps(meta, ensure_ascii=True))
                    self.end_headers(); started = True
                    with path.open("rb") as source:
                        shutil.copyfileobj(source, self.wfile, 1024*1024)
            else:
                self.reply(404, {"error": "unsupported"})
        except (ValueError, TypeError, KeyError, AttributeError):
            if not started:
                self.reply(422, {"error":"invalid_source"})
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            if not started:
                self.reply(503, {"error":"drive_unavailable"})

class Server(socketserver.UnixStreamServer):
    def verify_request(self, request, address):
        request.settimeout(60)
        _, uid, _ = struct.unpack("3i", request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        return uid == self.uid
    def handle_error(self, request, address):
        pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--socket", required=True, type=Path)
    p.add_argument("--spool", required=True, type=Path)
    p.add_argument("--remote", required=True)
    p.add_argument("--client-user", default="clipcutterweb")
    p.add_argument("--client-group", required=True)
    args = p.parse_args()
    import grp
    os.umask(0o077)
    if args.socket.exists() or args.socket.is_symlink():
        raise RuntimeError("Refusing to replace existing socket")
    drive = Drive(args.remote, args.spool)
    with Server(str(args.socket), Handler) as server:
        server.drive = drive
        server.uid = pwd.getpwnam(args.client_user).pw_uid
        os.chown(args.socket, -1, grp.getgrnam(args.client_group).gr_gid)
        os.chmod(args.socket, 0o660)
        try:
            server.serve_forever()
        finally:
            args.socket.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
