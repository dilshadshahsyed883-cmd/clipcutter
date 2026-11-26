"""Start ClipCutter Web on a dedicated loopback listener."""
import os
import uvicorn

if __name__ == "__main__":
    host = os.getenv("CLIPCUTTER_WEB_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1"}:
        raise SystemExit("ClipCutter Web must listen on loopback only")
    port = int(os.environ["CLIPCUTTER_WEB_PORT"])
    if port < 1024 or port > 65535 or port == 18873:
        raise SystemExit("Invalid unprivileged port")
    from app.modules.studio.auto_intake import start
    stop=start()
    try:
        uvicorn.run("app.main:app", host=host, port=port, reload=False)
    finally:
        stop.set()
