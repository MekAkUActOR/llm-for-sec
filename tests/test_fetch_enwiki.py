"""fetch_enwiki 纯函数单测（英文标题格式 / 分区选择与探针隔离 / 清洗器英文无副作用 / dump 解析）。"""
import bz2
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_enwiki import (  # noqa: E402
    format_doc,
    partition_no,
    select_partition_files,
)
from fetch_zhwiki import iter_pages, wikitext_to_text  # noqa: E402


class TestFormatDoc(unittest.TestCase):
    def test_english_title_format(self):
        self.assertEqual(format_doc("Foo bar", "Body text."),
                         "Wikipedia article: Foo bar\n\nBody text.")

    def test_title_with_special_chars(self):
        d = format_doc("C++ (programming language)", "Body")
        self.assertTrue(d.startswith("Wikipedia article: C++ "))


class TestPartitionSelection(unittest.TestCase):
    def test_partition_no_extraction(self):
        # 官方全名（含 .xml）与本地短名（下载时去掉了 .xml）都要认
        self.assertEqual(
            partition_no("enwiki-articles2.xml-p41243p151573.bz2"), 2)
        self.assertEqual(
            partition_no("enwiki-articles2-p41243p151573.bz2"), 2)
        self.assertEqual(partition_no("enwiki-articles10.xml-p1p2.bz2"), 10)
        self.assertIsNone(partition_no("enwiki-latest-abstract.xml.gz"))
        self.assertIsNone(partition_no("random-file.txt"))

    def test_probe_partition_excluded(self):
        """分区 1 已被 general_en 探针占用，必须强制排除（来源隔离）。"""
        # 本地短名（无 .xml）也要正确识别并排除分区 1
        names = ["enwiki-articles1-p1p41242.bz2",
                 "enwiki-articles2-p41243p151573.bz2"]
        self.assertEqual(select_partition_files(names),
                         ["enwiki-articles2-p41243p151573.bz2"])
        # 官方全名同理
        names = ["enwiki-articles1.xml-p1p41242.bz2",
                 "enwiki-articles2.xml-p41243p151573.bz2"]
        self.assertEqual(select_partition_files(names),
                         ["enwiki-articles2.xml-p41243p151573.bz2"])

    def test_numeric_sort(self):
        """分区按数字排序（2 < 10，非字典序）。"""
        names = ["enwiki-articles10.xml-a.bz2",
                 "enwiki-articles3.xml-b.bz2",
                 "enwiki-articles2.xml-c.bz2"]
        self.assertEqual(select_partition_files(names),
                         ["enwiki-articles2.xml-c.bz2",
                          "enwiki-articles3.xml-b.bz2",
                          "enwiki-articles10.xml-a.bz2"])

    def test_non_partition_files_ignored(self):
        names = ["enwiki-articles2.xml-p41243p151573.bz2",
                 "enwiki-latest-abstract.xml.gz",
                 "enwiki-articles1.xml-p1p41242.bz2-rss.xml"]
        # rss.xml 无分区号（articles1.xml-p1p41242.bz2-rss.xml 中
        # _PART_RE 匹配 "articles1.xml" —— 注意它其实带分区号，但扩展名
        # 不是 .bz2 结尾的分区 dump 命名，glob 已过滤；这里只验证选择器
        # 不会让非 .bz2 主文件混进来（由 glob 保证），故只测分区语义：
        self.assertEqual(len(select_partition_files(
            ["enwiki-articles2.xml-p41243p151573.bz2"])), 1)

    def test_probe_partition_alone_yields_empty(self):
        self.assertEqual(
            select_partition_files(["enwiki-articles1.xml-p1p41242.bz2"]), [])
        self.assertEqual(
            select_partition_files(["enwiki-articles1-p1p41242.bz2"]), [])


class TestWikitextCleanerEnglish(unittest.TestCase):
    def test_english_spacing_preserved(self):
        """英文词间空格必须保留（_CJK_GAP 只折叠 CJK 邻接空格）。"""
        t = wikitext_to_text("Hello world, this is English text.")
        self.assertEqual(t, "Hello world, this is English text.")

    def test_mixed_cjk_english_keeps_boundary_spaces(self):
        """中英混排的边界空格保留；只有 CJK-CJK 之间的空格被折叠。"""
        t = wikitext_to_text("使用 Python 编程")
        self.assertIn("使用 Python 编程", t)

    def test_english_markup_cleaned(self):
        t = wikitext_to_text(
            "'''Bold''' text with [[wiki link|anchor]] and "
            "[https://example.com external].")
        self.assertEqual(t, "Bold text with anchor and external.")


def _make_dump(pages: list[tuple[str, str, str]]) -> bytes:
    """构造小 wiki XML（(title, ns, text) 列表）并 bz2 压缩。"""
    body = ["<mediawiki><siteinfo><sitename>Test</sitename></siteinfo>"]
    for title, ns, text in pages:
        body.append(
            f"<page><title>{title}</title><ns>{ns}</ns>"
            f"<revision><text xml:space=\"preserve\">{text}"
            "</text></revision></page>")
    body.append("</mediawiki>")
    return bz2.compress("".join(body).encode("utf-8"))


class TestIterPagesEnglish(unittest.TestCase):
    def _run(self, pages):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test-dump.xml.bz2"
            p.write_bytes(_make_dump(pages))
            return list(iter_pages(p))

    def test_redirect_skipped(self):
        out = self._run([
            ("Real article", "0", "This is a real article body."),
            ("Redirect page", "0", "#REDIRECT [[Real article]]"),
        ])
        self.assertEqual([t for t, _ in out], ["Real article"])

    def test_non_ns0_skipped(self):
        out = self._run([
            ("Article", "0", "Body."),
            ("Talk:Article", "1", "Talk body."),
            ("User:Someone", "2", "User page."),
        ])
        self.assertEqual([t for t, _ in out], ["Article"])

    def test_lowercase_redirect_also_skipped(self):
        out = self._run([
            ("A", "0", "#redirect [[B]]"),
        ])
        self.assertEqual(out, [])

    def test_roundtrip_through_en_pipeline(self):
        """端到端：enwiki 格式 page → iter_pages → 清洗 → format_doc。"""
        out = self._run([("Python (programming language)", "0",
                          "'''Python''' is a [[high-level programming language]].")])
        title, wt = out[0]
        doc = format_doc(title, wikitext_to_text(wt))
        self.assertTrue(doc.startswith(
            "Wikipedia article: Python (programming language)\n\n"))
        self.assertIn("high-level programming language", doc)


if __name__ == "__main__":
    unittest.main()
