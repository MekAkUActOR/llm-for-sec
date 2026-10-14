# -*- coding: utf-8 -*-
"""审计 **真正的入训文件** data/sft/m2.5-staging/*.jsonl（★更正上一轮审错文件之误）。

上一轮我用 data/heldout/v0.5-topup-families/*.jsonl（74 KB 的**评测集**）当"入训数据"，
得出"三族 100% 契约共模、负样本为 0 ⇒ 照原样入训会崩塌"的结论 ✗。
**但真正的入训文件是 data/sft/m2.5-staging/**（各 3.4–4.9 MB）。
且 T9 生成器自述"负例 7 / 负例占比 ≥30%" ⇒ 上一轮结论很可能不成立。
本脚本对真文件重做同一套检查（A/B/C 三类）。
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
STAGING = ROOT / "data" / "sft" / "m2.5-staging"
BUDGET = 450
#: 契约标记（与 audit_dpo_discriminative_axes 同源口径）
MARKER_PATTERNS = ("VERDICT", "verdict", "action")
FAMILIES = ("t2_mechanism.jsonl", "doc_structure.jsonl", "t9_phish_expand.jsonl")


def iter_records(p: Path):
    with p.open(encoding="utf-8") as fh:
        for i, ln in enumerate(fh, 1):
            ln = ln.strip()
            if not ln:
                continue
            try:
                yield i, json.loads(ln)
            except json.JSONDecodeError:
                yield i, None


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
    print(f"审查目录 = {STAGING}（★真正的入训文件）")
    print(f"部署预算 = {BUDGET} 字符\n")
    print("=== 全部文件的真实行数（Python 计数，不信 PS）===")
    for p in sorted(STAGING.glob("*.jsonl")):
        n = sum(1 for _ in p.open(encoding="utf-8"))
        print(f"  {p.name:<36} {n:>8,} 行")
    print()

    verdicts = {}
    for name in FAMILIES:
        p = STAGING / name
        if not p.exists():
            print(f"--- {name}: 缺 ---")
            continue
        recs, bad = [], 0
        for _, r in iter_records(p):
            if r is None:
                bad += 1
            else:
                recs.append(r)
        texts = [target_text(r) for r in recs]
        ne = [t for t in texts if t]
        lens = [len(t) for t in ne]
        with_m = [t for t in ne if any(m in t for m in MARKER_PATTERNS)]
        print(f"--- {name} ---")
        print(f"    样本 {len(recs):,}（解析失败 {bad}）；有目标文本 {len(ne):,}")
        if lens:
            q = sorted(lens)
            print(f"    长度：中位 {statistics.median(lens):.0f}  p90 {q[int(len(q)*0.9)]:,}  最大 {max(lens):,}")
            over = sum(1 for x in lens if x > BUDGET)
            print(f"    超预算(>{BUDGET}) {over:,}/{len(lens):,} = {over/len(lens):.1%}")
        share = len(with_m) / len(ne) if ne else 0.0
        neg = len(ne) - len(with_m)
        a = share >= 0.95
        c = neg == 0
        verdicts[name] = (a, c)
        print(f"    [A 类] 契约标记率 = {share:.2%}  "
              f"{'★共模' if a else '★有对照 ✓'}")
        print(f"    [C 类] 不含标记的负样本 = {neg:,}（{neg/len(ne):.1%}）"
              f"  {'★为 0' if c else '★有 ✓'}")
        print()

    print("=== 汇总（对**入训文件**）===")
    nf = sum(1 for v in verdicts.values() if v[0] or v[1])
    print(f"  有结构缺陷的族 = {nf}/{len(verdicts)}")
    print(f"AUDIT-S1-TRAINING={'FAIL' if nf else 'PASS'}")
    print("\n★更正说明：上一轮报的 FAIL 基于评测集 heldout/v0.5-topup-families/*.jsonl，")
    print("  不是入训文件；本结果是**对入训文件**的真实读数。")
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
