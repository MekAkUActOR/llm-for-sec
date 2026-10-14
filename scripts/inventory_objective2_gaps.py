# -*- coding: utf-8 -*-
"""盘点 objective ② 的缺口：m25-full / m2-full / m3-dpo 的**部署格式(chat)**产物齐不齐？

objective ② 要求"按部署格式重测 m25-full/m2-full（heldout 161 + needle + sec），
产出修正后的 G3/G4/sec 读数并裁决 M3 起点" ⇒ 逐个 tag 对账。
"""
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")

# (标签, 说明) —— 覆盖 heldout 161 / needle / sec 三类
CHECKS = [
    ("resp-chat-gen-{t}.jsonl", "部署格式生成（v0.3-gen，含 sec/契约）"),
    ("scored-chat-gen-{t}-v2.json", "v0.3-gen 判分"),
    ("longctx-{t}-chat.json", "needle（chat 口径）"),
    ("resp-chat-{t}-v2.jsonl", "部署格式生成（v0.2.1 对齐/ORR）"),
    ("scored-chat-{t}-v2.json", "v0.2.1 判分"),
    ("scored-chat-to-{t}-v2.json", "v0.4-toolout 回归"),
    ("ppl-{t}-v0.4.json", "v0.4 PPL"),
]

TAGS = ["m2calib", "soup-a050", "m25full", "m2full", "m3-dpo"]

rows = {t: [] for t in TAGS}
for pat, desc in CHECKS:
    for t in TAGS:
        p = R / pat.format(t=t)
        mark = "✓" if p.exists() else "✗"
        rows[t].append(mark)

print(f"{'产物':<42}" + "".join(f"{t:>11}" for t in TAGS))
print("-" * (42 + 11 * len(TAGS)))
for i, (pat, desc) in enumerate(CHECKS):
    line = f"{pat.format(t=''):<42}"
    for t in TAGS:
        line += f"{rows[t][i]:>11}"
    print(line)

print("\n=== 缺口（objective ② 未完成项）===")
for t in TAGS:
    miss = [CHECKS[i][0].format(t=t) for i in range(len(CHECKS)) if rows[t][i] == "✗"]
    if miss:
        print(f"  {t:<10} 缺 {len(miss)} 项：{', '.join(miss)}")
    else:
        print(f"  {t:<10} 齐备 ✓")
