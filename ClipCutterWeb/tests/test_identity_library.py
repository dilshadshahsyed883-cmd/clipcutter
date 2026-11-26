import hashlib,tempfile,unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from fastapi import UploadFile,HTTPException
from app.modules.studio.store import Store
from app.modules.studio import identity_library as lib,output_names as names
from app.modules.studio.uploads import stage_uploads
from app.modules.studio.dispatch import Dispatcher
from test_studio import request,StudioWebTests,API
from test_gpu_dispatch import Fake

PNG=b"\x89PNG\r\n\x1a\nfake"
class IdentityTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup)
        self.base=Path(d.name).resolve();self.s=Store("owner",self.base)
        for mod in ("identity_library","uploads","output_names"):
            p=patch("app.modules.studio."+mod+".RESERVE",0);p.start();self.addCleanup(p.stop)
    def img(self,data=PNG,name="face.png"):
        return UploadFile(filename=name,file=BytesIO(data))
    def job(self,i,key):
        p=request();p["request_id"]=key*32;p["settings"].pop("reference_link",None)
        return lib.create_request(self.s,lib.IdentityRequest(identity_id=i,request=p))
    def test_snapshot_rename_delete_owner(self):
        i=lib.create(self.s,"Alex Eala")["id"]
        lib.add_files(self.s,i,[self.img()])
        with self.assertRaises(HTTPException):lib.add_files(self.s,i,[self.img(name="duplicate.png")])
        j=self.job(i,"a");self.assertEqual(self.job(i,"a")["id"],j["id"])
        image=lib.listing(self.s)[0]["images"][0]["id"]
        lib.rename_image(self.s,i,image,"portrait")
        lib.rename(self.s,i,"Alex New")
        lib.delete(self.s,i)
        self.assertEqual(lib.listing(self.s),[])
        self.assertEqual(lib.listing(Store("other",self.base)),[])
        with self.assertRaises(HTTPException):lib.image_path(Store("other",self.base),i,image)
        tmp=self.base/"stage";tmp.mkdir();manifest=[]
        stage_uploads(self.s,j["id"],j["settings"]["reference_uploads"],tmp,manifest,1000)
        self.assertEqual((tmp/manifest[0]["file"]).read_bytes(),PNG)
        with self.s.connect() as c:self.assertEqual(c.execute("SELECT label FROM request_identities WHERE job_id=?",(j["id"],)).fetchone()[0],"Alex Eala")
    def test_numbering_rename_and_zip(self):
        i=lib.create(self.s,"Alex Eala")["id"];lib.add_files(self.s,i,[self.img()])
        j=self.job(i,"a")["id"];k=self.job(i,"b")["id"]
        def item(name):return {"name":name,"size":len(PNG),"sha256":hashlib.sha256(PNG).hexdigest(),"media_type":"video/mp4","duration_ms":1000}
        a=[item("clip_001.mp4"),item("clip_002.mp4")]
        names.allocate(self.s,j,a);names.allocate(self.s,j,a);names.allocate(self.s,k,[item("clip.mp4")],True)
        self.assertEqual(names.alias_for(self.s,j,a[0]["name"]),"Alex_Eala_001.mp4")
        self.assertEqual(names.alias_for(self.s,k,"clip.mp4"),"Alex_Eala_Stitched_003.mp4")
        for x,y in (("awaiting_input","staging"),("staging","ready"),("ready","processing"),("processing","delivering")):self.s.transition(j,x,y,"test")
        dest=self.s.root/"outputs"/j;dest.mkdir(parents=True)
        for x in a:(dest/x["name"]).write_bytes(PNG)
        self.s.publish_verified_outputs(j,a)
        Dispatcher(self.s,Fake())
        with self.s.connect() as c:
            c.execute("INSERT INTO gpu_attempts VALUES (?,?,?,?,?,?,?,NULL,NULL)",(j,"a"*32,"{}","{}","acknowledged","1"*40,"https://example.salad.cloud"))
        names.change(self.s,j,names.Change(action="rename",ids=[a[0]["name"]],name="New_001.mp4"))
        self.assertEqual(names.download(self.s,j,a[0]["name"])[2],"New_001.mp4")
        p=names.make_zip(self.s,j,[a[0]["name"]]);import zipfile
        with zipfile.ZipFile(p) as z:self.assertEqual(z.namelist(),["New_001.mp4"])
        p.unlink()
        names.change(self.s,j,names.Change(action="delete",ids=[a[0]["name"]]))
        self.assertEqual(len(names.visible(self.s,j)["outputs"]),1)
        self.assertEqual(len(self.s.output_list(j)),2)
    def test_replace_snapshot(self):
        i=lib.create(self.s,"Person")["id"];lib.add_files(self.s,i,[self.img()])
        old=lib.listing(self.s)[0]["images"][0]
        lib.add_files(self.s,i,[self.img(PNG+b"new")],old["id"])
        self.assertNotEqual(lib.listing(self.s)[0]["images"][0]["sha256"],old["sha256"])

class IdentityRoutes(unittest.TestCase):
    setUp=StudioWebTests.setUp
    _form=StudioWebTests._form
    _login=StudioWebTests._login
    _signed_in=StudioWebTests._signed_in
    _post=StudioWebTests._post
    def test_identity_routes(self):
        self.assertEqual(self.client.get(API+"/identities").status_code,401)
        csrf=self._signed_in()
        self.assertEqual(self._post(API+"/identities","bad",{"name":"Person"}).status_code,403)
        r=self._post(API+"/identities",csrf,{"name":"Person"})
        self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.get(API+"/identities").json()["identities"][0]["name"],"Person")
