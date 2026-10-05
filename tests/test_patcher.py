"""
Unit tests for Patcher class.
"""

import os
import stat
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from agy_proxy.patcher import Patcher


class TestPatcher(unittest.TestCase):
    def setUp(self):
        self.patcher = Patcher()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_patch_binary_success(self):
        bin_path = os.path.join(self.temp_dir.name, "test_binary")
        with open(bin_path, "wb") as f:
            f.write(b"HELLO_WORLD_12345")
        os.chmod(bin_path, 0o755)

        # Replace 5 bytes with 5 bytes
        res = self.patcher.patch_binary(bin_path, b"WORLD", b"SPACE")
        self.assertTrue(res)

        with open(bin_path, "rb") as f:
            content = f.read()
        self.assertEqual(content, b"HELLO_SPACE_12345")
        # Ensure permissions were preserved
        st = os.stat(bin_path)
        self.assertTrue(bool(st.st_mode & stat.S_IXUSR))

    def test_patch_binary_length_mismatch(self):
        bin_path = os.path.join(self.temp_dir.name, "test_binary")
        with open(bin_path, "wb") as f:
            f.write(b"HELLO_WORLD")

        res = self.patcher.patch_binary(bin_path, b"WORLD", b"LONGER_REPLACEMENT")
        self.assertFalse(res)

    def test_patch_binary_not_found_file(self):
        missing_path = os.path.join(self.temp_dir.name, "nonexistent")
        res = self.patcher.patch_binary(missing_path, b"AAAA", b"BBBB")
        self.assertFalse(res)

    def test_patch_binary_target_bytes_not_found(self):
        bin_path = os.path.join(self.temp_dir.name, "test_binary")
        with open(bin_path, "wb") as f:
            f.write(b"HELLO_WORLD")

        res = self.patcher.patch_binary(bin_path, b"XYZ12", b"ABCDE")
        self.assertFalse(res)

    def test_inject_js_before_head(self):
        html_path = os.path.join(self.temp_dir.name, "index.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("<html><head><title>Test</title></head><body>Hello</body></html>")

        res = self.patcher.inject_js(html_path, "console.log('injected');")
        self.assertTrue(res)

        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("<script>\nconsole.log('injected');\n</script>\n</head>", content)

    def test_inject_js_before_body(self):
        html_path = os.path.join(self.temp_dir.name, "index_nobody.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("<html><body><h1>Title</h1></body></html>")

        res = self.patcher.inject_js(html_path, "console.log('body');")
        self.assertTrue(res)

        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("<script>\nconsole.log('body');\n</script>\n</body>", content)

    def test_inject_js_fallback(self):
        html_path = os.path.join(self.temp_dir.name, "snippet.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("<div>Simple snippet</div>")

        res = self.patcher.inject_js(html_path, "window.test = true;")
        self.assertTrue(res)

        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(content.endswith("<script>\nwindow.test = true;\n</script>\n"))

    def test_inject_js_file_not_found(self):
        res = self.patcher.inject_js("/path/does/not/exist.html", "code")
        self.assertFalse(res)

    @patch("subprocess.run")
    def test_resign_macos_binary(self, mock_run):
        bin_path = os.path.join(self.temp_dir.name, "macos_bin")
        with open(bin_path, "wb") as f:
            f.write(b"binary_code")

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        res = self.patcher.resign_macos_binary(bin_path)
        self.assertTrue(res)
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
