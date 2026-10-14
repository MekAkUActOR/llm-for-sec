# -*- coding: utf-8 -*-
"""抽看 DPO 各类的 chosen/rejected 实际文本 —— 判"类别语义是否被样本体现"。

★动机：token 实测发现 `carrier_inject_obedient` 的 rejected 只有 **51 token** 中位，
  但该类**自称**是"执行载体注入指令" ✗ —— 若 rejected 实际只是**简短拒绝**，
  那这一对教的是"短=坏"，而不是"服从注入=坏" ✗✗（语义与标签不符）。
  这是"长度混杂"之外更深的一层：**标签与内容是否一致**。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DPO = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
SHOW = ("carrier_inject_obedient", "carrier_inject_hollow",
        "carrier_clean_overrefusal", "calibration")
PER = 2


def txt(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("value") or v.get("content") or "")
    if isinstance(v, list):
        for m in reversed(v):
            if isinstance(m, dict) and (m.get("role") or m.get("from")) in ("assistant", "gpt"):
                return str(m.get("value") or m.get("content") or "")
    return ""


def clean(s: str, n: int = 420) -> str:
    s = s.replace("\n", "⏎")
    return s[:n] + ("…" if len(s) > n else "")


def main() -> int:
    want = {c: [] for c in SHOW}
    with DPO.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            c = str(d.get("dpo_class"))
            if c in want and len(want[c]) < PER:
                want[c].append(d)
            if all(len(v) >= PER for v in want.values()):
                break

    for cls in SHOW:
        print(f"\n{'='*78}\n### {cls}（抽 {len(want[cls])} 条）\n{'='*78}")
        for i, d in enumerate(want[cls], 1):
            ch, rj = txt(d.get("chosen")), txt(d.get("rejected"))
            print(f"\n--- #{i}  id={d.get('id')}  src_task={d.get('src_task')}  "
                  f"lang={d.get('lang')} ---")
            print(f"  [chosen  {len(ch):5d} 字符] {clean(ch)}")
            print(f"  [rejected{len(rj):5d} 字符] {clean(rj)}")

    print("\n=== 判读要点 ===")
    print("  · `carrier_inject_obedient` 的 rejected 若只是**简短拒绝**而非")
    print("    **执行注入的长回复**，则标签与内容不符 ✗ ⇒ 必须重新生成，")
    print("    光做长度匹配也不够（长度匹配只治症，不治本）。")
    print("  · `carrier_inject_hollow` 的 rejected 按定义就该是**短**的，")
    print("    故修法是改为「**冗长但空洞**」并等长 ✓。")
    print("\nDPO-CLASS-SAMPLE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
