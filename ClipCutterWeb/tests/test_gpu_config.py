import os
import unittest
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app.modules.studio.gpu import GPUSettings, GPUUpdate, GPUStore, image_pull_percent, read_status, group_path
from app.modules.studio.store import Store
import test_admin_security

API="/api/v1/gpu"
class GPUContractTests(unittest.TestCase):
    def test_defaults_and_units(self):
        cfg=GPUSettings()
        self.assertEqual((cfg.auto_start,cfg.image_pull_threshold,cfg.image_pull_seconds,cfg.salad_max_reallocations,cfg.salad_reallocate_cooldown),(False,8,20,3,30))
        for value,expected in ((.30,30),(30,30),(1.0,100),(0,0),(None,None),(True,None),(-1,None),(101,None),(float("nan"),None)):
            self.assertEqual(image_pull_percent(value),expected)
        for change in ({"salad_max_reallocations":4},{"image_pull_threshold":0},{"image_pull_seconds":4},{"parallel":3},{"salad_organization":"../other"},{"worker_gateway":"http://example.org"},{"worker_key":"x"*16}):
            with self.assertRaises(ValidationError): GPUUpdate.model_validate(change)

    def test_fixed_origin_read_only_status_and_no_secrets(self):
        cfg=GPUSettings(salad_organization="org",salad_project="proj",salad_container_group="clip-group")
        requests=[]
        key="s"*32
        def response(req):
            requests.append((req.method,str(req.url)))
            self.assertEqual(req.headers["Salad-Api-Key"],key)
            self.assertEqual(req.url.host,"api.salad.com")
            if req.url.path.endswith("/instances"):
                return httpx.Response(200,json={"instances":[{"id":"test","state":"downloading","ready":False,"pulling_progress":.30}]})
            return httpx.Response(200,json={"current_state":{"status":"running"},"replicas":1,"autostart_policy":False,"secret":key})
        client=httpx.Client(transport=httpx.MockTransport(response),follow_redirects=False)
        with patch("app.modules.studio.gpu.httpx.Client",return_value=client):
            result=read_status(cfg,key)
        self.assertTrue(result["dedicated_group_compatible"])
        self.assertEqual(result["instances"][0]["pulling_progress"],30)
        self.assertFalse(result["dispatch_enabled"])
        self.assertNotIn(key,str(result))
        self.assertEqual([x[0] for x in requests],["GET","GET"])

class GPUWebTests(unittest.TestCase):
    setUp=test_admin_security.LocalAdminSecurityTests.setUp
    _form=test_admin_security.LocalAdminSecurityTests._form
    _login=test_admin_security.LocalAdminSecurityTests._login
    _signed_in=test_admin_security.LocalAdminSecurityTests._signed_in
    _post=test_admin_security.LocalAdminSecurityTests._post

    def test_configuration_persistence_and_action_gate(self):
        for path in ("/studio/gpu-config",API+"/config",API+"/status"):
            self.assertEqual(self.client.get(path).status_code,401)
        csrf=self._signed_in()
        for path in ("/studio/extractor","/studio/analyzer","/studio/gpu-config"):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn("GPU Config",response.text)
        self.assertIn("Save Automation Settings",self.client.get("/studio/gpu-config").text)
        data={"auto_start":True,"image_pull_threshold":12,"salad_organization":"org","salad_project":"proj","salad_container_group":"clip-group","salad_key":"secret-"+"x"*32,"worker_key":"worker-"+"y"*32}
        self.assertEqual(self._post(API+"/config","invalid",data).status_code,403)
        response=self._post(API+"/config",csrf,data)
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()["salad_key_configured"])
        self.assertNotIn(data["salad_key"],response.text)
        self.assertNotIn(data["worker_key"],response.text)
        self.assertEqual(GPUStore(Store("owner")).public()["image_pull_threshold"],12)
        self.assertEqual(GPUStore(Store("another")).public()["image_pull_threshold"],8)
        invalid=self._post(API+"/config",csrf,{**data,"worker_key":"short-secret"})
        self.assertEqual(invalid.status_code,422)
        self.assertNotIn("short-secret",invalid.text)
        for action in ("start","stop","retry"):
            self.assertEqual(self._post(API+"/actions/"+action,csrf).status_code,409)
        self.assertTrue(self._post(API+"/actions/pause",csrf).json()["paused"])
        self.assertTrue(self.client.get("/api/v1/studio/requests?kind=extractor").json()["paused"])
        self.assertFalse(self._post(API+"/actions/resume",csrf).json()["paused"])
