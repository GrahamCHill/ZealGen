import unittest
from zealgen.utils.url import normalize_url, get_filename_from_url, clean_domain

class TestUrlUtils(unittest.TestCase):
    def test_clean_domain(self):
        cases = [
            ("www.example.com", "example.com"),
            ("example.org", "example.org"),
            ("sub.example.com", "sub.example.com"),
            ("www.python.io", "python.io"),
            ("example.net", "example.net"),
        ]
        for domain, expected in cases:
            with self.subTest(domain=domain):
                self.assertEqual(clean_domain(domain), expected)

    def test_normalize_url(self):
        cases = [
            ("https://www.example.com/", "example.com"),
            ("http://example.com", "example.com"),
            ("https://example.com/path/", "example.com/path"),
            ("HTTPS://WWW.EXAMPLE.COM/Path", "example.com/path"),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(normalize_url(url), expected)

    def test_get_filename_from_url(self):
        cases = [
            ("https://example.com/", "example.com_index.html"),
            ("https://example.com/page.html", "example.com_page.html"),
            ("https://example.com/dir/", "example.com_dir_index.html"),
            ("https://sub.example.com/path/to/file", "sub.example.com_path_to_file_index.html"),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(get_filename_from_url(url), expected)

if __name__ == "__main__":
    unittest.main()
