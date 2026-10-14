"""fetch_debian_dsa 转换器测试（纯函数，无网络）。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_debian_dsa as fd  # noqa: E402


FIXTURE = """<!-- MHonArc v2.6.19 -->
<!--X-Subject: [SECURITY] [DSA 5817&#45;1] chromium security update -->
<!--X-Date: Sat, 23 Nov 2024 10:51:11 +0000 (UTC) -->
<html><head><title>x</title></head><body>
<form method="POST" action="/cgi-bin/spam-report.pl">
<input type="submit" value="Report as spam" />
[<a href="msg00231.html">Date Prev</a>]
</form>
<h1>[SECURITY] [DSA 5817-1] chromium security update</h1>
<ul><li><em>From</em>: <a href="mailto:d%40debian.org">d@debian.org</a></li></ul>
<!--X-Body-of-Message-->
<pre>-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA256

- -------------------------------------------------------------------------
Debian Security Advisory DSA-5817-1                   security@debian.org
November 23, 2024
- -------------------------------------------------------------------------

Package        : chromium
CVE ID         : CVE-2024-11110 CVE-2024-11111

Security issues were discovered in Chromium which could result
in the execution of arbitrary code.

For the stable distribution (bookworm), these problems have been fixed in
version 131.0.6778.85-1~deb12u1.

We recommend that you upgrade your chromium packages.

<a rel="nofollow" href="https://security-tracker.debian.org/tracker/chromium">https://security-tracker.debian.org/tracker/chromium</a>
-----BEGIN PGP SIGNATURE-----

iQIzBAEBCAAdFiEEUAUk+X1YiTIjs19qZF0CR8NudjcFAmdBrIQACgkQZF0CR8Nu
=J21V
-----END PGP SIGNATURE-----
</pre>
<!--X-Body-of-Message-End-->
<hr />
<ul><li>Prev by Date:
<strong><a href="msg00231.html">[SECURITY] [DSA 5812-2] po</a></li></ul>
</body></html>
"""


class TestConvertDsa(unittest.TestCase):
    def test_full_advisory(self):
        t = fd.convert_dsa(FIXTURE)
        self.assertIsNotNone(t)
        self.assertIn("Debian Security Advisory [SECURITY] [DSA 5817-1] chromium security update",
                      t)
        self.assertIn("Sat, 23 Nov 2024", t)  # 日期取自 X-Date
        self.assertIn("Package : chromium", t)  # 正文保留字段行
        self.assertIn("CVE-2024-11110", t)
        self.assertIn("version 131.0.6778.85-1~deb12u1", t)  # 修复版本
        self.assertIn("security-tracker.debian.org/tracker/chromium", t)  # 链接保留

    def test_pgp_signature_stripped(self):
        t = fd.convert_dsa(FIXTURE)
        self.assertNotIn("BEGIN PGP SIGNATURE", t)
        self.assertNotIn("iQIzBAEBCAAdFiEE", t)
        self.assertNotIn("BEGIN PGP SIGNED MESSAGE", t)

    def test_date_entities_unescaped(self):
        # 老 MHonArc 页把时区减号编成 &#45;（如 2000 年 DSA-001-1）
        html = FIXTURE.replace(
            "<!--X-Date: Sat, 23 Nov 2024 10:51:11 +0000 (UTC) -->",
            "<!--X-Date: Tue, 28 Nov 2000 19:17:22 &#45;0600 -->")
        t = fd.convert_dsa(html)
        self.assertIsNotNone(t)
        self.assertIn("19:17:22 -0600", t)
        self.assertNotIn("&#45;", t)

    def test_navigation_excluded(self):
        t = fd.convert_dsa(FIXTURE)
        self.assertNotIn("Report as spam", t)
        self.assertNotIn("Date Prev", t)
        self.assertNotIn("Prev by Date", t)

    def test_non_dsa_message_rejected(self):
        html = FIXTURE.replace("[DSA 5817-1]", "[ANNOUNCE] Debian conference")
        self.assertIsNone(fd.convert_dsa(html))

    def test_marker_fallback(self):
        # 无 X-Body-of-Message 标记的老页面：全文降级路径，仍剔除导航与签名
        no_mark = FIXTURE.replace("<!--X-Body-of-Message-->", "").replace(
            "<!--X-Body-of-Message-End-->", "")
        t = fd.convert_dsa(no_mark)
        self.assertIsNotNone(t)
        self.assertIn("CVE-2024-11110", t)
        self.assertNotIn("BEGIN PGP SIGNATURE", t)


if __name__ == "__main__":
    unittest.main()
