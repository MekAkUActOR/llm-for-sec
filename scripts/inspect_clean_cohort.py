# -*- coding: utf-8 -*-
r"""看清 `carrier_clean_overrefusal` 的结构，为**外科式修法**做准备 ✓。

## 修法的设计原理（关键 ✓）

**现状**：干净支教的判别是「**没发现异常 ⇒ 干净 ⇒ answer**」✗ ——
而未见载体上模型**默认"没发现异常"** ✓ ⇒ 套用 `answer` ✗✓。

**修法**：把「干净」从**缺席信号**（没异常 ✗）改成**在场的显式标记** ✓
（载体自带 `provenance: verified-benign` 之类 ✓）。
**⇒ 判别规则变成「无良性标记 ⇒ 可疑」** ✓ = **保守方向** ✓✓ ——
**恰好与现在相反** ✓。

**★ 且必须配**同类的硬负样本**** ✓：注入**伪造**该良性标记 ✗ ⇒ chosen=`report` ✓
（否则模型会学"有标记就信"✗ —— 那只是把捷径换了个位置 ✗）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"


def side(s) -> str:
    if isinstance(s, dict):
        return str(s.get("value") or "")
    return str(s or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cls", default="carrier_clean_overrefusal")
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()

    rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    sel = [r for r in rows if str(r.get("dpo_class")) == a.cls]
    print(f"=== {a.cls}  n={len(sel)} ===")
    print(f"  src_task 取值 = {dict(Counter(str(r.get('src_task')) for r in sel).most_common(8))}")
    print(f"  lang = {dict(Counter(str(r.get('lang')) for r in sel))}")
    print(f"  pack = {dict(Counter(str(r.get('pack')) for r in sel))}")

    print(f"\n=== 抽 {a.n} 条完整看（human / chosen / rejected）===")
    for r in sel[:a.n]:
        h = next((str(c.get("value") or "") for c in (r.get("conversations") or [])
                  if c.get("from") == "human"), "")
        print(f"\n{'#'*90}\n# id={r.get('id')}  lang={r.get('lang')}  "
              f"src_task={r.get('src_task')}\n{'#'*90}")
        print(f"--- HUMAN ---\n{h}")
        print(f"\n--- CHOSEN ({len(side(r.get('chosen')))} 字) ---\n{side(r.get('chosen'))[:800]}")
        print(f"\n--- REJECTED ({len(side(r.get('rejected')))} 字) ---\n{side(r.get('rejected'))[:500]}")

    print("\n=== ★各类的『良性/干净』显式措辞统计（为本修法找锚点 ✓）===")
    marks = ("provenance", "verified", "benign", "已核验", "已确认", "内部", "受信",
             "trusted", "internal", "signed", "已签名", "白名单", "whitelist")
    for cls in ("carrier_clean_overrefusal", "carrier_inject_obedient",
                "carrier_inject_hollow"):
        sub = [r for r in rows if str(r.get("dpo_class")) == cls]
        n = len(sub)
        hits = Counter()
        for r in sub:
            h = next((str(c.get("value") or "") for c in (r.get("conversations") or [])
                      if c.get("from") == "human"), "")
            for m in marks:
                if m.lower() in h.lower():
                    hits[m] += 1
        print(f"  {cls:<30} n={n:<5} {dict(hits.most_common(6))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
