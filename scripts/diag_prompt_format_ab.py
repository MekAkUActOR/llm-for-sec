# -*- coding: utf-8 -*-
"""提示格式 A/B：裸续写 vs chat(LF qwen3_nothink)（2026-09-30，事后复核）。

发现：scripts/baseline_eval.py 的 BaseJudge 把 **item.query 原文**直接喂模型
（`self.tok(item.query)`），**没有 chat 模板**。该脚本写于 M0（对象是 base 模型，
裸续写正确），模型转为指令微调后从未更新。于是 G1/G4 与全部 heldout 行为读数
都在"非部署提示格式"下采集。

本脚本对**同一批 heldout 条目**用三种格式各生成一次，输出判分器 v2 可直接消费的
jsonl（schema: id/domain/kind/language/policy_pack/prompt/text）：

  raw          原样（复现现行管线）
  chat_user    <|im_start|>user\\n{q}<|im_end|>\\n<|im_start|>assistant\\n
  chat_system  <|im_start|>system\\n你是安全感知助手。<|im_end|>\\n + 同上

用法：
  python scripts/diag_prompt_format_ab.py --heldout reports/heldout-tooloutput-subset \
      --models m25full:checkpoints/qwen3-06b-sec-m25-full m2full:checkpoints/qwen3-06b-sec-m2-full \
      --out-dir reports/ab-promptformat
随后对每个 jsonl 跑 score_heldout_v2.py 得到标签分布。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SYS_PROMPT = "你是安全感知助手。"


def lf_chat(q: str, with_system: bool) -> str:
    """LLaMA-Factory qwen3_nothink 等价渲染（assistant 头后无思考块）。"""
    s = ""
    if with_system:
        s += f"<|im_start|>system\n{SYS_PROMPT}<|im_end|>\n"
    s += f"<|im_start|>user\n{q}<|im_end|>\n<|im_start|>assistant\n"
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heldout", required=True)
    ap.add_argument("--models", nargs="+", required=True, help="name:path")
    ap.add_argument("--out-dir", default="reports/ab-promptformat")
    ap.add_argument("--max-new-tokens", type=int, default=96)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from secfm.eval.heldout import load_dir

    suite, problems = load_dir(str(ROOT / args.heldout))
    if problems:
        raise SystemExit("heldout problems: " + "; ".join(problems))
    items = suite.items
    print(f"heldout: {suite.name} / {len(items)} 条")

    styles = ["raw", "chat_user", "chat_system"]
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    for spec in args.models:
        name, path = spec.split(":", 1)
        mp = ROOT / path
        print(f"\n=== {name} ({path}) ===", flush=True)
        tok = AutoTokenizer.from_pretrained(str(mp))
        model = AutoModelForCausalLM.from_pretrained(
            str(mp), dtype=torch.bfloat16, device_map="cuda",
            attn_implementation="sdpa")
        model.eval()
        for style in styles:
            rows = []
            t0 = time.time()
            for it in items:
                if style == "raw":
                    prompt = it.query
                elif style == "chat_user":
                    prompt = lf_chat(it.query, with_system=False)
                else:
                    prompt = lf_chat(it.query, with_system=True)
                ids = tok(prompt, return_tensors="pt").to(model.device)
                with torch.no_grad():
                    gen = model.generate(
                        **ids, max_new_tokens=args.max_new_tokens,
                        do_sample=False, pad_token_id=tok.eos_token_id)
                text = tok.decode(gen[0][ids["input_ids"].shape[1]:],
                                  skip_special_tokens=True).strip()
                rows.append({
                    "id": it.id, "domain": it.domain, "kind": it.kind,
                    "language": it.language, "policy_pack": it.policy_pack,
                    "prompt": it.query, "text": text,
                })
            f = out_dir / f"resp-{name}-{style}.jsonl"
            f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                 for r in rows), encoding="utf-8")
            empt = sum(1 for r in rows if not r["text"])
            print(f"  {style:12} -> {f.name}  (空输出 {empt}/{len(rows)}, "
                  f"{time.time() - t0:.0f}s)", flush=True)
        del model
        torch.cuda.empty_cache()
    print(f"\n下一步：对 {out_dir} 下每个 jsonl 跑 "
          f"score_heldout_v2.py --heldout {args.heldout} --responses <file> --out <file>.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
