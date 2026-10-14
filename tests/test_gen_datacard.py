"""gen_datacard 纯函数单测：许可逐字保留 / 占比计算 / 空 manifest / 分级覆盖。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gen_datacard import TIER_MAP, gen_card, lic_family, md_escape  # noqa: E402


def _row(id, tokens, license_, docs=1, url="https://example.org/x"):
    return {"id": id, "est_tokens": tokens, "license": license_,
            "docs": docs, "url": url}


class TestLicenseVerbatim(unittest.TestCase):
    def test_license_text_preserved_verbatim(self):
        lic = 'MSRC CVRF API: no termsOfService declared; "personal ' \
              'and non-commercial use" (project decision)'
        card = gen_card([_row("msrc-cvrf", 100, lic)], "ab" * 8, "t")
        # 逐字保留（含引号/连字符）；管道符转义后仍可还原
        self.assertIn(lic, card.replace("\\|", "|"))

    def test_pipe_in_license_escaped(self):
        card = gen_card([_row("x", 10, "MIT | GPL-2+ dual")], "ab" * 8, "t")
        self.assertIn("MIT \\| GPL-2+ dual", card)      # 表格安全
        self.assertNotIn("| MIT |", card.replace("| 源 |", ""))


class TestShareCalculation(unittest.TestCase):
    def test_shares_sum_to_100(self):
        rows = [_row("a", 300, "MIT"), _row("b", 100, "Apache-2.0")]
        card = gen_card(rows, "ab" * 8, "t")
        self.assertIn("75.00%", card)
        self.assertIn("25.00%", card)

    def test_zero_total_no_division_error(self):
        card = gen_card([_row("a", 0, "MIT", docs=0)], "ab" * 8, "t")
        self.assertIn("0 源" if False else "总 tokens：0", card)


class TestEmptyManifest(unittest.TestCase):
    def test_empty_rows_clean_card(self):
        card = gen_card([], "ab" * 8, "t")
        self.assertIn("源数：0", card)
        self.assertIn("## 逐源清单", card)   # 骨架仍完整
        self.assertNotIn("| T1", card.replace("| 分级 |", ""))  # 无源行


class TestLicFamily(unittest.TestCase):
    def test_families(self):
        self.assertEqual(lic_family("CC0 1.0 (arXiv API ToU)"), "CC0 1.0")
        self.assertEqual(lic_family("CC BY-SA 4.0"), "CC BY-SA（ShareAlike）")
        self.assertEqual(lic_family("CC BY-NC-SA 4.0 (project decision)"),
                         "CC BY-NC（非商用）")
        self.assertEqual(lic_family("GPL-3.0"), "GPL-3.0（copyleft）")
        self.assertEqual(lic_family("未公示（数据）; Apache-2.0 (repo code)"),
                         "未公示")
        self.assertEqual(lic_family("Public domain (US government work, "
                                    "17 U.S.C. §105)"),
                         "Public domain（美国政府作品）")


class TestTierCoverage(unittest.TestCase):
    def test_real_manifest_fully_classified(self):
        """全 manifest 行都有分级（防 TIER_MAP 与 manifest 漂移）。"""
        m = Path(__file__).resolve().parent.parent / "data" / "corpora" \
            / "manifest.jsonl"
        if not m.exists():
            self.skipTest("manifest 不在本测试环境")
        rows = [json.loads(l) for l in
                m.read_text(encoding="utf-8").splitlines() if l.strip()]
        missing = [r["id"] for r in rows if r["id"] not in TIER_MAP]
        self.assertEqual(missing, [],
                         f"manifest 新增源未评级: {missing} —— "
                         f"d3-ledger-memo §3 + TIER_MAP 需同步补录")


import json  # noqa: E402  (TestTierCoverage 用)

if __name__ == "__main__":
    unittest.main()
