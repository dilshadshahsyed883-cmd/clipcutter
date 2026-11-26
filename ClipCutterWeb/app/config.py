from dataclasses import dataclass
import os
from urllib.parse import urlsplit

@dataclass(frozen=True)
class Settings:
    origin: str
    app_name: str = "ClipCutter Web"

def load_settings() -> Settings:
    raw = os.getenv("CLIPCUTTER_WEB_PUBLIC_ORIGIN", "https://clip.scenebuilder.online").strip().rstrip("/")
    parsed = urlsplit(raw)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.path or
            parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("CLIPCUTTER_WEB_PUBLIC_ORIGIN must be an HTTPS origin")
    return Settings(origin=raw)
