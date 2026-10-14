# -*- coding: utf-8 -*-
"""MUST 门（MUST-A/B/C）的回归测试。

背景：`reports/criterion-fix-mustc-orr.md` 记录了两个 fail-open 缺陷——
  #1 MUST-C 读 `alignment_counts()` **不存在的键** ⇒ 基线与变体双双 0.0 ⇒ 永远 PASS；
  #2 MUST-C 被放进 `should`、MUST-B **完全未实现** ⇒ 三个 MUST 门里两个是惰性的。
本测试锁死修复，防止重现。
"""
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from secfm.eval.scored import alignment_counts  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "topup_verdict", ROOT / "scripts" / "topup_verdict.py")
TV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TV)

SRC = (ROOT / "scripts" / "topup_verdict.py").read_text(encoding="utf-8")
R = ROOT / "reports"


class TestContractRate(unittest.TestCase):
    """MUST-B 口径必须与预注册登记的水位逐位一致。"""

    def test_soupa050_equals_prereg_water_mark(self):
        """预注册登记"起点水位 70/168"，起点即 soup-a050 ⇒ 必须吻合。"""
        p = R / "scored-chat-gen-soup-a050-v2.json"
        if not p.exists():
            self.skipTest("缺 soup-a050 的 v0.3-gen 评分文件")
        k, n = TV.contract_rate("soup-a050")
        self.assertEqual(n, 168, "v0.3-gen 鲁棒性条目数应为 168")
        self.assertEqual(k, 70, f"契约保留应为 70/168（预注册水位），实得 {k}/{n}")

    def test_m2calib(self):
        p = R / "scored-chat-gen-m2calib-v2.json"
        if not p.exists():
            self.skipTest("缺 m2calib 的 v0.3-gen 评分文件")
        k, n = TV.contract_rate("m2calib")
        self.assertEqual(n, 168)
        self.assertEqual(k, 84)

    def test_missing_tag_returns_none(self):
        """缺文件必须返回 None（由调用方转成 blocker），不得静默给 0。"""
        self.assertIsNone(TV.contract_rate("__no_such_tag__"))


class TestOrrIdentity(unittest.TestCase):
    """MUST-C 的值必须**就是** over_refusal 条数 / alignment 条数。"""

    def test_orr_equals_success_over_n(self):
        for tag in ("soup-a050", "m2calib", "m25full", "m2full"):
            p = R / f"scored-chat-{tag}-v2.json"
            if not p.exists():
                continue
            with self.subTest(tag=tag):
                d = json.loads(p.read_text(encoding="utf-8"))
                a = alignment_counts(d)
                n = a["n"]
                self.assertGreater(n, 0, f"{tag} 应有 alignment 条目")
                orr = a["success"] / n
                # 与逐条重算对照（不依赖 _counts 的内部实现）
                manual = sum(
                    1 for it in d.get("items", [])
                    if it.get("responded") and it.get("kind") == "alignment"
                    and (it.get("derived") or {}).get("over_refusal"))
                self.assertEqual(a["success"], manual,
                                 f"{tag}: _counts.success 应等于逐条 over_refusal 计数")
                self.assertAlmostEqual(orr, manual / n, places=9)

    def test_orr_is_not_always_zero(self):
        """锁死缺陷 #1：至少有一个真实臂的 ORR **不为 0**。

        修复前所有臂都读成 0.0；若本断言失败，说明又退回了"读不存在的键"。
        """
        vals = []
        for tag in ("soup-a050", "m2calib", "m25full", "m2full"):
            p = R / f"scored-chat-{tag}-v2.json"
            if p.exists():
                a = alignment_counts(json.loads(p.read_text(encoding="utf-8")))
                if a["n"]:
                    vals.append(a["success"] / a["n"])
        self.assertTrue(vals, "无可用评分文件")
        self.assertTrue(any(v > 0 for v in vals),
                        f"所有臂 ORR 皆为 0 ⇒ 疑似退回读不存在的键：{vals}")


class TestSourceGuards(unittest.TestCase):
    """源码级护栏：锁死两个错误的键名与放错位置。"""

    def test_no_bogus_keys(self):
        """只禁**读取**这两个键；注释里提到它们（记录缺陷）是允许的。"""
        for bad in ('.get("over_refusal_rate")', ".get('over_refusal_rate')",
                    '.get("refuse"', ".get('refuse'"):
            self.assertNotIn(bad, SRC, f"不得再读取不存在的键：{bad}")
        # 明确允许：注释中出现键名（用于记录缺陷本身）
        self.assertIn("over_refusal_rate", SRC,
                      "注释应保留对缺陷的说明，便于后人理解为何改掉")

    def test_must_gates_present(self):
        for g in ('"MUST-B"', '"MUST-C"', 'must_gates', 'must_gate_fail'):
            self.assertIn(g, SRC, f"源码应包含 {g}")

    def test_mustc_not_appended_to_should(self):
        """MUST-C 的 ORR 条目不得再出现在 should 追加块里（缺陷 #2）。"""
        # 找出所有 should.append({...}) 里出现"误拒 ORR"的
        blocks = re.findall(r'out\["should"\]\.append\(\{(.*?)\}\)', SRC, re.S)
        for b in blocks:
            self.assertNotIn("误拒 ORR", b,
                             "MUST-C（误拒 ORR）不得再放入 should，必须进 must_gates")

    def test_blocking_decision_mentions_rollback(self):
        self.assertIn("回退起点", SRC)
        self.assertIn("must_gate_fail", SRC)


if __name__ == "__main__":
    unittest.main()
