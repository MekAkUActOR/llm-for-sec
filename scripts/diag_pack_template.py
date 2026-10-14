# -*- coding: utf-8 -*-
"""判别：pack 一致性探针的空输出是否由"训练/推理模板不一致"造成（2026-09-30）。

背景：`pack_consistency.py --run` 对 m25-full 产出 73/120 空输出（conservative 37/40），
而训练用的是 LLaMA-Factory `qwen3_nothink`（assistant 头后**无**思考块），
该探针用的是 HF 原生 `apply_chat_template(enable_thinking=False)`（会插空 ` thinking` 块）。

做法：取 sweep 前若干条（跨 3 个包），同一 prompt 用两种模板各生成一次（greedy），
对比输出长度与内容。若 LF 模板下空输出消失 → 确证为模板不一致。

用法：python scripts/diag_pack_template.py --n 6
输出：reports/diag-pack-template.json（+ stdout 对照表）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SWEEP = ROOT / "reports" / "pack-consistency-sweep.jsonl"


def lf_style_prompt(messages) -> str:
    """复刻 LLaMA-Factory qwen3_nothink：system/user 各自成块，末尾给 assistant 头。"""
    parts = []
    for m in messages:
        role = m["role"]
        parts.append(f"<|im_start|>{role}\n{m['content']}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="checkpoints/qwen3-06b-sec-m25-full")
    ap.add_argument("--n", type=int, default=6, help="取前 N 条（按 sweep 顺序，跨包）")
    ap.add_argument("--max-new-tokens", type=int, default=160)
    ap.add_argument("--out", default="reports/diag-pack-template.json")
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    mp = ROOT / args.model
    tok = AutoTokenizer.from_pretrained(str(mp))
    model = AutoModelForCausalLM.from_pretrained(
        str(mp), dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()

    entries = [json.loads(l) for l in
               SWEEP.read_text(encoding="utf-8").splitlines() if l.strip()][:args.n]
    out = []
    for e in entries:
        row = {"id": e["id"], "pack": e["pack"], "expected_action": e["expected_action"]}
        variants = {}
        try:
            variants["hf_enable_thinking_false"] = tok.apply_chat_template(
                e["messages"], tokenize=False, add_generation_prompt=True,
                enable_thinking=False)
        except TypeError:
            variants["hf_enable_thinking_false"] = tok.apply_chat_template(
                e["messages"], tokenize=False, add_generation_prompt=True)
        variants["lf_qwen3_nothink"] = lf_style_prompt(e["messages"])
        for vname, prompt in variants.items():
            ids = tok(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                gen = model.generate(**ids, max_new_tokens=args.max_new_tokens,
                                     do_sample=False,
                                     pad_token_id=tok.eos_token_id)
            text = tok.decode(gen[0][ids["input_ids"].shape[1]:],
                              skip_special_tokens=True).strip()
            row[vname] = {"len": len(text), "empty": len(text) == 0,
                          "has_verdict": "VERDICT" in text,
                          "head": text[:150]}
        out.append(row)
        print(f"  {e['id']:28} hf_len={row['hf_enable_thinking_false']['len']:5} "
              f"lf_len={row['lf_qwen3_nothink']['len']:5} "
              f"| hf_empty={row['hf_enable_thinking_false']['empty']} "
              f"lf_empty={row['lf_qwen3_nothink']['empty']}", flush=True)

    n = len(out)
    summ = {
        "n": n,
        "hf_empty": sum(r["hf_enable_thinking_false"]["empty"] for r in out),
        "lf_empty": sum(r["lf_qwen3_nothink"]["empty"] for r in out),
        "hf_has_verdict": sum(r["hf_enable_thinking_false"]["has_verdict"] for r in out),
        "lf_has_verdict": sum(r["lf_qwen3_nothink"]["has_verdict"] for r in out),
    }
    print("\n汇总:", json.dumps(summ, ensure_ascii=False))
    (ROOT / args.out).write_text(
        json.dumps({"summary": summ, "rows": out}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"report -> {ROOT / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
