import unittest

from opencode_proxy.rtk_compressor import compress_rtk


class TestRTKCompressor(unittest.TestCase):

    def test_rtk_compression_ansi_and_dividers(self):
        raw_text = "\x1b[31mError:\x1b[0m System failed\n===============================\nLine 1   \n\n\n\nLine 2"
        compressed = compress_rtk(raw_text)
        self.assertNotIn("\x1b[31m", compressed)
        self.assertIn("---", compressed)
        self.assertIn("Line 1\n\nLine 2", compressed)

    def test_rtk_table_border_compression(self):
        table_raw = "| :--- | :---: | ---: |\n| Data 1 | Data 2 | Data 3 |"
        compressed = compress_rtk(table_raw)
        self.assertIn("|---|", compressed)


if __name__ == "__main__":
    unittest.main()
