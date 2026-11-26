"""Host-side non-GPU entrypoint and authenticated capability checks."""
import json,os,time,urllib.request,urllib.error
base=os.environ["SMOKE_BASE"]
def get(path,token=None):
    req=urllib.request.Request(base+path,headers={"Authorization":"Bearer "+token} if token else {})
    try:
        with urllib.request.urlopen(req,timeout=3) as res:return res.status,json.load(res)
    except urllib.error.HTTPError as exc:return exc.code,json.load(exc)
for _ in range(30):
    try:
        code,data=get("/health/live")
        if code==200:break
    except OSError:pass
    time.sleep(1)
else:raise RuntimeError("Worker entrypoint did not start")
assert data=={"ok":True,"service":"clipcutter-gpu"}
assert get("/api/capabilities")[0]==401
code,data=get("/api/capabilities",os.environ["SMOKE_TOKEN"])
assert code==200 and data["source_sha"]==os.environ["EXPECTED_SOURCE_SHA"]
assert data["contract_version"]==1 and data["dispatch_enabled"] is False and data["ready"] is False
assert get("/health/ready")[0]==503
print("ENTRYPOINT_SMOKE=PASS (no physical GPU tested)")
