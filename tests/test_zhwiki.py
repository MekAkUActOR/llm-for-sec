"""fetch_zhwiki 纯函数单测：wikitext 清洗、安全域判据、确定性采样。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_zhwiki import is_security, sampled, wikitext_to_text


class TestWikitextToText(unittest.TestCase):
    def test_basic_markup(self):
        wt = "'''加粗'''和''斜体''以及普通文本"
        self.assertEqual(wikitext_to_text(wt), "加粗和斜体以及普通文本")

    def test_internal_link_anchor(self):
        wt = "参见[[密码学|加密学]]与[[防火墙]]"
        self.assertEqual(wikitext_to_text(wt), "参见加密学与防火墙")

    def test_external_link(self):
        wt = "详见[https://example.com 官方文档]或[https://a.b]"
        self.assertEqual(wikitext_to_text(wt), "详见官方文档或")

    def test_nested_templates_stripped(self):
        wt = "前文{{Infobox|a={{b}}|c=1}}后文"
        self.assertEqual(wikitext_to_text(wt), "前文后文")

    def test_refs_and_comments(self):
        wt = "结论<ref>引用内容</ref>与<ref name=x/>及<!--注释-->正文"
        self.assertEqual(wikitext_to_text(wt), "结论与及正文")

    def test_table_stripped(self):
        wt = "开头\n{| class=wikitable\n| 单元格\n|}\n结尾"
        out = wikitext_to_text(wt)
        self.assertNotIn("单元格", out)
        self.assertIn("开头", out)
        self.assertIn("结尾", out)

    def test_headings_become_lines(self):
        wt = "== 概述 ==\n内容一\n=== 细节 ===\n内容二"
        out = wikitext_to_text(wt)
        self.assertIn("概述", out)
        self.assertIn("细节", out)
        self.assertNotIn("==", out)

    def test_html_tags_and_list_marks(self):
        wt = "* 项目一\n* 项目二\n<b>强调</b>"
        out = wikitext_to_text(wt)
        self.assertIn("项目一", out)
        self.assertIn("强调", out)
        self.assertNotIn("<b>", out)

    def test_whitespace_normalized(self):
        wt = "多  个\t空格\n\n\n\n以及换行"
        out = wikitext_to_text(wt)
        self.assertNotIn("\t", out)
        self.assertNotIn("\n\n\n", out)


class TestIsSecurity(unittest.TestCase):
    def test_category_hit(self):
        wt = "正文。[[Category:计算机安全]]"
        self.assertTrue(is_security("某条目", wt))

    def test_category_alias_zh(self):
        wt = "[[分类:密码学]]"
        self.assertTrue(is_security("某条目", wt))

    def test_title_keyword_hit(self):
        self.assertTrue(is_security("勒索软件", "无分类正文"))

    def test_plain_article_not_security(self):
        self.assertFalse(is_security("贵州省", "[[分类:中国省份]]"))

    def test_safety_not_security(self):
        # 交通/食品安全属 safety 域：标题无关键词、分类不命中 → 不收
        self.assertFalse(is_security("交通安全", "[[分类:交通]]"))

    def test_unrelated_category_with_sec_word(self):
        # 分类名仅含"安全"二字但不在白名单 → 不收
        self.assertFalse(is_security("某地", "[[分类:公共安全]]"))


class TestSampled(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(sampled("条目A", 0.15), sampled("条目A", 0.15))

    def test_full_rate_always(self):
        self.assertTrue(sampled("任何条目", 1.0))

    def test_zero_rate_never(self):
        self.assertFalse(sampled("任何条目", 0.0))

    def test_rate_monotone(self):
        # 提高采样率不会漏掉先前命中的条目（哈希阈值性质）
        for t in ["a", "b", "c", "d", "e"]:
            self.assertFalse(sampled(t, 0.5) and not sampled(t, 0.9))


if __name__ == "__main__":
    unittest.main()
