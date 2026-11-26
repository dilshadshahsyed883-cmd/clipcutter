"""Regression tests for guarded deployment's private environment allowlist."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("check_env", Path(__file__).resolve().parents[1]/"deploy"/"check-env.py")
check_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_env)

class DeployEnvTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "CLIPCUTTER_AUTH_MODE": "local-admin",
            "CLIPCUTTER_WEB_PUBLIC_ORIGIN": "https://clip.scenebuilder.online",
            "CLIPCUTTER_WEB_HOST": "127.0.0.1",
            "CLIPCUTTER_WEB_SECURITY_DB": "/var/lib/clipcutter-web/security.sqlite3",
            "CLIPCUTTER_WEB_DATA_ROOT": "/var/lib/clipcutter-web",
            "CLIPCUTTER_ADMIN_USERNAME": "clip",
            "CLIPCUTTER_ADMIN_PASSWORD_HASH": "scrypt$16384$8$1$"+"a"*32+"$"+"b"*64,
            "CLIPCUTTER_ADMIN_SESSION_SECRET": "a"*40,
            "CLIPCUTTER_WEB_PORT": "18874",
        }
        self.gpu = {
            "CLIPCUTTER_SCHEDULER_ENABLED": "1",
            "CLIPCUTTER_LIFECYCLE_ENABLED": "1",
            "CLIPCUTTER_APPROVED_OWNER": "clip",
            "CLIPCUTTER_APPROVED_SALAD_GROUP": "/organizations/voice-generation/projects/default/containers/clipcutter-gpu",
            "CLIPCUTTER_APPROVED_WORKER_GATEWAY": "https://example.salad.cloud",
            "CLIPCUTTER_APPROVED_WORKER_SHA": "a"*40,
            "CLIPCUTTER_APPROVED_GPU_IMAGE": "ghcr.io/dilshadshahsyed883-cmd/clipcutter-gpu-private-test@sha256:"+"b"*64,
        }

    def test_base_and_approved_gpu(self):
        self.assertEqual(check_env.validate(self.base),18874)
        self.assertEqual(check_env.validate(self.base|self.gpu),18874)

    def test_unknown_or_missing_key(self):
        with self.assertRaises(SystemExit):
            check_env.validate(self.base|{"UNEXPECTED":"x"})
        values=self.base|self.gpu
        del values["CLIPCUTTER_APPROVED_GPU_IMAGE"]
        with self.assertRaises(SystemExit):
            check_env.validate(values)

    def test_invalid_approval_rejected(self):
        for key,value in [
            ("CLIPCUTTER_APPROVED_OWNER","other"),
            ("CLIPCUTTER_APPROVED_SALAD_GROUP","/organizations/voice-generation/projects/default/containers/concat-test-v1"),
            ("CLIPCUTTER_APPROVED_WORKER_GATEWAY","https://example.org"),
            ("CLIPCUTTER_APPROVED_WORKER_SHA","latest"),
            ("CLIPCUTTER_APPROVED_GPU_IMAGE","latest"),
            ("CLIPCUTTER_SCHEDULER_ENABLED","yes"),
            ("CLIPCUTTER_WEB_PORT","18873"),
        ]:
            with self.subTest(key=key), self.assertRaises(SystemExit):
                check_env.validate(self.base|self.gpu|{key:value})

    def test_optional_supported_flags(self):
        self.assertEqual(check_env.validate(self.base|self.gpu|{"CLIPCUTTER_YOUTUBE_DISPATCH_ENABLED":"1"}),18874)

if __name__=="__main__":
    unittest.main()
