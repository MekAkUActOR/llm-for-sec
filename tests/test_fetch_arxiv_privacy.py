"""fetch_arxiv_privacy 纯函数测试（无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_arxiv_privacy as fp  # noqa: E402


ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">42</opensearch:totalResults>
  <entry><id>http://arxiv.org/abs/2401.12345v2</id>
    <title>  Differential   Privacy in Practice </title>
    <summary> We study practical DP. </summary></entry>
  <entry><id>http://arxiv.org/abs/cs/0301012v1</id>
    <title>Old Paper</title><summary>Old summary.</summary></entry>
  <entry><id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Duplicate version</title><summary>Dup.</summary></entry>
</feed>"""


class TestParseAndFormat(unittest.TestCase):
    def test_parse_atom_ids_and_ws(self):
        rows = fp.parse_atom(ATOM)
        self.assertEqual(rows[0][0], "2401.12345")           # 版本剥离
        self.assertEqual(rows[0][1], "Differential Privacy in Practice")  # 空白规整
        self.assertEqual(rows[2][0], "2401.12345")           # v1 也剥离

    def test_total_results(self):
        self.assertEqual(fp.total_results(ATOM), 42)

    def test_format_doc(self):
        self.assertEqual(
            fp.format_doc("2401.12345", "T", "S"),
            "arXiv privacy research paper 2401.12345: T. S")

    def test_query_url(self):
        u = fp.query_url("differential-privacy", 200)
        self.assertIn("abs:%22differential+privacy%22", u)
        self.assertIn("cat:cs.CR", u)
        self.assertIn("start=200", u)
        self.assertIn("max_results=200", u)

    def test_all_queries_have_cat_filter(self):
        for name in fp.QUERIES:
            u = fp.query_url(name, 0)
            self.assertIn("cat:cs.CR+OR+cat:cs.LG+OR+cat:cs.DB", u)

    def test_norm_title(self):
        self.assertEqual(fp.norm_title("  A  Title "), "a title")


class TestExclusion(unittest.TestCase):
    def test_existing_ids_from_text_regex(self):
        line = ('{"text": "arXiv security research paper 2401.99999v1: T. S"}')
        m = fp._ID_IN_TEXT.search(line)  # jsonl 行有 JSON 前缀 → search 非 match
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "2401.99999v1")


if __name__ == "__main__":
    unittest.main()
