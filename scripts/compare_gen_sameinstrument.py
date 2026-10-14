# -*- coding: utf-8 -*-
"""同仪器（v0.3-gen 258 条）未见载体门禁的两两对照 + 所需样本量。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from secfm.eval.scored import robustness_axes  # noqa: E402
from secfm.eval.stats import fisher_p, wilson, diff_ci, required_n  # noqa: E402

tags = sys.argv[1:] or ["m2calib", "m2full", "m25full", "m3base-topup-e1", "m3base-topup-e2"]
rows = {}
for t in tags:
    p = ROOT / "reports" / f"scored-chat-gen-{t}-v2.json"
    if not p.exists():
        continue
    a = robustness_axes(json.loads(p.read_text(encoding="utf-8")))["all"]
    rows[t] = (a.get("success", 0), a.get("n", 0))

print(f"{'tag':18} {'k/n':>12} {'rate':>8} {'95% CI':>20}")
for t, (k, n) in rows.items():
    lo, hi = wilson(k, n)
    print(f"{t:18} {f'{k}/{n}':>12} {k/n:>8.4f}   [{lo:.3f}, {hi:.3f}]")

print("\n两两对照（Fisher 精确检验，双尾）")
print("  注：差值 = 第二个 − 第一个；`diff_ci(k1,n1,k2,n2)` 返回的正是该朝向的 Newcombe 区间")
ks = list(rows)
for i in range(len(ks)):
    for j in range(i + 1, len(ks)):
        a, b = ks[i], ks[j]
        ka, na = rows[a]
        kb, nb = rows[b]
        p = fisher_p(ka, na, kb, nb)
        d = kb / nb - ka / na
        lo, hi = diff_ci(ka, na, kb, nb)
        if not (lo <= d <= hi):
            lo, hi = hi, lo
        flag = "可区分" if p < 0.05 else "★未达可区分"
        print(f"  {a:18} → {b:18} {kb/nb:.4f} - {ka/na:.4f} = "
              f"{d:+.4f}  CI[{lo:+.3f},{hi:+.3f}]  p={p:.3g}  {flag}")

n34 = required_n(0.036, 0.15)
print(f"\n分辨 3.6% → 18.6%（15pp）所需每组样本量 ≈ {n34}（当前 168/载体总，够）")
