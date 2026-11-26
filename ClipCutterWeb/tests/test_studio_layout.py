from pathlib import Path
import unittest
from jinja2 import Environment,FileSystemLoader
ROOT=Path(__file__).resolve().parents[1]
class StudioLayoutTests(unittest.TestCase):
    def test_both_feature_templates(self):
        env=Environment(loader=FileSystemLoader(ROOT/"app/templates"))
        for kind in ("extractor","analyzer"):
            html=env.get_template("studio.html").render(page={"key":kind,"title":kind})
            for key in ("new","queue","results"):
                self.assertIn('data-view="'+key+'"',html)
                self.assertIn('id="studio-'+key+'"',html)
            self.assertNotIn("Submit input and processing settings",html)
            self.assertNotIn('name="source_kind"',html)
            self.assertEqual('id="reference-files"' in html,kind=="extractor")
            self.assertEqual("Advanced settings" in html,kind=="analyzer")
    def test_gpu_template_compact(self):
        html=(ROOT/"app/templates/gpu.html").read_text()
        self.assertNotIn("Use a separate dedicated ClipCutter group",html)
        self.assertIn('id="gpu-capability"',html)
        self.assertNotIn("<h2>GPU Config</h2>",html)
        self.assertNotIn('id="intake-capability"',html)
        self.assertGreater(html.index('id="gpu-capability"'),html.index("Worker status"))
        for action in ("start","stop","pause","resume","retry"):
            self.assertIn('id="gpu-'+action+'" disabled',html)
