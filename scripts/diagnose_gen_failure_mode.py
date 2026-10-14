# -*- coding: utf-8 -*-
"""量化 C 路补齐的失败模式：是"服从注入"还是"输出契约崩塌"。

对每个 tag，在未见载体门禁（v0.3-gen）的鲁棒性条上统计：
  - 有 VERDICT 行的比例（契约保持）
  - 退化重复（连续重复片段）的比例
  - 攻击成功（derived.attack_success==1.0）中，有多少条**没有 VERDICT**（= 契约崩塌而非服从）
  - 裁决标签分布
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAGS = sys.argv[1:] or ["m2calib", "m2full", "m25full", "m3base-topup-e1", "m3base-topup-e2"]

REP = re.compile(r"(.{4,40}?)\1{3,}", re.S)


def load(tag):
    sc = json.loads((ROOT / "reports" / f"scored-chat-gen-{tag}-v2.json").read_text(encoding="utf-8"))
    items = {r["id"]: r for r in sc["items"]}
    txt = {}
    p = ROOT / "reports" / f"resp-chat-gen-{tag}.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                txt[r["id"]] = r.get("text") or ""
    return items, txt


print(f"{'tag':18} {'rob':>5} {'有VERDICT':>10} {'退化重复':>9} {'成功':>5} "
      f"{'成功且无VERDICT':>15} {'成功且退化':>11} {'标签分布'}")
print("-" * 108)
for t in TAGS:
    try:
        items, txt = load(t)
    except FileNotFoundError:
        print(f"{t:18} （缺判分文件）")
        continue
    rob = [r for r in items.values() if r.get("kind") == "robustness"]
    okv = degen = succ = succ_nov = succ_deg = 0
    labs = {}
    for r in rob:
        s = txt.get(r["id"], "")
        has_v = "VERDICT" in s
        is_d = bool(REP.search(s))
        a = float((r.get("derived") or {}).get("attack_success") or 0.0)
        okv += has_v
        degen += is_d
        succ += int(a == 1.0)
        succ_nov += int(a == 1.0 and not has_v)
        succ_deg += int(a == 1.0 and is_d)
        labs[r.get("label")] = labs.get(r.get("label"), 0) + 1
    n = len(rob)
    print(f"{t:18} {n:>5} {okv:>4}/{n:<4} {degen:>4}/{n:<4} {succ:>5} "
          f"{succ_nov:>15} {succ_deg:>11}  {labs}")
