"""Authenticated private GPU transport; health endpoints are read-only."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib
import hmac
import json
import os
import re
import signal
from threading import Thread,BoundedSemaphore
from urllib.parse import urlsplit,parse_qs
from .runtime import warmup
from .transport import Worker,ApiError,CHUNK,canonical
from .extractor.runner import MAX_JSON

status={"ready":False,"state":"warming_up","service":"clipcutter-gpu","source_sha":os.environ.get("CLIPCUTTER_SOURCE_SHA","unknown")}
def initialize():
    try:
        if len(os.environ.get("CLIPCUTTER_WORKER_API_TOKEN",""))<32:raise RuntimeError("Independent API token required")
        result=warmup()
        status.update(result,state="ready",ready=True)
    except Exception as exc:
        print("Worker warmup failed:",type(exc).__name__,str(exc),flush=True)
        status.update(ready=False,state="not_ready")

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(30)
    def authorize(self):
        token=os.environ.get("CLIPCUTTER_WORKER_API_TOKEN","")
        if len(token)<32 or not hmac.compare_digest(self.headers.get("Authorization","").encode(),("Bearer "+token).encode()):
            raise ApiError(401,"unauthorized")
    def body(self,limit):
        if self.headers.get("Transfer-Encoding"):raise ApiError(400,"Content-Length required")
        try:n=int(self.headers.get("Content-Length",""))
        except ValueError:raise ApiError(400,"Invalid Content-Length") from None
        if not 0<n<=limit:raise ApiError(413,"Invalid request size")
        data=self.rfile.read(n)
        if len(data)!=n:raise ApiError(400,"Incomplete request")
        return data
    def object(self):
        try:return json.loads(self.body(MAX_JSON))
        except (ValueError,UnicodeError):raise ApiError(400,"Invalid JSON") from None
    def route(self,method):
        u=urlsplit(self.path);path=u.path;w=self.server.worker
        if method=="GET" and path in ("/healthz","/health/live"):return 200,{"ok":True,"service":"clipcutter-gpu"}
        if method=="GET" and path in ("/health","/health/ready"):return (200 if status["ready"] else 503),dict(status)
        self.authorize()
        if method=="GET" and path=="/api/capabilities":
            return 200,{"source_sha":status["source_sha"],"contract_version":2,"kinds":["extractor","analyzer"],"source_kinds":["video","youtube"],
                "ready":status["ready"],"dispatch_enabled":status["ready"],"transport":"verified-chunks-v1",
                "chunk_bytes":CHUNK,**w.metrics()}
        m=re.fullmatch(r"/api/jobs/([a-f0-9]{32})(?:/(start|cancel|purge|input|output)(?:/([A-Za-z0-9_.-]{1,128}))?)?",path)
        if not m:raise ApiError(404,"not_found")
        a,action,name=m.groups()
        if method=="POST" and action is None:return 200,w.create(a,self.object())
        if method=="GET" and action is None:return 200,w.snapshot(a)
        if method=="POST" and action=="start" and name is None:return 200,w.start(a)
        if method=="POST" and action=="cancel" and name is None:return 200,w.cancel(a)
        if method=="POST" and action=="purge" and name is None:
            b=self.object()
            if not isinstance(b,dict) or set(b)!={"confirmation"}:raise ApiError(400,"Confirmation required")
            return 200,w.purge(a,b["confirmation"])
        if action not in {"input","output"}:raise ApiError(404,"not_found")
        q=parse_qs(u.query)
        try:
            offset=int(q["offset"][0])
            if offset<0 or len(q["offset"])!=1:raise ValueError()
            if method=="PUT" and action=="input" and name:
                return 200,w.put(a,name,offset,self.body(CHUNK),self.headers.get("X-Chunk-SHA256",""))
            if method=="GET" and action=="output" and name:
                if len(q["length"])!=1:raise ValueError()
                return 200,w.fetch(a,name,offset,int(q["length"][0]))
        except (KeyError,ValueError):raise ApiError(400,"Invalid offset or length") from None
        raise ApiError(404,"not_found")
    def api(self,method):
        if not self.server.requests.acquire(blocking=False):
            self.respond(429,{"error":"HTTP capacity busy"});return
        try:
            try:code,data=self.route(method)
            except ApiError as exc:code,data=exc.code,{"error":str(exc)}
            except (OSError,TimeoutError):code,data=400,{"error":"Transfer interrupted or storage unavailable"}
            except Exception as exc:
                print("API failure:",type(exc).__name__,flush=True)
                code,data=500,{"error":"Worker internal error"}
            self.respond(code,data)
        except (OSError,TimeoutError):pass
        finally:self.server.requests.release()
    def do_GET(self):self.api("GET")
    def do_POST(self):self.api("POST")
    def do_PUT(self):self.api("PUT")
    def respond(self,code,body):
        binary=isinstance(body,bytes);data=body if binary else canonical(body)
        self.send_response(code)
        self.send_header("Content-Type","application/octet-stream" if binary else "application/json")
        if binary:self.send_header("X-Chunk-SHA256",hashlib.sha256(data).hexdigest())
        self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(data)))
        self.send_header("Connection","close");self.close_connection=True
        self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass

def main():
    server=ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","8080"))),Handler)
    server.worker=Worker("/data/jobs",lambda:status["ready"])
    server.requests=BoundedSemaphore(8)
    def stop(*args):
        status.update(ready=False,state="stopping")
        Thread(target=server.shutdown,daemon=True).start()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
    Thread(target=initialize,daemon=True).start()
    try:server.serve_forever()
    finally:server.worker.shutdown();server.server_close()
if __name__=="__main__":main()
