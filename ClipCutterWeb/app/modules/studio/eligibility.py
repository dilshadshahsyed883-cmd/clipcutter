"""One shared eligibility policy for lifecycle and dispatch."""
import os
from .drive_delivery import allowed

def blocker(request):
    inp=request["input"];settings=request["settings"];kind=inp["source_kind"]
    if kind not in ("video","youtube"):return "Single-video staged input required"
    if kind=="youtube" and os.environ.get("CLIPCUTTER_YOUTUBE_DISPATCH_ENABLED")!="1":
        return "YouTube GPU worker approval required"
    if settings["kind"]=="analyzer" and (settings.get("reference_link") or settings.get("reference_uploads")):
        return "Analyzer reference profiles are not supported"
    if inp.get("output_folder") and not allowed(inp["output_folder"]):
        return "Approved Drive delivery credentials and destination required"
    return None
