"""Shared analysis + footage workflow. Review remains mandatory."""
from pathlib import Path
import copy
from .analysis_library import AnalysisLibrary, source_stamp
from .analysis import run
from .models import resolve_models
from .storage import Profiles, new_project
from .footage import Index, inspect_video, build_plan
from v22.engine import Engine
from v22.filters import DEFAULTS

def link_people(scene, data, valid_ids, source_footage=False):
    groups=[g for g in data["people"] if not g.get("ignored") and not g.get("filtered")
            and any(a<scene["end"] and b>scene["start"] for a,b in g.get("segments", []))]
    known=[g for g in groups if g.get("library_id") in valid_ids
           and g.get("identity_status") in ("manual","matched")]
    confirmed={str(g["library_id"]) for g in known}
    unknown={"unknown:"+data["source"]+":"+g["id"] for g in groups if g not in known}
    scene["people"]=sorted(confirmed|unknown)
    scene["person_names"]=sorted({g["name"] for g in groups})
    if source_footage:
        covered=set()
        for pid in confirmed:
            at=scene["start"]
            for a,b in sorted((a,b) for g in known if str(g["library_id"])==pid for a,b in g["segments"]):
                if b<=at: continue
                if a>at+1e-6: break
                at=max(at,b)
                if at>=scene["end"]-1e-6:
                    covered.add(pid);break
        confirmed=covered
    scene["confirmed_people"]=sorted(confirmed)

def generate(reference_path, folder, cfg, store, weights, limits, cancel, progress):
    """Only selected-folder footage is eligible. Cache misses get a fresh analysis.
    No identity inference based solely on filenames. Unknowns stay blocked.
    """
    reference_path=Path(reference_path).resolve()
    folder=Path(folder).resolve()
    if not folder.is_dir():raise ValueError("Choose a valid footage folder.")
    cfg=copy.deepcopy(cfg)
    cfg["filters"]={**DEFAULTS,**cfg.get("filters",{})}
    lib=AnalysisLibrary()
    engine=models=signature=profiles=None
    valid_ids={c.id for c in store.characters()} if store is not None else set()
    def check():
        if cancel():raise InterruptedError("Timeline generation cancelled")
    def get_analysis(path):
        nonlocal engine,models,signature,profiles
        check()
        cached=lib.find(path,cfg)
        if cached:return cached[1]
        if not cfg.get("custom_models") and not cfg.get("model_license_accepted"):
            raise ValueError("Accept model terms in Person Analyzer or choose licensed models in Settings.")
        if engine is None:
            models,signature=resolve_models(cfg,lambda name,n,total:progress("Downloading "+name,n,total),cancel)
            engine=Engine(models,cfg.get("gpu",True),cfg.get("size",640))
            profiles=Profiles(store).entries(signature,engine,cancel,[])
            cfg["model_signature"]=signature
        return run(str(path),new_project(),models,cfg,
                   lambda t,d,*rest:progress("Analyzing "+Path(path).name,t,d),
                   cancel,None,profiles,engine=engine)
    initial=source_stamp(reference_path)
    reference=inspect_video(reference_path,cancel,lambda a,b:progress("Reference scenes",a,b))
    data=get_analysis(reference_path)
    if source_stamp(reference_path)!=initial or data.get("source_stamp")!=initial:
        raise ValueError("Reference changed during processing.")
    for scene in reference["scenes"]:link_people(scene,data,valid_ids)
    idx=Index()
    indexed=idx.index(folder,cancel,lambda a,b:progress("Indexing footage",a,b))
    selected=[m for m in indexed if Path(m["path"]).resolve().is_relative_to(folder)
              and Path(m["path"]).resolve()!=reference_path]
    if not selected:raise ValueError("No eligible alternative videos found in the selected folder.")
    media=[]
    stamps={}
    warnings=[]
    for n,m in enumerate(selected):
        check()
        path=Path(m["path"])
        stamp=source_stamp(path)
        data=get_analysis(path)
        if source_stamp(path)!=stamp or data.get("source_stamp")!=stamp:
            raise ValueError("Footage changed during processing: "+path.name)
        item=copy.deepcopy(m)
        for scene in item["scenes"]:link_people(scene,data,valid_ids,True)
        media.append(item);stamps[str(path)]=stamp
        progress("Footage identities",n+1,len(selected))
    check()
    plan=build_plan(reference,media,weights,cancel=cancel,**limits)
    check()
    if source_stamp(reference_path)!=initial or any(source_stamp(path)!=stamp for path,stamp in stamps.items()):
        raise ValueError('Media changed during timeline generation; generate again.')
    missing=sum(not r.get("selected") for r in plan["rows"])
    if missing:warnings.append(f"{missing} scenes need manual replacement or verified person profiles.")
    plan["warnings"]=warnings
    return plan
