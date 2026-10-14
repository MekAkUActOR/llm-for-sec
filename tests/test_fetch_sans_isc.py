"""fetch_sans_isc 转换器测试（纯函数，无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_sans_isc as fs  # noqa: E402


ARCHIVE = """
<div class="isc-card"><div class="card-body">
<a class="card-link">Published: 2020-06-30</a>
<h2 class="card-title"><a href="../diary/ISC+Snapshot+SpectX+IP+Hitcount+Query/26296/">ISC Snapshot: SpectX IP Hitcount Query</a></h2>
<div class="card-content"><p>excerpt one</p></div></div></div>
<div class="isc-card"><div class="card-body">
<a class="card-link">Published: 2020-06-28</a>
<h2 class="card-title"><a href="../diary/Another+Diary/26290/">Another Diary</a></h2>
<div class="card-content"><p>excerpt two</p></div></div></div>
<div class="isc-card"><div class="card-body">
<a class="card-link">Published: 2026-09-24</a>
<h2 class="card-title"><a href="../diary/Recent+Fallback/33366/">Recent Fallback Entry</a></h2>
<div class="card-content"><p>should be filtered</p></div></div></div>
"""

DIARY = """<html><head><title>Pandas Errors: What encoding are my logs in? - SANS ISC</title></head>
<body>
<nav>Home Diary Forums Handler List</nav>
<article>
<h1>Pandas Errors: What encoding are my logs in?</h1>
<div class="diaryheader"> <b>Published</b>: 2024-08-23. <b>Last Updated</b>: 2024-08-23 12:26:15 UTC<br /> <b>by</b> <a href="/handler_list.html#jesse-la-grew">Jesse La Grew</a> (Version: 1)<br /> </div>
<a class="ico-comments" href="#comments">0 comment(s)</a>
<div class="diarybody"> <p>While trying to process some of my honeypot data, I ran
into the following error in my Python script:</p>
<p><strong>"Exception has occurred: ValueError</strong> values should be unique
if codes is not None"</p>
<pre>cowrie_data = cowrie_data.merge(df, on=["dates"])</pre>
<p>Summary: always check your encodings.</p>
</div>
<div class="diarykeywords">Keywords: <a href="/tag.html?tag=dataframe">dataframe</a> <a href="/tag.html?tag=python">python</a> </div>
<div class="teachingschedule">Click HERE to learn more about classes</div>
<ul class="diaryPagination"><li><a href="/diary/1">Older</a></li></ul>
</article></body></html>
"""


class TestParseArchiveCards(unittest.TestCase):
    def test_month_filter(self):
        cards = fs.parse_archive_cards(ARCHIVE, 2020, 6)
        ids = [c["id"] for c in cards]
        self.assertIn("26296", ids)
        self.assertIn("26290", ids)
        self.assertNotIn("33366", ids)  # 回退近期条目按日期滤除

    def test_card_fields(self):
        c = fs.parse_archive_cards(ARCHIVE, 2020, 6)[0]
        self.assertEqual(c["date"], "2020-06-30")
        self.assertEqual(c["title"], "ISC Snapshot: SpectX IP Hitcount Query")


class TestConvertSansDiary(unittest.TestCase):
    def test_full_diary(self):
        t = fs.convert_sans_diary(DIARY)
        self.assertIsNotNone(t)
        self.assertTrue(t.startswith(
            "SANS Internet Storm Center diary: Pandas Errors: What encoding are my logs in?"))
        self.assertIn("Published 2024-08-23, by Jesse La Grew", t)
        self.assertIn("honeypot data", t)
        self.assertIn("values should be unique", t)
        self.assertIn("Keywords: dataframe python", t)

    def test_noise_excluded(self):
        t = fs.convert_sans_diary(DIARY)
        self.assertNotIn("Handler List", t)      # 导航
        self.assertNotIn("teachingschedule", t)  # 课程广告
        self.assertNotIn("Older", t)             # 分页
        self.assertNotIn("comment(s)", t)        # 评论

    def test_missing_body_rejected(self):
        self.assertIsNone(fs.convert_sans_diary("<html><title>x</title></html>"))
        self.assertIsNone(fs.convert_sans_diary("<div>no title</div>"))

    def test_short_diary_rejected(self):
        tiny = ("<html><head><title>Tiny</title></head><body>"
                '<div class="diarybody">short</div></body></html>')
        self.assertIsNone(fs.convert_sans_diary(tiny))

    def test_oneliner_old_template(self):
        # 2010-2015 年短日记:无 diarybody,正文在 oneliner div,日期靠 hint
        one = ("<html><head><title>PostgreSQL 8.4.2 and 8.3.9 have security "
               "fixes</title></head><body>"
               '<ul class="diaryPagination"><li><a href="/diary/1">previous</a></li></ul>'
               '<div class="oneliner">PostgreSQL 8.4.2, 8.3.9, 8.2.15 have security '
               'fixes: <a href="http://www.postgresql.org/docs/current/">release '
               'notes</a></div></article>'
               '<div class="teachingschedule">Click HERE</div></body></html>')
        t = fs.convert_sans_diary(one, date_hint="2010-01-04")
        self.assertIsNotNone(t)
        self.assertTrue(t.startswith("SANS Internet Storm Center diary: "
                                     "PostgreSQL 8.4.2 and 8.3.9 have security fixes"))
        self.assertIn("Published 2010-01-04", t)
        self.assertIn("8.2.15", t)
        self.assertNotIn("Click HERE", t)
        self.assertNotIn("previous", t)
        # 无 oneliner 也无 diarybody -> None
        self.assertIsNone(fs.convert_sans_diary(
            "<html><title>Empty</title><body>nothing</body></html>"))


if __name__ == "__main__":
    unittest.main()
