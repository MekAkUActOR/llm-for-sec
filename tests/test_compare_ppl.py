"""compare_ppl 门禁逻辑单测。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from compare_ppl import compare


def _report(ppl_by_domain):
    return {"model": "m", "domains": {k: {"ppl": v, "tokens": 1, "docs": 1}
                                      for k, v in ppl_by_domain.items()}}


class TestComparePpl(unittest.TestCase):
    def test_sec_drop_pass(self):
        r = compare(_report({"sec": 20.0}), _report({"sec": 14.0}), 0.25, 0.10)
        self.assertTrue(r["sec"]["ok"])  # -30% ≤ -25%

    def test_sec_drop_fail(self):
        r = compare(_report({"sec": 20.0}), _report({"sec": 16.0}), 0.25, 0.10)
        self.assertFalse(r["sec"]["ok"])  # -20% > -25%

    def test_general_rise_pass(self):
        r = compare(_report({"general_zh": 30.0}), _report({"general_zh": 32.0}),
                    0.25, 0.10)
        self.assertTrue(r["general_zh"]["ok"])  # +6.7% ≤ 10%

    def test_general_rise_fail(self):
        r = compare(_report({"general_en": 30.0}), _report({"general_en": 34.0}),
                    0.25, 0.10)
        self.assertFalse(r["general_en"]["ok"])  # +13.3% > 10%

    def test_secondary_domain_no_gate(self):
        r = compare(_report({"privacy": 30.0}), _report({"privacy": 99.0}),
                    0.25, 0.10)
        self.assertIsNone(r["privacy"]["ok"])

    def test_missing_domain(self):
        r = compare(_report({"sec": 20.0}), _report({}), 0.25, 0.10)
        self.assertEqual(r["sec"]["ok"], None)
        self.assertEqual(r["sec"]["reason"], "missing")


if __name__ == "__main__":
    unittest.main()
