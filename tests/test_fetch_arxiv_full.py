"""fetch_arxiv_full 纯函数单测（版本号剥离 / Atom 解析 / 去重 / 转换格式）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_arxiv_full import (  # noqa: E402
    format_doc,
    norm_title,
    parse_atom,
    strip_version,
)

_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>arXiv Query</title>
  <entry>
    <id>http://arxiv.org/abs/2609.26761v1</id>
    <title> A2M: Trace-Optimized
      Agent Hijacking </title>
    <summary> We introduce
      A2M. </summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/cs/0301012v3</id>
    <title>Old-style paper</title>
    <summary>Old summary.</summary>
  </entry>
  <entry>
    <id>http://example.org/not-arxiv</id>
    <title>Bad id</title>
    <summary>Skipped.</summary>
  </entry>
</feed>"""


class TestStripVersion(unittest.TestCase):
    def test_new_style(self):
        self.assertEqual(strip_version("2609.26761v2"), "2609.26761")

    def test_old_style(self):
        self.assertEqual(strip_version("cs/0301012v1"), "cs/0301012")

    def test_no_version(self):
        self.assertEqual(strip_version("2609.26761"), "2609.26761")

    def test_dedup_across_versions(self):
        """同一论文不同版本必须折叠为同一 id（去重正确性）。"""
        self.assertEqual(strip_version("2609.26761v1"),
                         strip_version("2609.26761v9"))


class TestParseAtom(unittest.TestCase):
    def test_parse_and_normalize(self):
        entries = parse_atom(_ATOM)
        # 非 arxiv.org/abs/ 的 id 跳过；标题/摘要空白规范化
        self.assertEqual(entries, [
            ("2609.26761", "A2M: Trace-Optimized Agent Hijacking",
             "We introduce A2M."),
            ("cs/0301012", "Old-style paper", "Old summary."),
        ])

    def test_version_stripped_in_parse(self):
        entries = parse_atom(_ATOM)
        self.assertTrue(all(not e[0].endswith(tuple(f"v{i}" for i in range(10)))
                            for e in entries))


class TestFormatDoc(unittest.TestCase):
    def test_format_with_id(self):
        d = format_doc("2609.26761", "A2M: Trace-Optimized Agent Hijacking",
                       "We introduce A2M.")
        self.assertEqual(
            d, "arXiv security research paper 2609.26761: "
               "A2M: Trace-Optimized Agent Hijacking. We introduce A2M.")

    def test_id_dedupable_from_text(self):
        """嵌入的 id 可从文本再提取（后续去重可用）。"""
        import re
        d = format_doc("cs/0301012", "T", "S.")
        m = re.search(r"paper (\S+):", d)
        self.assertEqual(m.group(1), "cs/0301012")


class TestNormTitle(unittest.TestCase):
    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(norm_title("  A2M: Trace-Optimized  Agent "),
                         "a2m: trace-optimized agent")


if __name__ == "__main__":
    unittest.main()
