import tempfile,unittest
from pathlib import Path
from v22.model_locator import find_models,NAMES
class LocatorTests(unittest.TestCase):
    def test_standard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); p=root/'local/Clipivo/models/buffalo_l'; p.mkdir(parents=True)
            for n in NAMES: (p/n).write_bytes(b'x')
            self.assertEqual(find_models(root/'invalid',home=root/'home',local=root/'local',roaming=root/'roaming'),p)
    def test_install_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); p=root/'local/Programs/Clipivo/_internal/custom'; p.mkdir(parents=True)
            (p/NAMES[0]).write_bytes(b'x')
            kw=dict(home=root/'home',local=root/'local',roaming=root/'roaming')
            self.assertIsNone(find_models(**kw)); (p/NAMES[1]).write_bytes(b'x')
            self.assertEqual(find_models(**kw),p)
