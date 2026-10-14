"""fetch_oracle_cpu 转换器测试（纯函数，无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_oracle_cpu as fo  # noqa: E402


FIXTURE = """<html><head><title>Oracle Critical Patch Update Advisory - October 2026</title>
<style>a{color:red}</style></head><body>
<div id="nav">QUICK LINKS Cloud Database Java AI Sign Out</div>
<h1>Oracle Critical Patch Update Advisory - October 2026</h1>
<p>Description</p>
<p>This Critical Patch Update contains 389 new security patches for Oracle products,
addressing vulnerabilities in Oracle Database, MySQL, Fusion Middleware, Java SE and
other product families. Due to the threat posed by successful attacks, Oracle strongly
recommends that customers apply CPU security patches as soon as possible.</p>
<p>The next Critical Patch Update dates are 19 January 2027, 20 April 2027,
20 July 2027, and 19 October 2027.</p>
<table>
<tr><th>Component</th><th>Protocol</th><th>CVSS</th></tr>
<tr><td>MySQL Server</td><td>HTTP</td><td>9.8</td></tr>
</table>
<p>Patch Availability: Oracle has released security patches for all supported
products in the October 2026 Critical Patch Update. See My Oracle Support note
for patch details.</p>
<footer>Copyright © 2026 Oracle
Legal Notices and Terms of Use
Site Map</footer>
</body></html>
"""


class TestConvertOracle(unittest.TestCase):
    def test_full_advisory(self):
        t = fo.convert_oracle(FIXTURE)
        self.assertIsNotNone(t)
        self.assertTrue(t.startswith(
            "Oracle security advisory: Oracle Critical Patch Update Advisory - October 2026"))
        self.assertIn("389 new security patches", t)
        self.assertIn("MySQL Server", t)      # 风险矩阵行保留
        self.assertIn("Patch Availability", t)

    def test_nav_and_footer_excluded(self):
        t = fo.convert_oracle(FIXTURE)
        self.assertNotIn("QUICK LINKS", t)
        self.assertNotIn("Legal Notices and Terms of Use", t)

    def test_thin_page_rejected(self):
        thin = ("<html><head><title>Thin Shell</title></head><body>"
                "<h1>Thin Shell</h1><p>Only a shell page.</p></body></html>")
        self.assertIsNone(fo.convert_oracle(thin))

    def test_extract_links_filters_nav_pages(self):
        html = ('<a href="/security-alerts/cpuoct2025.html">a</a>'
                '<a href="/security-alerts/cpuoct2025.html">dup</a>'
                '<a href="/security-alerts/securityemail.html">mail</a>'
                '<a href="/security-alerts/alert-cve-2021-44228.html">log4j</a>'
                '<a href="/other/place.html">elsewhere</a>')
        self.assertEqual(fo.extract_links(html),
                         ["alert-cve-2021-44228.html", "cpuoct2025.html"])


if __name__ == "__main__":
    unittest.main()
