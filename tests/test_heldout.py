"""私有留出集（v0.1 种子批）加载、校验、政策对照组不变量测试。"""

import unittest
from pathlib import Path

from secfm.eval.heldout import load_dir, stats, validate
from secfm.eval.schema import EvalItem

HELDOUT = Path(__file__).resolve().parents[1] / "data" / "heldout" / "v0.1"


class TestHeldoutLoad(unittest.TestCase):
    def setUp(self):
        self.suite, self.problems = load_dir(HELDOUT)

    def test_loads_clean(self):
        self.assertEqual(self.problems, [])
        self.assertEqual(len(self.suite.items), 60)

    def test_validate(self):
        self.assertEqual(validate(self.suite.items), [])

    def test_per_domain_and_language(self):
        st = stats(self.suite.items)
        for d in ("ai_safety", "security", "privacy"):
            self.assertGreaterEqual(st["by_domain"][d], 20)
            zh = sum(1 for i in self.suite.items
                     if i.domain == d and i.language == "zh")
            en = sum(1 for i in self.suite.items
                     if i.domain == d and i.language == "en")
            self.assertGreater(zh, 0, f"{d} 缺中文条目")
            self.assertGreater(en, 0, f"{d} 缺英文条目")

    def test_kinds_covered(self):
        st = stats(self.suite.items)
        for k in ("robustness", "alignment", "capability", "calibration"):
            self.assertGreater(st["by_kind"][k], 0, f"kind {k} 无条目")

    def test_policy_groups_wellformed(self):
        """政策对照组不变量：同组同 query、异 pack、期望相反。"""
        groups = {}
        for it in self.suite.items:
            if it.group:
                groups.setdefault(it.group, []).append(it)
        self.assertEqual(len(groups), 6)  # 每域 2 组
        for g, items in sorted(groups.items()):
            self.assertEqual(len(items), 2, f"{g}: 条数 {len(items)}")
            self.assertEqual(len({i.query for i in items}), 1,
                             f"{g}: 组内 query 不一致")
            self.assertEqual(len({i.policy_pack for i in items}), 2,
                             f"{g}: 组内 policy_pack 未区分")
            self.assertEqual(
                len({i.expected["must_refuse"] for i in items}), 2,
                f"{g}: 组内期望未随政策变化")


class TestValidateNegatives(unittest.TestCase):
    def test_missing_expected_key(self):
        bad = EvalItem(id="x", domain="security", kind="robustness",
                       language="zh", policy_pack="default", query="q",
                       expected={})  # 缺 must_refuse
        self.assertTrue(any("must_refuse" in p for p in validate([bad])))

    def test_duplicate_ids(self):
        a = EvalItem(id="x", domain="security", kind="alignment",
                     language="zh", policy_pack="default", query="q",
                     expected={"must_refuse": False})
        b = EvalItem(id="x", domain="security", kind="alignment",
                     language="en", policy_pack="default", query="q2",
                     expected={"must_refuse": False})
        self.assertTrue(any("duplicate" in p for p in validate([a, b])))

    def test_bad_language(self):
        bad = EvalItem(id="x", domain="security", kind="alignment",
                       language="fr", policy_pack="default", query="q",
                       expected={"must_refuse": False})
        self.assertTrue(any("language" in p for p in validate([bad])))


if __name__ == "__main__":
    unittest.main()
