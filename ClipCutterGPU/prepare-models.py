"""Stage the pinned PC models from a secret HTTPS ZIP URL. Never log the URL."""
import os
import contextlib
import io
import re
from pathlib import Path
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from worker.model_pins import MODELS, verify_models

MAX_ARCHIVE = 220 * 1024 * 1024

class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def validate_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("An HTTPS model archive URL is required")

def unpack(archive, destination):
    destination = Path(destination)
    # A new private temporary directory only; never overwrite model data.
    destination.mkdir(mode=0o700)
    try:
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            if len(entries) != len(MODELS) or {x.filename for x in entries} != set(MODELS):
                raise ValueError("Model ZIP must contain exactly the two pinned filenames")
            for entry in entries:
                if entry.file_size != MODELS[entry.filename][0] or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError("Invalid model ZIP entry")
                with z.open(entry) as src, (destination / entry.filename).open("xb") as out:
                    shutil.copyfileobj(src, out, length=1024 * 1024)
            verify_models(destination.resolve())
            for file in destination.iterdir():
                file.chmod(0o400)
    except BaseException:
        shutil.rmtree(destination)
        raise

def main():
    url = os.environ.get("CLIPCUTTER_MODEL_ZIP_URL", "")
    drive_id = os.environ.get("CLIPCUTTER_MODEL_DRIVE_ID", "")
    if drive_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", drive_id):
            raise ValueError("Invalid Drive file ID")
    else:
        validate_url(url)
    parent = Path(os.environ["RUNNER_TEMP"]).resolve()
    destination = parent / "clipcutter-authorized-models"
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        archive = Path(temp) / "models.zip"
        if drive_id:
            import gdown
            # Public owner-supplied archive; never use ambient Google cookies.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = gdown.download(id=drive_id, output=str(archive), quiet=True, use_cookies=False)
            if not result:
                raise ValueError("Drive download failed")
        else:
            opener = urllib.request.build_opener(HTTPSOnly())
            with opener.open(url, timeout=60) as response, archive.open("xb") as output:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > MAX_ARCHIVE:
                        raise ValueError("Model archive exceeds size limit")
                    output.write(block)
        if archive.stat().st_size > MAX_ARCHIVE:
            raise ValueError("Model archive exceeds size limit")
        unpack(archive, destination)
    with open(os.environ["GITHUB_ENV"], "a") as env:
        env.write("CLIPCUTTER_AUTHORIZED_MODEL_DIR=" + str(destination) + "\n")
    print("MODEL_SUPPLY=VERIFIED")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Network exceptions may contain signed URLs; never print them.
        raise SystemExit("Model supply failed; check URL validity, ZIP contents and pinned hashes") from None
