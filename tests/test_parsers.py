import unittest
from zealgen.parsers.generic import GenericParser

class TestGenericParser(unittest.TestCase):
    def setUp(self):
        self.parser = GenericParser()

    def test_matches(self):
        self.assertTrue(self.parser.matches("any html"))

    def test_parse_title(self):
        html = "<html><head><title>Test Title</title></head></html>"
        parsed = self.parser.parse(html)
        self.assertEqual(parsed.title, "Test Title")

    def test_parse_symbols(self):
        html = """
        <html>
            <body>
                <h1 id="header1">Header 1</h1>
                <h2 id="header2">Header 2</h2>
                <h3>No ID</h3>
                <h3 id="header3">Header 3</h3>
            </body>
        </html>
        """
        parsed = self.parser.parse(html)
        expected_symbols = [
            ("Header 1", "Section", "header1"),
            ("Header 2", "Section", "header2"),
            ("Header 3", "Section", "header3"),
        ]
        self.assertEqual(parsed.symbols, expected_symbols)

if __name__ == "__main__":
    unittest.main()
