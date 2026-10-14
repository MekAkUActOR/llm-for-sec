# -*- coding: utf-8 -*-
"""验证：S1 入训文件的 **prompt 侧**是否本就要求"以 VERDICT 行结尾"。

★这是判定"契约 100% 共模"是**缺陷**还是**正确行为**的关键：
  - 若 prompt 每次都要求发 VERDICT ⇒ 目标 100% 含 VERDICT 是**合规模仿** ✓
    （此时真正的问题在**长度**：目标超出部署预算 ⇒ 截断 ⇒ 契约丢失）
  - 若 prompt 有时要求、有时不要求 ⇒ 目标却总含 VERDICT ⇒ 才是**共模缺陷**
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
STAGING = ROOT / "data" / "sft" / "m2.5-staging"
FAMILIES = ("t2_mechanism.jsonl", "doc_structure.jsonl", "t9_phish_expand.jsonl")

#: prompt 侧可能出现的"必须发契约"指令片段
MANDATE_PATTERNS = (
    "VERDICT", "verdict",
    "必须以", "结尾", "最后一行", "输出格式",
)


def prompt_text(rec) -> str:
    """取 prompt（用户侧/系统侧），不含目标回答。"""
    if not isinstance(rec, dict):
        return ""
    parts = []
    for k in ("instruction", "input", "prompt", "query", "question", "system"):
        v = rec.get(k)
        if isinstance(v, str):
            parts.append(v)
    for k in ("messages", "conversations"):
        v = rec.get(k)
        if isinstance(v, list):
            for m in v:
                if isinstance(m, dict):
                    role = m.get("role") or m.get("from")
                    content = m.get("content") or m.get("value")
                    if role in ("user", "human", "system") and isinstance(content, str):
                        parts.append(content)
    return "\n".join(parts)


def target_text(rec) -> str:
    if not isinstance(rec, dict):
        return ""
    for k in ("output", "response", "completion", "assistant", "target", "answer"):
        v = rec.get(k)
        if isinstance(v, str) and v:
            return v
    for k in ("messages", "conversations"):
        v = rec.get(k)
        if isinstance(v, list):
            for m in reversed(v):
                if isinstance(m, dict):
                    role = m.get("role") or m.get("from")
                    content = m.get("content") or m.get("value")
                    if role in ("assistant", "gpt") and isinstance(content, str):
                        return content
    return ""


def main() -> int:
    print(f"审查入训文件 = {STAGING}\n")
    for name in FAMILIES:
        p = STAGING / name
        if not p.exists():
            continue
        tot = mandate = with_v = 0
        for ln in p.open(encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            tot += 1
            pt = prompt_text(r)
            # "要求发契约"：prompt 里出现 VERDICT 字面，或有"必须/结尾/最后一行"类指令
            if ("VERDICT" in pt or "verdict" in pt
                    or any(k in pt for k in ("必须以", "最后一行", "结尾"))):
                mandate += 1
            if "VERDICT" in target_text(r):
                with_v += 1
        print(f"--- {name} ---")
        print(f"    样本 {tot:,}")
        print(f"    prompt 侧要求发契约 = {mandate:,} ({mandate/tot:.2%})" if tot else "")
        print(f"    目标含 VERDICT     = {with_v:,} ({with_v/tot:.2%})" if tot else "")
        if tot:
            if mandate / tot > 0.95 and with_v / tot > 0.95:
                print("    ⇒ ★prompt 要求 + 目标合规 ⇒ 契约共模**不是缺陷**，"
                      "真正问题是长度（见下）")
            elif with_v / tot > 0.95 and mandate / tot < 0.95:
                print("    ⇒ ★prompt 并非总要求，目标却总含 ⇒ **共模缺陷**")
            else:
                print("    ⇒ 需人工判读")
        print()
    print("PROMPT-MANDATE-CHECK=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
