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
            self.assertNotIn("/api/v1/studio/performance-report",html)
            self.assertNotIn("Submit input and processing settings",html)
            self.assertNotIn('name="source_kind"',html)
            self.assertEqual('id="reference-files"' in html,kind=="extractor")
            self.assertEqual("Advanced settings" in html,kind=="analyzer")
    def test_four_input_row(self):
        env=Environment(loader=FileSystemLoader(ROOT/"app/templates"))
        html=env.get_template("studio.html").render(page={"key":"extractor","title":"Clip Extractor"})
        row=html.split('studio-input-row">',1)[1].split('<div id="reference-details">',1)[0]
        for control in ('name="source"','name="output_folder"','name="reference_mode"','id="reference-browse"','name="reference_link"'):
            self.assertIn(control,row)
        self.assertNotIn('id="reference-preview"',row)
        css=(ROOT/"app/static/studio.css").read_text()
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))",css)
    def test_gpu_template_compact(self):
        html=(ROOT/"app/templates/gpu.html").read_text()
        self.assertEqual(html.count("/api/v1/studio/performance-report"),1)
        self.assertIn('name="hours"',html)
        self.assertIn('value="24" selected',html)
        self.assertNotIn("Use a separate dedicated ClipCutter group",html)
        self.assertIn('id="gpu-capability"',html)
        self.assertNotIn("<h2>GPU Config</h2>",html)
        self.assertNotIn('id="intake-capability"',html)
        self.assertGreater(html.index('id="gpu-capability"'),html.index("Worker status"))
        for action in ("start","stop","pause","resume","retry"):
            self.assertIn('id="gpu-'+action+'" disabled',html)

    def test_cached_gpu_status_does_not_flash_loading_or_rebuild_unchanged_rows(self):
        js=(ROOT/"app/static/gpu.js").read_text()
        self.assertIn('if(live){setDisabled("gpu-refresh",true);setText("gpu-status","Checking SaladCloud…");}',js)
        self.assertIn('if(el.textContent!==value)el.textContent=value;',js)
        self.assertIn('if(signature!==instanceSignature)',js)
        self.assertIn('api(live?"/status":"/status/cached")',js)
        self.assertNotIn('if(!$("gpu-instances").children.length)',js)

    def test_delete_without_browser_popup(self):
        js=(ROOT/"app/static/studio.js").read_text()
        self.assertNotIn("confirm(",js)
        self.assertIn('await api("/requests/"+job.id,"DELETE")',js)
        self.assertIn("deleting.has(job.id)",js)
        self.assertIn("deleted.add(job.id)",js)

    def test_identity_library_controls(self):
        env=Environment(loader=FileSystemLoader(ROOT/"app/templates"))
        html=env.get_template("studio.html").render(page={"key":"extractor","title":"Clip Extractor"})
        for id in ("identity-dialog","identity-add","identity-rename","identity-delete-selected","identity-files","identity-import","output-zip","output-identity-filter"):
            self.assertIn('id="'+id+'"',html)
        self.assertNotIn('id="identity-dialog"',env.get_template("studio.html").render(page={"key":"analyzer","title":"Person Analyzer"}))

    def test_review_preview_and_output_view(self):
        env=Environment(loader=FileSystemLoader(ROOT/"app/templates"))
        html=env.get_template("studio.html").render(page={"key":"extractor","title":"Clip Extractor"})
        for control in ("review-video","review-timeline","review-seek","output-view"):
            self.assertIn('id="'+control+'"',html)
        self.assertIn("Scan settings",html)
        self.assertIn("Encoding settings",html)
        other=env.get_template("studio.html").render(page={"key":"analyzer","title":"Analyzer"})
        self.assertNotIn('id="review-video"',other)
        self.assertNotIn('id="output-view"',other)

    def test_analyzer_dominance_controls(self):
        env=Environment(loader=FileSystemLoader(ROOT/"app/templates"))
        html=env.get_template("studio.html").render(page={"key":"analyzer","title":"Analyzer"})
        self.assertIn('name="dominant_face_ratio"',html)
        self.assertNotIn('name="dominant_face_ratio"',env.get_template("studio.html").render(page={"key":"extractor","title":"Extractor"}))
