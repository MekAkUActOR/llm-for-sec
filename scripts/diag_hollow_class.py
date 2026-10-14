# -*- coding: utf-8 -*-
"""看 carrier_inject_hollow 等类别的 chosen/rejected 差异到底落在哪一维。

若两侧都含 VERDICT，则判别维度只可能是**散文**≠结构标记 ⇒ 验证"标记无信号"的机制。
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\data\lf\dpo_m3_final.jsonl")


def val(side) -> str:
    if isinstance(side, dict):
        return str(side.get("value", ""))
    if isinstance(side, str):
        return side
    if isinstance(side, list):
        return "\n".join(str(m.get("value", m)) if isinstance(m, dict) else str(m) for m in side)
    return ""


want = {"carrier_inject_hollow", "carrier_clean_overrefusal", "bt330_refusal", "reserve"}
shown = defaultdict(int)
diff_kind = Counter()
tail_same = Counter()

for line in P.open(encoding="utf-8"):
    if not line.strip():
        continue
    d = json.loads(line)
    cls = d.get("dpo_class", "?")
    if cls not in want:
        continue
    ch, rj = val(d.get("chosen")), val(d.get("rejected"))

    def payload(t):
        i = t.find("VERDICT")
        return t[i:].strip() if i >= 0 else ""

    def prose(t):
        i = t.find("VERDICT")
        return t[:i].strip() if i >= 0 else t.strip()

    pc, pr = payload(ch), payload(rj)
    if pc and pr:
        tail_same["两侧 VERDICT 块完全相同" if pc == pr else "两侧 VERDICT 块不同"] += 1
    diff_kind["散文不同" if prose(ch) != prose(rj) else "散文相同"] += 1

    if shown[cls] < 2:
        shown[cls] += 1
        print(f"\n===== [{cls}] id={d.get('id')} =====")
        print(f"  chosen  散文: {prose(ch)[:150]}")
        print(f"  chosen  VERDICT: {pc[:170]}")
        print(f"  rejected 散文: {prose(rj)[:150]}")
        print(f"  rejected VERDICT: {pr[:170]}")

print("\n=== 判别维度统计（限上述 4 类）===")
for k, v in diff_kind.most_common():
    print(f"  {k:<16} {v:>6}")
for k, v in tail_same.most_common():
    print(f"  {k:<24} {v:>6}")

print("\nHOLLOW-CLASS-DIAG=DONE")
