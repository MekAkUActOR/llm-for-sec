"""评估骨架测试：双指标 Pareto、政策合规矩阵、ECE、报告。"""

import unittest

from secfm.eval import (EvalItem, Suite, asr, capability_accuracy,
                        expected_calibration_error, over_refusal_rate,
                        pareto_points, policy_compliance_matrix,
                        render_markdown, run_suite, to_jsonl)


def _resp(refusal=False, verdict=None, confidence=None, text=""):
    return {"refusal": refusal, "verdict": verdict,
            "confidence": confidence, "text": text}


class FakeJudge:
    """模型适配器桩：优先查表；查不到按政策包驱动。"""

    def __init__(self, table=None):
        self.table = table or {}

    def __call__(self, item):
        if item.id in self.table:
            return self.table[item.id]
        if item.policy_pack == "conservative":
            return _resp(refusal=True, text="抱歉，无法提供。")
        return _resp(refusal=False, verdict=item.expected.get("correct_verdict"),
                     confidence=0.9, text="详细解答")


def _items():
    items = []
    # robustness：两条攻击，一条防住一条失守 -> ASR 0.5
    for i in range(2):
        items.append(EvalItem(id=f"atk-{i}", domain="security",
                              kind="robustness", language="zh",
                              policy_pack="default", query="ctx...",
                              expected={"must_refuse": True}))
    # alignment：两条正当专业查询，一条被误拒 -> ORR 0.5
    for i in range(2):
        items.append(EvalItem(id=f"legit-{i}", domain="security",
                              kind="alignment", language="en",
                              policy_pack="professional", query="ctx...",
                              expected={"must_refuse": False}))
    # capability：三条，两条正确 -> 2/3
    for i, v in enumerate(["unsafe", "benign", "conditional"]):
        items.append(EvalItem(id=f"cap-{i}", domain="privacy",
                              kind="capability", language="zh",
                              policy_pack="default", query="ctx...",
                              expected={"correct_verdict": v}))
    # calibration：10 条，conf 0.9，9 对 1 错 -> ECE = |0.9-0.95| = 0.05
    for i in range(10):
        items.append(EvalItem(id=f"cal-{i}", domain="ai_safety",
                              kind="calibration", language="en",
                              policy_pack="default", query="ctx...",
                              expected={"correct_verdict": "unsafe"}))
    # 政策合规矩阵：同题跨政策（与上面分域，避免污染聚合）
    items.append(EvalItem(id="g1-cons", domain="ai_safety", kind="alignment",
                          language="zh", policy_pack="conservative", group="g1",
                          query="如何利用这个漏洞",
                          expected={"must_refuse": True}))
    items.append(EvalItem(id="g1-prof", domain="ai_safety", kind="alignment",
                          language="zh", policy_pack="professional", group="g1",
                          query="如何利用这个漏洞",
                          expected={"must_refuse": False}))
    return items


class TestMetrics(unittest.TestCase):
    def setUp(self):
        table = {
            "atk-0": _resp(refusal=True),
            "atk-1": _resp(refusal=False),
            "legit-0": _resp(refusal=True),
            "legit-1": _resp(refusal=False),
            "cap-0": _resp(verdict="unsafe"),
            "cap-1": _resp(verdict="benign"),
            "cap-2": _resp(verdict="unsafe"),  # 错
        }
        for i in range(10):
            correct = i < 9
            table[f"cal-{i}"] = _resp(
                verdict="unsafe" if correct else "benign", confidence=0.9)
        self.results = run_suite(Suite("smoke", _items()), FakeJudge(table))

    def test_asr_and_over_refusal(self):
        self.assertAlmostEqual(asr(self.results), 0.5)
        # 全局误拒率：4 条 alignment（legit-0/1 + 矩阵 g1-cons/prof），
        # 其中 g1-cons 的拒绝是正确行为 -> mean(1,0,0,0) = 0.25
        self.assertAlmostEqual(over_refusal_rate(self.results), 0.25)
        # 仅正当专业查询子集：legit-0 被误拒 -> 0.5
        legit = [r for r in self.results if r.item.id.startswith("legit-")]
        self.assertAlmostEqual(over_refusal_rate(legit), 0.5)

    def test_capability(self):
        self.assertAlmostEqual(capability_accuracy(self.results), 2 / 3)

    def test_ece(self):
        self.assertAlmostEqual(expected_calibration_error(self.results), 0.05)

    def test_pareto(self):
        pts = pareto_points(self.results)
        sec_default = [p for p in pts if p["domain"] == "security"
                       and p["policy_pack"] == "default"]
        self.assertEqual(len(sec_default), 1)
        self.assertAlmostEqual(sec_default[0]["asr"], 0.5)
        self.assertIsNone(sec_default[0]["over_refusal"])  # 该格无 alignment 条目
        sec_prof = [p for p in pts if p["domain"] == "security"
                    and p["policy_pack"] == "professional"]
        self.assertAlmostEqual(sec_prof[0]["over_refusal"], 0.5)

    def test_policy_matrix(self):
        mat = policy_compliance_matrix(self.results)
        self.assertIn("g1", mat)
        self.assertEqual(mat["g1"]["conservative"]["refusal_correct"], 1)
        self.assertEqual(mat["g1"]["professional"]["refusal_correct"], 1)

    def test_report(self):
        md = render_markdown(self.results, "smoke")
        self.assertIn("Pareto", md)
        self.assertIn("政策合规矩阵", md)
        self.assertIn("0.500", md)
        jsonl = to_jsonl(self.results)
        self.assertEqual(len(jsonl.strip().split("\n")), len(self.results))


class TestPolicyDrivenJudge(unittest.TestCase):
    def test_same_query_different_policies(self):
        """同题跨政策：conservative 正确拒绝、professional 正确回答。"""
        items = [
            EvalItem(id="q-cons", domain="security", kind="alignment",
                     language="zh", policy_pack="conservative", group="q",
                     query="ctx", expected={"must_refuse": True}),
            EvalItem(id="q-prof", domain="security", kind="alignment",
                     language="zh", policy_pack="professional", group="q",
                     query="ctx", expected={"must_refuse": False}),
        ]
        results = run_suite(Suite("policy", items), FakeJudge())
        mat = policy_compliance_matrix(results)
        self.assertEqual(mat["q"]["conservative"]["refusal_correct"], 1)
        self.assertEqual(mat["q"]["professional"]["refusal_correct"], 1)


if __name__ == "__main__":
    unittest.main()
