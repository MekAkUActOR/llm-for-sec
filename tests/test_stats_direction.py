# -*- coding: utf-8 -*-
"""规则 27 的机械化检验：方向相关的统计代码必须按方向自证。

背景（`reports/criterion-fix-mustc-orr.md` 9.3/9.4）：
  - `axis_decision` 在 `direction="higher_is_better"` 下**端点反序**，
    配对路径的 `width` 因此变成负数 ⇒ `resolution_ok` 假为 True（fail-open）；
  - 接线时把 `discordant=(n01, n10)` 按固定顺序传，在"越高越好"的轴上方向传反，
    p 由 0.0407 变成 0.978（保守 24 倍）。
此前所有调用都只用默认方向，所以两个 bug 都长期未暴露。
"""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from secfm.eval.stats import axis_decision, mcnemar_p  # noqa: E402


class TestCiEndpointsOrdered(unittest.TestCase):
    """(a) 两种方向下区间端点都必须正序，且宽度为正。"""

    def test_lower_is_better(self):
        d = axis_decision(9, 54, 5, 54, tolerance=0.05, direction="lower_is_better",
                          discordant=(6, 2))
        self.assertLessEqual(d["diff_ci95_paired"][0], d["diff_ci95_paired"][1])
        self.assertLessEqual(d["diff_ci95"][0], d["diff_ci95"][1])

    def test_higher_is_better(self):
        """本用例在修复前会失败（端点反序）。"""
        d = axis_decision(70, 168, 84, 168, tolerance=0.05,
                          direction="higher_is_better", discordant=(35, 21))
        self.assertLessEqual(d["diff_ci95"][0], d["diff_ci95"][1],
                             f"非配对 CI 端点反序：{d['diff_ci95']}")
        self.assertLessEqual(d["diff_ci95_paired"][0], d["diff_ci95_paired"][1],
                             f"配对 CI 端点反序：{d['diff_ci95_paired']}")

    def test_width_never_negative(self):
        """(c) 宽度为负会让 resolution_ok 假为 True ⇒ 必须杜绝。"""
        for direction in ("lower_is_better", "higher_is_better"):
            for tol in (0.01, 0.05, 0.5):
                with self.subTest(direction=direction, tol=tol):
                    d = axis_decision(9, 54, 5, 54, tolerance=tol,
                                      direction=direction, discordant=(6, 2))
                    if d.get("diff_ci95_paired"):
                        w = d["diff_ci95_paired"][1] - d["diff_ci95_paired"][0]
                        self.assertGreaterEqual(w, 0.0, "区间宽度为负")
                        self.assertEqual(d["resolution_ok"], w <= tol,
                                         "resolution_ok 与宽度不一致")


class TestDiscordantDirection(unittest.TestCase):
    """(b) 同一对不一致计数，两侧 p 必须一侧显著、另一侧不显著。"""

    def test_mcnemar_two_sides_complementary(self):
        """两侧**不是**和为 1，而是 1 + P(X = min(b,c))。

        推导（b+c=n、b 不等于 c，X~Binom(n,1/2)）：P(X>=c) = 1 - P(X<=c-1)，
        由对称性 P(X<=c-1) = P(X>=n-c+1) = P(X>=b+1)，
        故 P(X>=b) + P(X>=c) = 1 + P(X>=b) - P(X>=b+1) = 1 + P(X=b)。
        第一版断言"和为 1"是错的；本测试保留推导，防止再写错。
        """
        b, c = 35, 21
        n = b + c
        p_worse = mcnemar_p(b, c)
        p_better = mcnemar_p(c, b)
        self.assertLess(p_worse, 0.05, f"{b} vs {c} 应显著，实得 {p_worse}")
        self.assertGreater(p_better, 0.05, f"{c} vs {b} 不应显著，实得 {p_better}")
        pmf_min = math.comb(n, min(b, c)) / 2 ** n
        self.assertAlmostEqual(p_worse + p_better, 1.0 + pmf_min, places=9,
                               msg="应为 1 + P(X=min(b,c))，而非 1")

    def test_axis_decision_honours_b_side(self):
        """把"更差"那侧放在 b ⇒ 显著；放反 ⇒ 不显著。方向由调用方负责。"""
        wrong = axis_decision(70, 168, 84, 168, tolerance=0.05,
                              direction="higher_is_better", discordant=(21, 35))
        right = axis_decision(70, 168, 84, 168, tolerance=0.05,
                              direction="higher_is_better", discordant=(35, 21))
        self.assertGreater(wrong["fisher_p"], 0.05)
        self.assertLess(right["fisher_p"], 0.05)

    def test_contract_case_regression(self):
        """锁死真实读数：契约保留 84/168 → 70/168，p 约 0.0407。"""
        d = axis_decision(70, 168, 84, 168, tolerance=0.0,
                          direction="higher_is_better", discordant=(35, 21))
        self.assertAlmostEqual(d["fisher_p"], 0.0407, places=4)

    def test_mustc_case_regression(self):
        """锁死 MUST-C 的配对读数：5/54 → 9/54，配对 p 约 0.1445（不显著）。"""
        d = axis_decision(9, 54, 5, 54, tolerance=0.05,
                          direction="lower_is_better", discordant=(6, 2))
        self.assertAlmostEqual(d["fisher_p"], 0.1445, places=4)
        self.assertAlmostEqual(d["diff"], 0.0741, places=4)
        self.assertFalse(d["resolution_ok"], "n=54 下 0.05 公差原理上不可分辨")
        self.assertEqual(d["state"], "undecidable")


if __name__ == "__main__":
    unittest.main()
