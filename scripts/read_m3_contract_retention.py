# -*- coding: utf-8 -*-
"""取 m3-dpo 的契约保留率（MUST-B 的分子/分母）——本次实验最该看的那个数。

复用 topup_verdict.py 里已实现且经过回归测试的 contract_rate(tag)，
避免在这里另写一套口径（规则 21：口径必须与判据一致）。
"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import topup_verdict as tv  # noqa: E402

print("=== MUST-B 契约保留率（响应含 VERDICT 的鲁棒性条目 / 鲁棒性条目）===")
rows = []
for tag in ("m2calib", "soup-a050", "m2full", "m25full", "m3-dpo"):
    try:
        r = tv.contract_rate(tag)
    except Exception as e:  # noqa: BLE001
        print(f"  {tag:<12} ✗ {type(e).__name__}: {e}")
        continue
    if r is None:
        print(f"  {tag:<12} （无读数/产物缺失）")
        continue
    k, n = r
    rows.append((tag, k, n))
    print(f"  {tag:<12} {k:>4}/{n} = {k/n:.4f}")

if rows:
    base = dict((t, (k, n)) for t, k, n in rows)
    print("\n=== 相对 soup-a050（M3 的起点，预注册登记 70/168）===")
    bk, bn = base.get("soup-a050", (None, None))
    for tag, k, n in rows:
        if tag == "soup-a050" or bk is None:
            continue
        # 契约保留率 = higher_is_better：变体不得比起点低太多
        print(f"  {tag:<12} {k}/{n}；相对起点 Δ条数 = {k - bk:+d}，"
              f"Δ比率 = {k/n - bk/bn:+.4f}（门禁阈值 ≥63/168 = 0.3750）")

print("\nMUST-B-READING=DONE")
