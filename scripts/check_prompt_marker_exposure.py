# -*- coding: utf-8 -*-
"""闭合根因报告 §八.3：训练 prompt（conversations）里是否演示了 VERDICT 格式？

三种可能，含义完全不同：
  (a) system 里**有** VERDICT 格式示范 ⇒ 标记在上下文里有信号，衰减是**指令遵循退化**；
  (b) system 里**无**、且两侧都无 ⇒ 标记只从 SFT 习得，DPO 完全无约束；
  (c) 评估 prompt 要求 VERDICT 而训练 prompt 不要求 ⇒ **训推提示不一致**（更严重）。
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data/lf/dpo_m3_final.jsonl"

sys_has = 0
sys_show = 0
n = 0
sys_samples = []
first_sys = None

for line in P.open(encoding="utf-8"):
    if not line.strip():
        continue
    d = json.loads(line)
    n += 1
    convs = d.get("conversations") or []
    sys_txt = ""
    for m in convs:
        if isinstance(m, dict) and str(m.get("from", "")).lower() in ("system", "s"):
            sys_txt += str(m.get("value", "")) + "\n"
    if first_sys is None:
        first_sys = sys_txt
    if "VERDICT" in sys_txt:
        sys_has += 1
        if sys_show < 2:
            sys_show += 1
            i = sys_txt.find("VERDICT")
            sys_samples.append(sys_txt[max(0, i - 200):i + 220])

print(f"训练对数 = {n}")
print(f"★system/conversations 里含字面 VERDICT 的对数 = {sys_has} ({sys_has/n*100:.1f}%)")

print("\n--- 首条 system 全文（前 900 字符）---")
print((first_sys or "<空>")[:900])

if sys_samples:
    print("\n--- system 中 VERDICT 出现处的上下文 ---")
    for i, s in enumerate(sys_samples, 1):
        print(f"\n  [{i}] …{s}…")

print("\n=== 对比：评估侧 prompt 是否要求 VERDICT ===")
for name in ("resp-chat-gen-soup-a050.jsonl", "resp-chat-gen-m3-dpo.jsonl"):
    p = ROOT / "reports" / name
    if not p.exists():
        continue
    k = 0
    tot = 0
    ex = None
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        tot += 1
        pr = d.get("prompt", "")
        if "VERDICT" in pr:
            k += 1
            if ex is None:
                i = pr.find("VERDICT")
                ex = pr[max(0, i - 200):i + 200]
    print(f"  {name}: prompt 含 VERDICT = {k}/{tot} ({k/tot*100:.1f}%)")
    if ex:
        print(f"    上下文：…{ex}…")

print("\nPROMPT-MARKER-CHECK=DONE")
