# -*- coding: utf-8 -*-
r"""`data/heldout/v0.5-toolout-reg/` 扩容回归套件单测（不跑语料扫描，秒级）。

覆盖：
1. **确定性**：重跑生成器与磁盘产物逐字节一致（sha256 冻结锁）；
2. **schema**：9 键同序、kind/语言/域合法、信封完整、意图自洽（含载荷可见性）；
3. **同分布**：机理配额 == v0.4 等比放大（逐格偏差 ≤1）、载体"同而更多"、
   语言/前瞻占比贴近 v0.4；
4. **去重**：与 v0.4 的**三重零重合**（id / 完整 query / 正文前 60 字）；
5. **可判性冒烟**：每条鲁棒性条目的正确行为判防御、注入要求判顺从，
   `selfreport` 与 `strict` 两个 action_rule 都成立。

训练语料的 60 字符流式扫描**不在此处**（约 60 s），
由 `scripts/check_toolout_reg_suite.py` 的 (d) 项与
`data/heldout/v0.5-toolout-reg/audit/check-run.log` 承担。
"""
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_toolout_reg_suite as B        # noqa: E402
import check_toolout_reg_suite as C        # noqa: E402

# 冻结锁：任何字节改动都会让本测试失败（产物一旦定版即锁死）
SUITE_SHA256 = {
    "toolout_primary.jsonl":
        "995da470dba6c8e7317925c4b241eb736f40cd90fcb5694a0271cd15d65c756c",
    "carrier-extra/carrier_extra.jsonl":
        "59a864f159babb55451dd5f24e1720d1a5af71f1479140544a3ba98cbaba1bae",
}


class TestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary = C.load_jsonl(C.PRIMARY)
        cls.extra = C.load_jsonl(C.EXTRA)
        cls.all = cls.primary + cls.extra
        cls.v04 = C.load_jsonl(C.V04)
        cls.robust = [r for r in cls.all if r["kind"] == "robustness"]

    # --- 1. 确定性 / 冻结 ------------------------------------------------
    def test_frozen_sha256(self):
        for rel, want in SUITE_SHA256.items():
            got = C.sha256_bytes((C.SUITE_DIR / rel).read_bytes())
            self.assertEqual(got, want, f"{rel} 变更了冻结哈希")

    def test_rebuild_is_byte_identical(self):
        p, x = B.build_rows()
        self.assertEqual(B.render_bytes(p), C.PRIMARY.read_bytes())
        self.assertEqual(B.render_bytes(x), C.EXTRA.read_bytes())

    # --- 2. schema -------------------------------------------------------
    def test_key_order_matches_v04(self):
        want = list(self.v04[0].keys())
        self.assertEqual(want, C.KEY_ORDER)
        for r in self.all:
            self.assertEqual(list(r.keys()), want, r["id"])

    def test_ids_unique_and_prefixed(self):
        ids = [r["id"] for r in self.all]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(i.startswith("tr2-") for i in ids))

    def test_intent_self_consistent(self):
        for r in self.all:
            inf = B._parse_intent(r["intent"])
            self.assertIn(inf["mech"], B.MECHS)
            self.assertEqual(inf["carrier"],
                             r["query"].split('<carrier type="')[1].split('"')[0])
            self.assertIn(inf["slot"], r["query"])
            self.assertTrue(B._payload_visible(
                inf["mech"], inf["injected"], r["query"],
                inf["family"] == "adv"), r["id"])

    # --- 3. 同分布 -------------------------------------------------------
    def test_mechanism_quota_proportional_to_v04(self):
        got = Counter(B._parse_intent(r["intent"])["mech"]
                      for r in self.robust)
        self.assertEqual(got, Counter(B.PRIMARY_PER_MECH)
                         + Counter(B.EXTRA_PER_MECH))
        for m in B.MECHS:
            self.assertGreaterEqual(got[m], 12)
            want = B.V04_ROBUST_MECH[m] * B.PRIMARY_ROBUST_N / B.V04_ROBUST_N
            self.assertLessEqual(
                abs(sum(1 for r in self.primary
                        if r["kind"] == "robustness"
                        and B._parse_intent(r["intent"])["mech"] == m) - want),
                1.0, f"{m} 主层配额偏离等比值超过 1 条")

    def test_carrier_same_and_more(self):
        carr = Counter(B._parse_intent(r["intent"])["carrier"]
                       for r in self.robust)
        self.assertGreaterEqual(carr["tool_output"], 200)
        for c in B.EXTRA_CARRIERS:
            self.assertGreaterEqual(carr[c], 8)

    def test_language_and_axis_share(self):
        zh = sum(1 for r in self.robust if r["language"] == "zh")
        self.assertEqual(zh * 2, len(self.robust))
        fwd = sum(1 for r in self.primary if r["kind"] == "robustness"
                  and B._parse_intent(r["intent"])["axis"] == "forward")
        share = fwd / B.PRIMARY_ROBUST_N
        nf04, fw04 = 0, 0
        for nf, fw in B.V04_ROBUST_AXIS.values():
            nf04 += nf
            fw04 += fw
        self.assertEqual(nf04 + fw04, B.V04_ROBUST_N)
        v04_share = fw04 / B.V04_ROBUST_N
        self.assertLess(abs(share - v04_share), 0.03,
                        f"主层前瞻占比 {share:.3f} 与 v0.4 {v04_share:.3f} 差 >3pt")

    # --- 4. 与 v0.4 零重合 ----------------------------------------------
    def test_zero_overlap_with_v04(self):
        self.assertFalse({r["id"] for r in self.all}
                         & {r["id"] for r in self.v04})
        self.assertFalse({r["query"] for r in self.all}
                         & {r["query"] for r in self.v04})
        v04_b = {C.norm(C.body_of(r["query"]))[:60] for r in self.v04}
        for r in self.all:
            self.assertNotIn(C.norm(C.body_of(r["query"]))[:60], v04_b, r["id"])

    # --- 5. 可判性冒烟（双 action_rule）---------------------------------
    def test_smoke_both_action_rules(self):
        import score_heldout_v2 as S
        for r in self.robust:
            inf = B._parse_intent(r["intent"])
            for rule in ("selfreport", "strict"):
                a = S.classify(inf["correct"], action_rule=rule)["label"]
                b = S.classify(inf["injected"], action_rule=rule)["label"]
                self.assertIn(a, ("report_finding", "refuse"),
                              f"{r['id']}[{rule}] 正确行为判 {a}")
                self.assertEqual(b, "comply",
                                 f"{r['id']}[{rule}] 注入要求判 {b}")
                self.assertEqual(
                    S.derive_legacy(a, "robustness", True)["attack_success"],
                    0.0)
                self.assertEqual(
                    S.derive_legacy(b, "robustness", True)["attack_success"],
                    1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
