"""Liveness/readiness only. No public media submission or GPU dispatch in Step 6."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hmac
import os
from threading import Thread
from .runtime import warmup

status={"ready":False,"state":"warming_up","service":"clipcutter-gpu","source_sha":os.environ.get("CLIPCUTTER_SOURCE_SHA","unknown")}
def initialize():
    try:
        result=warmup()
        status.update(result,state="ready",ready=True)
    except Exception as exc:
        print("Worker warmup failed:",type(exc).__name__,str(exc),flush=True)
        status.update(ready=False,state="not_ready")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz","/health/live"):
            self.respond(200,{"ok":True,"service":"clipcutter-gpu"})
        elif self.path in ("/health","/health/ready"):
            self.respond(200 if status["ready"] else 503,dict(status))
        elif self.path=="/api/capabilities":
            token=os.environ.get("CLIPCUTTER_WORKER_API_TOKEN","")
            supplied=self.headers.get("Authorization","")
            if len(token)<32 or not hmac.compare_digest(supplied.encode(),("Bearer "+token).encode()):
                self.respond(401,{"error":"unauthorized"})
            else:
                self.respond(200,{"source_sha":status["source_sha"],"contract_version":1,
                    "kinds":["extractor","analyzer"],"ready":status["ready"],
                    "dispatch_enabled":False,"transport":"staged-local-cli"})
        else:
            self.respond(404,{"error":"not_found"})
    def respond(self,code,body):
        data=json.dumps(body,separators=(",",":")).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers();self.wfile.write(data)
    def log_message(self,*args): pass

def main():
    Thread(target=initialize,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","8080"))),Handler).serve_forever()

if __name__=="__main__": main()
