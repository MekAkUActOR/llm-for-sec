# -*- coding: utf-8 -*-
r"""★★★ 查 `carrier_clean_overrefusal` 到底在教什么 —— 这决定 M4 值不值得发射。

## 假说

M3 的失败模式是 **`action=answer`** ✗（81/168 条自己声明照做 ✓）。
而第 17 轮记录显示有一类偏好对：
**`carrier_clean_overrefusal`：chosen=`answer`(1320) vs rejected=`report`(1320)** ✗
⇒ **字面上就在教"用 answer 取代 report"** ✗✓。

**★ 若该类样本的 prompt 是"干净载体"（无攻击 ✓）⇒ 教 answer 是对的 ✓，
但模型可能**泛化到攻击载体**上** ✗✓ ⇒ **长度匹配修不好它** ✗ ⇒ H1 会失败 ✓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
ACT = re.compile(r"action\"?\s*[:：]\s*\"?([A-Za-z_]+)")
CLS = re.compile(r'"dpo_class"\s*:\s*"([^"]+)"')


def side_text(side) -> str:
    if isinstance(side, dict):
        return str(side.get("value") or "")
    if isinstance(side, list) and side and isinstance(side[-1], dict):
        return str(side[-1].get("value") or "")
    return str(side or "")


def main() -> int:
    ap = argparse.ArgumentParser(description="逐 dpo_class 统计 chosen/rejected 的 action")
    ap.add_argument("--data", required=True)
    ap.add_argument("--cls", default="carrier_clean_overrefusal")
    ap.add_argument("--samples", type=int, default=1)
    a = ap.parse_args()

    d = ROOT / a.data
    rows = [json.loads(l) for l in d.read_text(encoding="utf-8").splitlines() if l.strip()]
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(str(r.get("dpo_class")), []).append(r)

    print(f"=== {d.name}：逐 dpo_class 的 action 对照（全 {len(rows)} 行）===")
    print(f"  {'dpo_class':<30} {'n':>6} {'chosen 的 action':<34} {'rejected 的 action'}")
    for cls, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        cc = Counter()
        cr = Counter()
        for r in rs:
            m = ACT.search(side_text(r.get("chosen")))
            cc[m.group(1) if m else "(无)"] += 1
            m = ACT.search(side_text(r.get("rejected")))
            cr[m.group(1) if m else "(无)"] += 1
        print(f"  {cls:<30} {len(rs):>6} "
              f"{str(dict(cc.most_common(3))):<34} {dict(cr.most_common(3))}")

    rs = by.get(a.cls) or []
    if rs:
        print(f"\n=== {a.cls} 抽 {a.samples} 对看原文 ===")
        for i, r in enumerate(rs[:a.samples], 1):
            conv = r.get("conversations") or []
            hum = next((c.get("value") for c in conv if c.get("from") == "human"), "")
            print(f"\n{'='*82}\n### 第 {i} 对   id={r.get('id')}  src_task={r.get('src_task')}")
            print(f"  --- human（前 700 字）---\n{str(hum)[:700]}")
            print(f"  --- chosen ---\n{side_text(r.get('chosen'))[:600]}")
            print(f"  --- rejected ---\n{side_text(r.get('rejected'))[:600]}")
    print("\nDPO-CLASS-SEMANTICS=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
