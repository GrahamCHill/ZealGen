import unittest
import pathlib
import tempfile
import shutil
import anyio
from docugen.assets.rewrite import rewrite_assets

class TestAssetRewrite(unittest.TestCase):
    def setUp(self):
        self.test_dir = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_rewrite_assets_skips_missing(self):
        # We can't easily test real downloads without mocking httpx
        # but we can test if it returns the same HTML if no assets are found or reachable
        html = "<html><body><p>No assets</p></body></html>"
        result = anyio.run(rewrite_assets, html, "https://example.com", self.test_dir)
        self.assertIn("No assets", result)

if __name__ == "__main__":
    unittest.main()
