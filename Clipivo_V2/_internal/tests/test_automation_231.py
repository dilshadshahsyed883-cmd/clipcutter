from studio.analysis_library import source_stamp, scan_key, AnalysisLibrary
from studio.automation import link_people

def test_source_stamp_invalidates_changed_video(tmp_path):
    path=tmp_path/"video.mp4";path.write_bytes(b"old")
    before=source_stamp(path);path.write_bytes(b"changed")
    assert source_stamp(path)!=before

def test_scan_key_changes_for_scan_controls():
    assert scan_key({})!=scan_key({"step": .25})

def test_legacy_project_not_registered(tmp_path):
    video=tmp_path/"video.mp4";video.write_bytes(b"v")
    project=tmp_path/"analysis.json";project.write_text("{}")
    assert not AnalysisLibrary(tmp_path).register(project,{"source":str(video)})

def test_unknown_or_removed_profile_is_not_confirmed():
    scene={"start":0,"end":2}
    data={"source":"example.mp4","people":[{"id":"x","name":"Example","library_id":"p",
              "identity_status":"matched","segments":[[0,2]]}]}
    link_people(scene,data,set(),True)
    assert scene["people"] and not scene["confirmed_people"]

def test_partial_source_appearance_not_confirmed():
    scene={"start":0,"end":2}
    data={"source":"example.mp4","people":[{"id":"x","name":"Example","library_id":"p",
              "identity_status":"matched","segments":[[0,1]]}]}
    link_people(scene,data,{"p"},True)
    assert scene["people"]==["p"] and not scene["confirmed_people"]


def test_registered_analysis_reuses_only_matching_stamp_and_settings(tmp_path,monkeypatch):
    import json
    video=tmp_path/"video.mp4";video.write_bytes(b"v")
    project=tmp_path/"analysis.json"
    data={"source":str(video.resolve()),"source_stamp":source_stamp(video),
          "scan_key":scan_key({}),"version":2,"people":[],"duration":1,"sample_interval":.5}
    project.write_text(json.dumps(data))
    monkeypatch.setattr("studio.analysis.open_project",lambda p:json.loads(p.read_text()))
    lib=AnalysisLibrary(tmp_path)
    assert lib.register(project,data)
    assert lib.find(video,{})[0]==project
    assert lib.find(video,{"step":.25}) is None
    video.write_bytes(b"changed")
    assert lib.find(video,{}) is None
    assert project.is_file()

def test_source_identity_requires_continuous_coverage():
    scene={"start":1,"end":2}
    data={"source":"example.mp4","people":[{"id":"x","name":"Example","library_id":"p",
              "identity_status":"matched","segments":[[0,1],[1,1.5],[1.5,2]]}]}
    link_people(scene,data,{"p"},True)
    assert scene["confirmed_people"]==["p"]
