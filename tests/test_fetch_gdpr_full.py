"""fetch_gdpr_full 纯函数测试（无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_gdpr_full as g  # noqa: E402

ART = ('<p id="d1e{i}-1-1" class="oj-ti-art">Article {i}</p> '
       '<div class="eli-title" id="art_{i}.tit_1"> '
       '<p class="oj-sti-art">Title {i}</p> '
       '<div class="oj-normal"><p>Body of article {i} with sufficient text '
       'to survive the length threshold for clean output ingestion checks '
       'and general packing behaviour in the corpus pipeline. This paragraph '
       'is deliberately long because GDPR article bodies in the real EUR-Lex '
       'rendering typically span hundreds to thousands of characters and the '
       'footer-cut markers only apply beyond a minimum offset guard.</p></div></div>')


def make_html(n_arts: int) -> str:
    parts = ["<html><body>",
             "<p>Regulation (EU) 2016/679 of the European Parliament and of "
             "the Council</p>"]
    # 序言区足够长(真实页 ~40k 字符,阈值 200)
    for i in range(1, 8):
        parts.append(f"<p>({i}) Data protection is a fundamental right and "
                     "protected interest, and this recital explains part of "
                     "the reasoning that led the Union legislature to adopt "
                     "a comprehensive framework for the processing of "
                     "personal data in the digital age.</p>")
    for i in range(1, n_arts + 1):
        parts.append(ART.format(i=i))
    parts.append("<p>OJ L, 04/05/2016 p. 1</p></body></html>")
    return "".join(parts)


class TestConvertGdpr(unittest.TestCase):
    def test_full_page(self):
        docs = g.convert_gdpr(make_html(3))
        # 1 recitals doc + 3 article docs
        self.assertEqual(len(docs), 4)
        self.assertIn("Preamble and Recitals", docs[0])
        self.assertIn("Regulation (EU) 2016/679", docs[0])
        self.assertTrue(docs[1].startswith(
            "EU General Data Protection Regulation (GDPR) Article 1"))
        self.assertIn("— Title 1", docs[1])
        self.assertIn("Body of article 1", docs[1])

    def test_article_numbering_all(self):
        docs = g.convert_gdpr(make_html(5))
        arts = [d for d in docs if "Article " in d.split("\n")[0]]
        self.assertEqual([a.split("Article ")[1].split(" ")[0] for a in arts],
                         ["1", "2", "3", "4", "5"])

    def test_shell_page_returns_empty(self):
        self.assertEqual(g.convert_gdpr("<html><body>Access Denied</body></html>"), [])

    def test_no_title_still_documents(self):
        html = ('<p class="oj-ti-art">Article 1</p>'
                '<div class="oj-normal"><p>Body text without an ste-title '
                'element but still long enough to pass the writing checks '
                'of the corpus pipeline validation.</p></div>')
        docs = g.convert_gdpr(html)
        self.assertEqual(len(docs), 1)
        self.assertIn("Article 1", docs[0])
        self.assertNotIn("— ", docs[0])

    def test_footer_cut(self):
        html = make_html(2).replace(
            "</body>",
            "<p>Done at Strasbourg long trailing material that should be cut "
            "when the marker appears with enough preceding body text.</p>"
            "</body>")
        docs = g.convert_gdpr(html)
        arts = [d for d in docs
                if d.startswith("EU General Data Protection Regulation (GDPR) Article")]
        self.assertEqual(len(arts), 2)
        self.assertNotIn("Done at Strasbourg long trailing", arts[-1])


if __name__ == "__main__":
    unittest.main()
