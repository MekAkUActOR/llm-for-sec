# -*- coding: utf-8 -*-
"""权威载体普查（**修正转义**）：`<carrier type=\"X\" ...>` 在每个文件里的分布。

修正说明：训练文件是 JSONL，信封的引号被 JSON 转义为 `\"`。
先前两版正则（裸 `<carrier>`、未转义 `type="`）都因此得 0——**这是方法错，不是事实**。
字节级验证：`<carrier type=\\"` 在 `sft_m25.jsonl` 出现 **13,981** 次，
与 docs/01 记的"13,981 行带信封"逐位吻合。

本脚本回答：**document 载体到底有没有进入活谱系。**
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 关键：引号被 JSON 转义 ⇒ 匹配 `type=\"X\"`
PAT = re.compile(r'<carrier\s+type=\\"([^\\"]+)\\"')

FILES = [
    ("sft_m25.jsonl", "m25-full（**活**）"),
    ("sec_sft_needlefix.jsonl", "soup-a050 的一半（**活**）"),
    ("dpo_m3_final.jsonl", "M3 DPO（**活**，训练中）"),
    ("sec_sft_topup.jsonl", "C 路 top-up（**已废弃**）"),
    ("sec_sft_needlefix_carrier.jsonl", "R5 候选（未使用）"),
    ("carrier_sft_slice.jsonl", "载体切片"),
]

rows_by_type = {}
for name, role in FILES:
    p = ROOT / "data" / "lf" / name
    if not p.exists():
        print(f"{name:<36} 缺失")
        continue
    c = Counter()
    rows = withc = 0
    with p.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            rows += 1
            ms = PAT.findall(line)
            if ms:
                withc += 1
                for t in ms:
                    c[t.lower()] += 1
    rows_by_type[name] = c
    print(f"\n{name:<36} [{role}]")
    print(f"  行数={rows:>8,}  带信封行数={withc:>7,}  信封数={sum(c.values()):>7,}")
    print(f"  分布：" + (" ".join(f"{k}={v}" for k, v in c.most_common(10)) if c else "（无）"))
    print(f"  ★ document = {c.get('document', 0)}")

LIVE = ("sft_m25.jsonl", "sec_sft_needlefix.jsonl", "dpo_m3_final.jsonl")
print("\n" + "=" * 74)
for t in ("document", "text", "email", "tool_output", "log", "webpage", "code"):
    lv = sum(rows_by_type.get(n, Counter()).get(t, 0) for n in LIVE)
    dp = rows_by_type.get("sec_sft_topup.jsonl", Counter()).get(t, 0)
    print(f"  {t:<12} 活谱系合计={lv:>7,}   已废弃 C 路={dp:>6,}")
print("\n⇒ 若活谱系合计为 0 而 C 路非 0，则该载体**只在废弃分支里出现过**，")
print("  对任何活产物而言它仍是**未见载体**（可支撑未见载体泛化）。")
