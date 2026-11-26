"""Reference set contract and synthetic vector tests; no model downloads."""
import tempfile
import unittest
from pathlib import Path
import hashlib
import numpy as np
from worker.transport import Worker,ApiError
from worker.analyzer.reference_set import annotate_candidates
from worker.job import Staged

def sha(b):return hashlib.sha256(b).hexdigest()

class ReferenceTests(unittest.TestCase):
    def test_transport_accepts_profile_references(self):
        src=b"synthetic video";ref=b"synthetic reference"
        job={"job_id":"a"*32,"source_sha256":sha(src),"references_sha256":[sha(ref)],
             "request":{"request_id":"b"*32,"input":{"source":"https://drive.google.com/file/d/abcdefghijk/view"},
                        "settings":{"kind":"analyzer","profile_id":"c"*32}}}
        m={"job":job,"action":"analyze","files":{"source.video":{"size":len(src),"sha256":sha(src)},
                    "reference-01.img":{"size":len(ref),"sha256":sha(ref)}}}
        with tempfile.TemporaryDirectory() as tmp:
            w=Worker(Path(tmp),lambda:True)
            a="d"*32
            self.assertEqual(w.create(a,m)["state"],"staging")
            self.assertEqual(w.put(a,"reference-01.img",0,ref,sha(ref))["offset"],len(ref))
            with self.assertRaises(ApiError):w.create("e"*32,{**m,"job":{**job,"references_sha256":[]}})
    def test_anonymous_candidates_and_overlap(self):
        def group(e,segments,identity="unknown"):
            return {"identity_status":identity,"segments":segments,"observations":[{"embedding":e,"time":1.0}]}
        groups=[group([1.,0.],[[0.,2.]]),group([0.,1.],[[0.,2.]]),group([1.,0.],[[3.,4.]],"uncertain")]
        people=[{"name":"Person "+str(i),"segments":g["segments"]} for i,g in enumerate(groups)]
        data={"people":groups,"duration":5.,"sample_interval":1.,"filters":{"background":False,"static":False}}
        ref={"center":np.array([1.,0.],np.float32)}
        annotate_candidates(data,people,ref,lambda:False)
        self.assertEqual([p["reference_candidate"] for p in people],["review_candidate","not_candidate","not_evaluated"])
        self.assertEqual(people[0]["name"],"Person 0")
        self.assertNotIn("embedding",people[0])
        groups.append(group([1.,0.],[[0.,2.]]));people.append({"name":"Person 3","segments":[[0.,2.]]})
        annotate_candidates(data,people,ref,lambda:False)
        self.assertEqual(people[0]["reference_candidate"],"uncertain")
        self.assertEqual(people[3]["reference_candidate"],"uncertain")
