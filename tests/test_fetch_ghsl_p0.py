"""fetch_ghsl_p0 转换器测试（纯函数，无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_ghsl_p0 as fg  # noqa: E402


GHSL_FIXTURE = """<html><head>
<meta property="og:title" content="GHSL-2020-001: Off-by-one heap overflow in Bftpd">
<title>Bftpd | GitHub Security Lab</title></head><body>
<nav>skip to content Security Lab Research Blog Advisories</nav>
<header>
<a class="font-mono post-date" href="/advisories/GHSL-2020-001-Bftpd/">
  <span class="font-mono">March 12, 2020</span></a>
<h1>GHSL-2020-001: Off-by-one heap overflow in Bftpd</h1>
<p>Antonio Morales</p>
</header>
<main>
<h2>Summary</h2>
<p>Under certain circumstances, an <code>off-by-one</code> heap overflow can occur.</p>
<h2>Product</h2>
<p>Bftpd</p>
<h2>Impact</h2>
<p>Heap memory corruption with a single nul byte.</p>
<h2>Coordinated Disclosure Timeline</h2>
<p>01/09/2020: Report sent to Vendor</p>
</main>
<footer>Product
Features
Security
Team
Enterprise
GitHub Inc. © 2024</footer>
</body></html>
"""

RCA_FIXTURE = """---
title: "CVE-2021-1647: Heap overflow in RCA parser"
layout: page
---
<!-- a comment -->
# CVE-2021-1647: RCE in Foo

## The Basics

**Disclosure or Patch Date:** January 2021

**Product:** Foo

## Summary
A heap overflow in the parser allows remote code execution when
opening a malicious document. The root cause is an integer overflow
in the length calculation preceding an allocation.
"""


class TestConvertGhsl(unittest.TestCase):
    def test_full_advisory(self):
        t = fg.convert_ghsl(GHSL_FIXTURE)
        self.assertIsNotNone(t)
        self.assertTrue(t.startswith(
            "GitHub Security Lab advisory GHSL-2020-001: Off-by-one heap overflow in Bftpd (March 12, 2020)"))
        self.assertIn("Heap memory corruption", t)
        self.assertIn("01/09/2020: Report sent to Vendor", t)

    def test_nav_and_footer_excluded(self):
        t = fg.convert_ghsl(GHSL_FIXTURE)
        self.assertNotIn("skip to content", t)
        self.assertNotIn("Team", t)          # 页脚产品导航
        self.assertNotIn("GitHub Inc.", t)

    def test_non_advisory_page_rejected(self):
        html = GHSL_FIXTURE.replace("GHSL-2020-001:", "About page:")
        self.assertIsNone(fg.convert_ghsl(html))

    def test_parse_index_dedup(self):
        html = ('<a href="/advisories/GHSL-2020-001-Bftpd/">a</a>'
                '<a href="/advisories/GHSL-2020-001-Bftpd/">b</a>'
                '<a href="/advisories/GHSL-2026-105_Signal-iOS/">c</a>'
                '<a href="/research/">d</a>')
        self.assertEqual(fg.parse_index(html),
                         ["GHSL-2020-001-Bftpd", "GHSL-2026-105_Signal-iOS"])


class TestConvertRca(unittest.TestCase):
    def test_frontmatter_and_comment_stripped(self):
        t = fg.convert_rca(RCA_FIXTURE)
        self.assertIsNotNone(t)
        self.assertNotIn("layout: page", t)
        self.assertNotIn("a comment", t)
        self.assertIn("CVE-2021-1647", t)
        self.assertIn("integer overflow", t)
        self.assertTrue(t.startswith("Google Project Zero 0-day root cause analysis"))

    def test_template_rejected(self):
        self.assertIsNone(fg.convert_rca("# 0-day Root Cause Analysis Template\n\n## The Basics\n"
                                          + "x" * 300))

    def test_too_short_rejected(self):
        self.assertIsNone(fg.convert_rca("---\nlayout: page\n---\n\nshort text"))


if __name__ == "__main__":
    unittest.main()
