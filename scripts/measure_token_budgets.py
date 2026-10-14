# -*- coding: utf-8 -*-
"""按 **token** 统计"训练目标长度 vs 部署预算"，以决定 max_new_tokens 该取多少。

★为什么必须按 token：`max_new_tokens` 是 token 数，而此前所有讨论都用**字符**近似
  （"450 字符 ≈ 96 token"）。字符↔token 的比例随语言与内容漂移，
  **用字符推断预算会系统性失准** ✗。本脚本用真实 tokenizer 量。

产出：每个训练族的目标长度分位数（token），以及覆盖率
      "预算 ≥ 该族多少比例的样本"。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TOK = (ROOT / ".cache" / "huggingface" / "hub"
       / "models--Qwen--Qwen3-0.6B-Base" / "snapshots"
       / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
STAGING = ROOT / "data" / "sft" / "m2.5-staging"
FAMILIES = ("t2_mechanism.jsonl", "doc_structure.jsonl", "t9_phish_expand.jsonl")
DPO = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
BUDGETS = (96, 192, 256, 384, 512, 768)


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


def quantiles(xs: list[int]) -> dict:
    q = sorted(xs)
    n = len(q)
    def at(p):
        return q[min(n - 1, int(n * p))]
    return {"n": n, "min": q[0], "p25": at(.25), "p50": at(.50),
            "p75": at(.75), "p90": at(.90), "p99": at(.99), "max": q[-1],
            "mean": round(statistics.fmean(q), 1)}


def main() -> int:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(TOK))
    print(f"tokenizer = {TOK.name}\n")

    def ntok(s: str) -> int:
        return len(tok(s, add_special_tokens=False)["input_ids"])

    print("=== SFT 三族：目标长度（token）===")
    allfam: dict[str, list[int]] = {}
    for name in FAMILIES:
        p = STAGING / name
        if not p.exists():
            print(f"--- {name}: 缺")
            continue
        lens = []
        for ln in p.open(encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            t = target_text(r)
            if t:
                lens.append(ntok(t))
        allfam[name] = lens
        q = quantiles(lens)
        print(f"--- {name}（n={q['n']}）---")
        print(f"    p25={q['p25']}  p50={q['p50']}  p75={q['p75']}  "
              f"p90={q['p90']}  p99={q['p99']}  max={q['max']}  mean={q['mean']}")
        cov = "  ".join(f"{b}:{sum(1 for x in lens if x <= b)/len(lens):.1%}" for b in BUDGETS)
        print(f"    预算覆盖率  {cov}")

    print("\n=== DPO chosen / rejected 长度（token）===")
    if DPO.exists():
        ch, rj = [], []
        for ln in DPO.open(encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            for key, acc in (("chosen", ch), ("rejected", rj)):
                v = r.get(key)
                txt = ""
                # ★2026-10-06 修：DPO 的 chosen/rejected 实际是**字典**
                #   `{'from': 'gpt', 'value': '...'}` —— 原版没处理 dict ⇒ 测出 0 条 ✗。
                if isinstance(v, str):
                    txt = v
                elif isinstance(v, dict):
                    c = v.get("value") or v.get("content") or ""
                    txt = c if isinstance(c, str) else ""
                elif isinstance(v, list):
                    for m in reversed(v):
                        if isinstance(m, dict) and (m.get("role") or m.get("from")) in ("assistant", "gpt"):
                            c = m.get("content") or m.get("value") or ""
                            txt = c if isinstance(c, str) else ""
                            break
                if txt:
                    acc.append(ntok(txt))
        for nm, acc in (("chosen", ch), ("rejected", rj)):
            if not acc:
                continue
            q = quantiles(acc)
            print(f"--- {nm}（n={q['n']}）---")
            print(f"    p50={q['p50']}  p75={q['p75']}  p90={q['p90']}  "
                  f"p99={q['p99']}  max={q['max']}  mean={q['mean']}")
            cov = "  ".join(f"{b}:{sum(1 for x in acc if x <= b)/len(acc):.1%}" for b in BUDGETS)
            print(f"    预算覆盖率  {cov}")

    print("\n=== 结论提示 ===")
    for name, lens in allfam.items():
        if not lens:
            continue
        for b in BUDGETS:
            if sum(1 for x in lens if x <= b) / len(lens) >= 0.90:
                print(f"  {name}: 达到 90% 覆盖率所需预算 = **{b}** token")
                break
        else:
            print(f"  {name}: 即使 {BUDGETS[-1]} token 也覆盖不到 90% ✗")
    print("\nTOKEN-BUDGET-MEASURE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
