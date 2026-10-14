# -*- coding: utf-8 -*-
r"""★受控实验：从**同一份 512 响应**切出各预算，量化"口径 → 契约保留率"。

## 为什么这是硬证据

第 18 轮独立复算发现：起点 `soup-a050` 在 v0.3-gen 上的契约保留率
**512 口径 97.3%** ✓ vs **96 口径 46.9%** ✗✗。

但"97.3% vs 46.9%"是**两次不同的实跑**比出来的 —— 严格说仍可能有别的差异 ✗。
本脚本用**同一份 512 产物**做**受控对照** ✓：
模型、条目、prompt、解码全同 ✓，**只改新 token 上限** ✓
（依据：`do_sample=False` ⇒ 贪心解码是**前缀确定**的 ✓，
故 `new_token_ids[:N]` 解码 = 直接实跑 N ✓）。

⇒ 若各预算的保留率曲线恰好复现 96 口径的低值 ✓，
则"**96 口径测的是截断，不是契约遵守**"由**受控实验**确证 ✓✓。

## 只读

本脚本**不写任何实跑同名的产物** ✓ —— 避免与正在进行的真实跑批混淆 ✗。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TOK = (ROOT / ".cache" / "huggingface" / "hub"
       / "models--Qwen--Qwen3-0.6B-Base" / "snapshots"
       / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
VERDICT = re.compile(r"VERDICT\s*[:：]")
BUDGETS = (64, 96, 128, 160, 192, 256, 384, 512)


def main() -> int:
    ap = argparse.ArgumentParser(description="口径→契约保留率 受控实验（只读）")
    ap.add_argument("--responses", default="reports/resp-chat-gen-soup-a050-mnt512.jsonl")
    ap.add_argument("--out", default="reports/caliber-curve-soup-a050.json")
    a = ap.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(TOK))

    p = ROOT / a.responses
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        print("★0 条记录", file=sys.stderr)
        return 2
    if not all(isinstance(r.get("new_token_ids"), list) for r in rows):
        print("★有条目缺 new_token_ids ⇒ 无法做前缀切分（fail-closed）", file=sys.stderr)
        return 2

    print(f"源 = {a.responses}   条目 = {len(rows)}")
    print(f"★受控实验：同模型/同条目/同 prompt/同贪心解码，**只改新 token 上限**\n")
    print(f"  {'预算':>5} {'含VERDICT':>10} {'保留率':>9} {'被截断':>9} {'截断率':>8}")
    curve = []
    for n in BUDGETS:
        hit = trunc = 0
        for r in rows:
            ids = r["new_token_ids"][:n]
            txt = tok.decode(ids, skip_special_tokens=True)
            if VERDICT.search(txt):
                hit += 1
            # 该预算下"被截断" = 真实长度超过 n
            if len(r["new_token_ids"]) > n:
                trunc += 1
        rate = hit / len(rows)
        tr = trunc / len(rows)
        curve.append({"budget": n, "verdict_rate": round(rate, 4),
                      "truncated_share": round(tr, 4), "n": len(rows)})
        print(f"  {n:>5} {hit:>10} {rate:>9.1%} {trunc:>9} {tr:>8.1%}")

    Path(ROOT / a.out).write_text(json.dumps({
        "source": a.responses, "n_items": len(rows),
        "method": ("同一份 512 贪心产物按 new_token_ids[:N] 切分 "
                   "（贪心前缀确定 ⇒ 与实跑 N 逐 token 等价）；只读，不写实跑同名产物"),
        "curve": curve,
        "preregistered_mustb_threshold": 63 / 168,
        "reading": ("若 96 附近的保留率≈96 口径实跑值（46.9%）而 512 处≈97%，"
                    "则 96 口径测的是截断而非契约遵守 ✓"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport -> {a.out}")
    print("CALIBER-CURVE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
