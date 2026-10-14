# -*- coding: utf-8 -*-
r"""★判分依据的完整分布：`evidence` / `label` / `derived` 三者的对应关系。

## 为什么这一步不能省

我曾担心"512 响应变长 ⇒ 大段引用注入 ⇒ 被判分器误判成 comply" ✗。
抽检显示判分器读的是**模型自己声明的 `action` 字段** ✓
（`evidence = "template action=answer"` ✓）—— 那是**语义**判定 ✓。

**⇒ 本脚本把三者的对应关系完整列出来** ✓：
若 `label=comply` 恒对应 `action=answer/report?`，且 `derived.attack_success=1.0` ✓
⇒ 判定是**自洽的** ✓ ⇒ 50.6% 是真读数 ✓✓。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def main() -> int:
    ap = argparse.ArgumentParser(description="evidence × label × attack_success 分布")
    ap.add_argument("--scored", nargs="+", required=True)
    a = ap.parse_args()

    for pat in a.scored:
        for p in sorted(ROOT.glob(pat)) or [Path(pat)]:
            if not p.exists():
                print(f"  ★缺 {p.name}")
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            items = [x for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"]
            print(f"\n{'='*84}\n{p.name}  鲁棒性 {len(items)} 条\n{'='*84}")
            trip = Counter()
            ev_by_label: dict[str, Counter] = {}
            for x in items:
                lab = str(x.get("label"))
                ev = str(x.get("evidence"))
                asr = None
                if isinstance(x.get("derived"), dict):
                    asr = x["derived"].get("attack_success")
                trip[(lab, ev, asr)] += 1
                ev_by_label.setdefault(lab, Counter())[ev] += 1
            print("  label × evidence × attack_success：")
            for (lab, ev, asr), c in sorted(trip.items(), key=lambda kv: -kv[1]):
                print(f"    {lab:<16} | {ev:<34} | as={asr}  ×{c}")
            print("\n  按 label 归并的 evidence：")
            for lab, c in sorted(ev_by_label.items()):
                print(f"    {lab:<16} {dict(c)}")
    print("\nEVIDENCE-DIST=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
