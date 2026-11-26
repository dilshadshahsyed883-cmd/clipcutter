"""Ephemeral comparison against one user-selected reference set.
Uses desktop consistency threshold; never assigns names or persists embeddings.
"""
import numpy as np
from .vendor.engine import unit
from .vendor.filters import filter_observations
from .vendor.analyzer import intervals

THRESHOLD=.60
MARGIN=.08

def load_reference_set(refs,engine,cancel):
    import cv2
    embeddings=[]
    for _,blob in refs:
        if cancel():raise InterruptedError("Cancelled")
        img=cv2.imdecode(np.frombuffer(blob,np.uint8),cv2.IMREAD_COLOR)
        if img is None:continue
        faces=engine.get(img)
        if len(faces)==1:embeddings.append(unit(faces[0][0]))
    result={"valid_count":len(embeddings),"status":"no_valid_references","center":None}
    if not embeddings:return result
    try:
        center=unit(np.mean(embeddings,axis=0))
        if not all(float(np.dot(e,center))>=THRESHOLD for e in embeddings):
            result["status"]="inconsistent_references";return result
    except (ValueError,TypeError):result["status"]="inconsistent_references";return result
    result.update(status="ready_for_comparison",center=center)
    return result

def annotate_candidates(data,people,ref,cancel):
    center=ref["center"];candidates=[]
    for g,p in zip(data["people"],people):
        if cancel():raise InterruptedError("Cancelled")
        p["reference_candidate"]="not_evaluated"
        if center is None or g.get("filtered") or g.get("ignored") or g.get("identity_status")=="uncertain":continue
        active,_=filter_observations(g,data,intervals)
        try:
            vecs=[unit(o["embedding"]) for o in active]
            if not vecs or any(len(e)!=len(center) for e in vecs):continue
            group_center=unit(np.mean(vecs,axis=0));score=float(np.dot(group_center,center))
            if score>=THRESHOLD and all(float(np.dot(e,group_center))>=THRESHOLD for e in vecs):
                p["reference_candidate"]="review_candidate";candidates.append(p)
            else:p["reference_candidate"]="uncertain" if score>=THRESHOLD-MARGIN else "not_candidate"
        except (ValueError,TypeError,KeyError):continue
    for p in candidates:
        if any(a<d and c<b for other in candidates if other is not p for a,b in p["segments"] for c,d in other["segments"]):
            p["reference_candidate"]="uncertain"
