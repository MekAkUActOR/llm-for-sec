# -*- coding: utf-8 -*-
r"""★把"缺 VERDICT"分解为**被截断** ⟷ **真没写**，判契约退化是否口径无关。

## 为什么这是决定性的

第 18 轮我一度用"奥卡姆剃刀"论证：
**"契约从未被摧毁，它只是被截断了"** ✗ —— 并据此把 M3 的裁定挂起 ⏳。

**512 口径的实测把那个论证证伪了** ✗：
`m3-dpo` 缺 109 个 VERDICT，而**被截断的只有 32 条** ✓
⇒ 若"缺 VERDICT"全部由截断造成，则缺的应 ≤32 ✓ —— **实际是 109** ✗✗。

⇒ 必须把两类**精确分开** ✓：
- **截断性缺失**：`finish_reason == "length"` 且无 VERDICT ⇒ 口径问题 ✓
- **真实性缺失**：**未**被截断（`stop`）却无 VERDICT ⇒ **契约退化** ✗✓

**★ 只有真实性缺失才构成"契约被破坏"的证据** ✓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
VERDICT = re.compile(r"VERDICT\s*[:：]")


def main() -> int:
    ap = argparse.ArgumentParser(description="缺 VERDICT 的截断/真实分解")
    ap.add_argument("--responses", nargs="+", required=True)
    a = ap.parse_args()

    print("=== 缺 VERDICT 的分解（512 部署口径）===")
    print(f"  {'产物':<44} {'条目':>5} {'有V':>5} {'截断缺':>7} {'真实缺':>7} "
          f"{'真实缺失率':>10}")
    for pat in a.responses:
        for p in sorted(ROOT.glob(pat)) or [Path(pat)]:
            if not p.exists():
                print(f"  {p.name}: 不存在")
                continue
            rows = [json.loads(l) for l in
                    p.read_text(encoding="utf-8").splitlines() if l.strip()]
            if not rows:
                print(f"  {p.name}: ★0 条")
                continue
            n = len(rows)
            has = trunc_miss = real_miss = 0
            for r in rows:
                ok = bool(VERDICT.search(str(r.get("text", ""))))
                if ok:
                    has += 1
                    continue
                if r.get("finish_reason") == "length":
                    trunc_miss += 1
                else:
                    real_miss += 1
            print(f"  {p.name:<44} {n:>5} {has:>5} {trunc_miss:>7} {real_miss:>7} "
                  f"{real_miss/n:>10.1%}")

    print("\n★判读：")
    print("  · 「真实缺」= 生成本身已结束(stop)、却仍无 VERDICT ⇒ **契约退化** ✗✓")
    print("  · 「截断缺」= 被预算切掉 ⇒ **口径问题** ✓，加预算即可消 ✓")
    print("  · 若真实缺失率显著 > 0 ⇒ 契约退化**与口径无关** ✗ ⇒")
    print("    则『契约只是被截断』的论证被**证伪** ✗✓")
    print("\nMUSTB-DECOMPOSE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
