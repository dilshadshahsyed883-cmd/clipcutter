"""Keep desktop release metadata centralized without changing JSON schema."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ReleaseVersionConsistency(unittest.TestCase):
    def test_version_metadata(self):
        source = ast.parse((ROOT / 'version.py').read_text(encoding='utf-8'))
        assignments = {t.id: ast.literal_eval(n.value) for n in source.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        version = assignments['__version__']
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        self.assertIn('V' + version, (ROOT / 'docs' / 'README.md').read_text(encoding='utf-8'))
        for relative in ('app.py', 'ui/about_dialog.py', 'studio/timeline_window.py'):
            tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'))
            self.assertTrue(any(isinstance(n, ast.ImportFrom) and n.module == 'version' and any(a.name == '__version__' for a in n.names) for n in ast.walk(tree)), relative)
        # The frozen analyzer has independent component metadata; do not mutate it for a desktop release.

if __name__ == '__main__':
    unittest.main()
