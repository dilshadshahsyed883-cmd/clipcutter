"""Bounded, video-only YouTube intake using the approved local runtime.
Credentials never cross the API; subprocess output is private and discarded.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import time

from .contracts import youtube_link
from .store import safe_dir

RUNTIME=Path("/opt/clipcutter-ytdlp/bin")
COOKIE=Path("/var/lib/clipcutter-youtube/cookies.txt")
LIMIT=4*1024**3
RESERVE=5_000_000_000
TIMEOUT=3600

def cookie_bytes():
    try:
        with os.fdopen(os.open(COOKIE,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),"rb") as f:
            s=os.fstat(f.fileno())
            if (not stat.S_ISREG(s.st_mode) or s.st_nlink!=1
                    or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o600
                    or not 0<s.st_size<=1024*1024):
                raise ValueError()
            data=f.read(1024*1024+1)
            if len(data)>1024*1024 or not data.startswith((b"# Netscape HTTP Cookie File",b"# HTTP Cookie File")):
                raise ValueError()
            return data
    except (OSError,ValueError):
        raise RuntimeError("YouTube cookies missing or unsafe; administrator must install a private Netscape cookie file") from None

def available():
    try:
        cookie_bytes()
        return all(p.is_file() and os.access(p,os.X_OK) for p in
                   (RUNTIME/"yt-dlp",RUNTIME/"deno",Path("/usr/bin/ffprobe")))
    except RuntimeError:
        return False

def command(url, work, limit):
    return [str(RUNTIME/"yt-dlp"),"--ignore-config","--no-playlist",
            "--no-cache-dir","--no-progress","--no-warnings","--no-mtime",
            "--no-remote-components","--no-plugin-dirs",
            "--cookies",str(work/"cookies.txt"),
            "--js-runtimes","deno:"+str(RUNTIME/"deno"),
            "--ffmpeg-location","/usr/bin","--socket-timeout","30",
            "--retries","2","--fragment-retries","2","--max-filesize",str(limit),
            "--match-filter","!is_live",
            "-f","bv[height<=1080][ext=mp4]",
            "-o",str(work/"source.%(ext)s"),"--",youtube_link(url)]

def stop(proc):
    if proc.poll() is None:
        try: os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        proc.wait()

def verify(path):
    try:
        p=subprocess.run(["/usr/bin/ffprobe","-v","error","-show_entries",
                          "stream=codec_type,height,width:format=duration","-of","json",str(path)],
                         capture_output=True,timeout=60,check=True)
        data=json.loads(p.stdout)
        streams=data["streams"]
        video=[s for s in streams if s.get("codec_type")=="video"]
        duration=float(data["format"]["duration"])
        if (len(video)!=1 or any(s.get("codec_type")=="audio" for s in streams)
                or not 0<video[0]["height"]<=1080 or not 0<video[0]["width"]
                or not 0<duration<=86400):
            raise ValueError()
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError):
        raise RuntimeError("YouTube file failed video-only media verification") from None

def download(store,url,target,remaining):
    if not available():
        raise RuntimeError("YouTube runtime or private cookies not configured")
    url=youtube_link(url)
    # One transfer per deployment; no shared mutable cookie jar.
    locks=safe_dir(store.root.parent.parent/"youtube-locks")
    with os.fdopen(os.open(locks/"download.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a") as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another YouTube download is active; retry intake") from None
        limit=min(LIMIT,remaining,shutil.disk_usage(target.parent).free-RESERVE)
        if limit<=0:
            raise RuntimeError("Insufficient VPS storage reserve")
        with tempfile.TemporaryDirectory(prefix="youtube-",dir=target.parent) as td:
            work=Path(td)
            with (work/"cookies.txt").open("xb") as f:
                os.chmod(work/"cookies.txt",0o600)
                f.write(cookie_bytes())
            # Private HOME and cache; no ambient config, proxy or credentials.
            env={"PATH":str(RUNTIME)+":/usr/bin:/bin","HOME":td,
                 "XDG_CONFIG_HOME":td,"XDG_CACHE_HOME":td,"LANG":"C.UTF-8"}
            with (work/"error.log").open("w+b") as log:
                proc=subprocess.Popen(command(url,work,limit),stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL,stderr=log,env=env,
                                      start_new_session=True)
                deadline=time.monotonic()+TIMEOUT
                try:
                    while proc.poll() is None:
                        used=sum(p.stat().st_size for p in work.iterdir() if p.is_file() and not p.is_symlink())
                        if used>limit+2*1024**2 or shutil.disk_usage(work).free<RESERVE:
                            raise RuntimeError("YouTube download exceeded VPS storage limit")
                        if time.monotonic()>=deadline:
                            raise RuntimeError("YouTube download timed out; retry intake")
                        time.sleep(.5)
                finally:
                    stop(proc)
                if proc.returncode:
                    log.seek(max(0,log.tell()-65536))
                    error=log.read(65536).lower()
                    if any(x in error for x in (b"sign in",b"cookies",b"not a bot",b"login")):
                        raise RuntimeError("YouTube authentication rejected; refresh VPS cookies and retry")
                    raise RuntimeError("YouTube download failed or requested video-only format unavailable")
            media=work/"source.mp4"
            if media.is_symlink() or not media.is_file() or not 0<media.stat().st_size<=limit:
                raise RuntimeError("YouTube did not return one valid MP4")
            verify(media)
            sha,md5=hashlib.sha256(),hashlib.md5(usedforsecurity=False)
            with media.open("rb") as f:
                for chunk in iter(lambda:f.read(1024*1024),b""):
                    sha.update(chunk);md5.update(chunk)
            size=media.stat().st_size
            with media.open("rb") as f:os.fsync(f.fileno())
            media.rename(target)
            return {"name":"source.mp4","size":size,"sha256":sha.hexdigest(),"md5":md5.hexdigest()}
