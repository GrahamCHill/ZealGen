import unittest
import os
import shutil
import tempfile
import sqlite3
from zealgen.docset.builder import DocsetBuilder
from zealgen.parsers.base import ParsedPage

class TestDocsetBuilder(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.test_dir, "Test.docset")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_initialization(self):
        builder = DocsetBuilder(self.output_path)
        self.assertEqual(builder.docset_name, "Test")
        self.assertTrue(os.path.exists(builder.documents_path))
        self.assertTrue(os.path.exists(os.path.join(builder.resources_path, "docSet.dsidx")))

    def test_add_page(self):
        builder = DocsetBuilder(self.output_path)
        page = ParsedPage("Title", "<html><body>Content</body></html>", [("Sym", "Type", "anchor")])
        builder.add_page(page, "https://example.com/page")
        
        expected_file = os.path.join(builder.documents_path, "example.com_page.html")
        self.assertTrue(os.path.exists(expected_file))
        
        # Check index
        builder.finalize()
        conn = sqlite3.connect(os.path.join(builder.resources_path, "docSet.dsidx"))
        cursor = conn.execute("SELECT name, type, path FROM searchIndex")
        row = cursor.fetchone()
        self.assertEqual(row, ("Sym", "Type", "example.com_page.html#anchor"))
        conn.close()

if __name__ == "__main__":
    unittest.main()
