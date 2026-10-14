# -*- coding: utf-8 -*-
"""看 DPO prompt 是否**规定了 VERDICT 行的内部 schema**（决定 action/verdict 键
是否应算"prompt 强制"）。

★动机：更正后的 `audit_dpo_discriminative_axes.py` 把"两侧都含 `"action":` 但
  prompt 未出现字面词 action"判为真缺陷 ✗。但若 prompt 已用例子写明了
  `VERDICT: {"action": ..., "verdict": ...}` 的格式，那么这两个键**也是被强制的** ✓
  ⇒ 判为缺陷会**误伤**，且会误导后续修数据的方向 ✗。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DPO = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
KEYS = ("VERDICT", "action", "verdict")


def prompt_text(d: dict) -> str:
    parts = []
    conv = d.get("conversations")
    if isinstance(conv, list):
        for m in conv:
            if isinstance(m, dict):
                role = m.get("from") or m.get("role")
                if role in ("system", "human", "user"):
                    parts.append(str(m.get("value") or m.get("content") or ""))
    return "\n".join(parts)


def main() -> int:
    print(f"数据 = {DPO}")
    prompts: Counter = Counter()
    n = 0
    with DPO.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            n += 1
            prompts[prompt_text(d)] += 1
    print(f"共 {n:,} 对；**不同的 prompt 串** {len(prompts):,} 个\n")

    # 各键在 prompt 中的出现率（按对计权）
    for k in KEYS:
        hit = sum(c for pt, c in prompts.items() if k in pt)
        print(f"  prompt 含字面 {k!r} 的对数 = {hit:,}（{hit/n:.1%}）")

    print("\n=== 最常见的 2 个 prompt 串（去重后）===")
    for i, (pt, c) in enumerate(prompts.most_common(2), 1):
        print(f"\n--- #{i}（{c:,} 对）---")
        print(pt[:1400])

    # schema 判定：prompt 里是否出现 VERDICT 后跟 JSON 键的形态
    import re
    schema_re = re.compile(r'VERDICT\s*[:：]\s*\{[^}]*"(action|verdict)"', re.S)
    with_schema = sum(c for pt, c in prompts.items() if schema_re.search(pt))
    print(f"\n★prompt 里写明 `VERDICT: {{...\"action\"/\"verdict\"...}}` 形态的对数 = "
          f"{with_schema:,}（{with_schema/n:.1%}）")
    print("⇒ 若接近 100%，则 action/verdict 两个键**也是 prompt 强制的** ✓，")
    print("  把它们判为『未强制下的共模缺陷』是**假阳性** ✗。")
    print("\nPROMPT-SCHEMA-CHECK=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
