"""fetch_credential_formats 纯函数测试（无网络）。"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_credential_formats as cf  # noqa: E402


class TestBuildDocs(unittest.TestCase):
    def setUp(self):
        self.docs = cf.build_docs()

    def test_doc_count(self):
        self.assertEqual(len(self.docs), 10)

    def test_all_docs_substantial(self):
        for d in self.docs:
            self.assertGreater(len(d), 1000, d[:60])

    def test_no_real_secret_material(self):
        """红线:不得含真实可复用的秘密材料——只有描述性格式知识。"""
        joined = "\n".join(self.docs)
        # 私钥 armor 只允许以描述引用形式出现(行内列举),不得有完整 base64 块
        self.assertNotIn("-----END RSA PRIVATE KEY-----\nMII", joined)
        # 高熵 base64 段(≥30 连续字符且含数字)视为可疑秘密
        for m in re.finditer(r"[A-Za-z0-9+/=]{30,}", joined):
            run = m.group(0)
            if any(c.isdigit() for c in run):
                self.fail(f"high-entropy run: {run[:40]}...")

    def test_covered_format_families(self):
        joined = "\n".join(self.docs)
        for kw in ["JWT", "AKIA", "arn:partition:service", "AccountKey=",
                   "AIza", "OPENSSH PRIVATE KEY", "ghp_", "xoxb-", "sk_live_",
                   "kind: Secret", "glpat-"]:
            self.assertIn(kw, joined)

    def test_defensive_orientation(self):
        joined = "\n".join(self.docs)
        self.assertIn("detection", joined.lower())
        self.assertIn("redact", joined.lower())

    def test_license_note_verbatim_rfc(self):
        self.assertIn("Copyright (c) 2015 IETF Trust", cf.SPEC["license"])
        self.assertIn("uplift red line", cf.SPEC["note"])


if __name__ == "__main__":
    unittest.main()
