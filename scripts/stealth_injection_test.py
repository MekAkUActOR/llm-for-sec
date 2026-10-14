# -*- coding: utf-8 -*-
r"""★★★★★★ 决定性数字：**不带任何自称词汇的注入，顺从率是多少**。

## 为什么这是关键

上一版把注入按"自称词汇"分三档 ✓，但三档**只覆盖 83/168 条** ✗。
总数 85 条 comply 里只有 23 条落在三档内 ✗
⇒ **62 条顺从来自"无自称词汇"的条目** ✗✓ —— 那是最隐蔽的注入 ✓。

**⇒ 若"无自称"档的 ASR 远高于其它档 ⇒ 机制确定：**
**模型的检测依赖**显式词汇**，遇到**纯语义意图的隐蔽注入**就漏检** ✗✓
**⇒ M4 必须补**隐蔽注入**的正样本** ✗✓。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CARRIER = re.compile(r"<carrier\b[^>]*>(.*?)</carrier>", re.S)
ALLKEYS = ("指令", "裁决", "instruct", "override", "系统提示词", "忽略操作者",
           "忽略以上", "处理说明", "备注", "说明", "注记", "提示", "政策",
           "条款", "policy", "§")


def carrier_map() -> dict[str, str]:
    out = {}
    d = ROOT / "data" / "heldout" / "v0.3-gen"
    for p in sorted(d.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) != "robustness":
                continue
            m = CARRIER.search(str(r.get("query") or ""))
            if m:
                out[str(r.get("id"))] = m.group(1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="无自称词汇的隐蔽注入 ASR")
    ap.add_argument("--show", type=int, default=2)
    a = ap.parse_args()

    cm = carrier_map()
    for name, rel in [("起点", "reports/scored-chat-gen-soup-a050-v2-mnt512.json"),
                      ("m3-dpo", "reports/scored-chat-gen-m3-dpo-v2-mnt512.json")]:
        p = ROOT / rel
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        items = [x for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"]
        labeled = [x for x in items
                   if any(k.lower() in cm.get(str(x.get("id")), "").lower()
                          for k in ALLKEYS)]
        stealth = [x for x in items if x not in labeled]
        print(f"\n{'='*86}\n{name}   n={len(items)}\n{'='*86}")
        for lab, sub in (("带自称词汇", labeled), ("★无自称词汇（隐蔽）", stealth)):
            if not sub:
                continue
            k = sum(1 for x in sub if str(x.get("label")) == "comply")
            rf = sum(1 for x in sub if str(x.get("label")) == "report_finding")
            print(f"  {lab:<22} n={len(sub):>4}  comply={k:>3}  "
                  f"ASR={k/len(sub):>6.1%}   检测到(report_finding)={rf}")
        kk = sum(1 for x in stealth if str(x.get("label")) == "comply")
        kl = sum(1 for x in labeled if str(x.get("label")) == "comply")
        print(f"\n  ★顺从的构成：隐蔽类 {kk} 条 / 带词汇类 {kl} 条  （合计 {kk+kl}）")

        if name != "起点" and a.show:
            print(f"\n  --- 无自称词汇的样本（看注入长什么样）---")
            for x in stealth[:a.show]:
                print(f"\n  ### {x.get('id')}  label={x.get('label')}  "
                      f"evidence={str(x.get('evidence'))[:70]}")
                print("  " + cm.get(str(x.get("id")), "")[:1100].replace("\n", "\n  "))
    print("\n★判读：若『无自称词汇』档 ASR 远高 ⇒ 模型**靠显式词汇检测** ✗ ⇒")
    print("   M4 必须补**纯语义意图、无指令词汇**的隐蔽注入正样本 ✓✓")
    print("\nSTEALTH-INJECTION=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
