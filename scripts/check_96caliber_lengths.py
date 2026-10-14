# -*- coding: utf-8 -*-
r"""对比 96 口径下 起点 vs m3-dpo 的**响应长度分布**与契约保留率。

★目的：判 M3 那次 `20/168` 到底是"契约没学会"✗，还是"响应被截断"✗。
  若 m3-dpo 在 96 口径下的文本长度**逼近上限 96 token**（即被切断），
  则它的低保留率是**截断产物** ✓，与"是否学会契约"无关 ✓。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TOK = (ROOT / ".cache" / "huggingface" / "hub"
       / "models--Qwen--Qwen3-0.6B-Base" / "snapshots"
       / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
VERDICT = re.compile(r"VERDICT\s*[:：]")


def main() -> int:
    ap = argparse.ArgumentParser(description="96 口径下起点 vs m3-dpo 的长度与保留率")
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--cap", type=int, default=96, help="该口径的新 token 上限")
    a = ap.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(TOK))
    nt = lambda s: len(tok(s, add_special_tokens=False)["input_ids"])

    print(f"口径上限 = {a.cap} token")
    print(f"\n  {'产物':<40} {'条目':>5} {'tok中位':>8} {'tok≥cap-3':>10} "
          f"{'含VERDICT':>10} {'保留率':>8}")
    for pat in a.files:
        for p in sorted(ROOT.glob(pat)) or [Path(pat)]:
            if not p.exists():
                print(f"  {p.name}: 不存在")
                continue
            rows = [json.loads(l) for l in
                    p.read_text(encoding="utf-8").splitlines() if l.strip()]
            if not rows:
                print(f"  {p.name}: ★0 条")
                continue
            toks = [nt(str(r.get("text", ""))) for r in rows]
            med = st.median(toks)
            near = sum(1 for t in toks if t >= a.cap - 3)
            hit = sum(1 for r in rows if VERDICT.search(str(r.get("text", ""))))
            print(f"  {p.name:<40} {len(rows):>5} {med:>8.0f} {near:>10}"
                  f" {hit:>10} {hit/len(rows):>8.1%}")

    print("\n★读法：若 m3-dpo 的 tok中位**贴近上限**（≈cap）且 'tok≥cap-3' 占比很高 ✓，")
    print("  则该口径下它的响应被**整批切断** ✗ ⇒ 低保留率是截断产物 ✓，")
    print("  不能作为'契约未学会'的证据 ✗。")
    print("\n96-CALIBER-LENGTH-CHECK=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
