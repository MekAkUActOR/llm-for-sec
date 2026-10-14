# -*- coding: utf-8 -*-
"""漂移性质判别：raw 续写 vs assistant 框架 vs user 框架（2026-09-30）。

动机：M2.5 出口判定 G2 FAIL（general_en +15.2% / general_zh +22.8% vs m15），
且 v0.4 干净口径复现同样幅度（+15.08%）→ 排除"探针污染"。但**仍未回答**：
这 +15~23% 是"通用建模能力退化"，还是"SFT 后模型预期产出应答体而非续写原文"
的**框架位移**（probe 是原始文档，训练数据全是 chat 格式）。

判据：同一批文档、同一计分口径，只换前缀框架：
  raw   无前缀（复现门禁口径）
  asst  `<|im_start|>assistant\\n`（把文档当作"模型即将产出的话"）
  user  `<|im_start|>user\\n`（把文档当作"用户输入"）
若 m25/m15 比值在 asst 或 user 下显著塌缩 → 框架位移；若三框架一致 → 能力退化。
另附 sec / ais（漂移最大域，+110% / +64%）——框架位移假说预测它们同样塌缩。

计分与窗口逻辑**完全复用** scripts/probe_ppl.py（chunk_windows），仅前缀 token 置 -100。

用法：
  python scripts/diag_ppl_framing.py --docs 60 \
     --models m15:checkpoints/qwen3-06b-sec-m15 m25full:checkpoints/qwen3-06b-sec-m25-full
输出：reports/diag-ppl-framing.json（+ stdout 比值表）
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from probe_ppl import chunk_windows  # noqa: E402  （复用窗口化，保证口径一致）

FRAMES = {
    "raw": "",
    "asst": "<|im_start|>assistant\n",
    "user": "<|im_start|>user\n",
}


def domain_ppl_framed(model, tok, texts, prefix, max_len, stride, batch_size=4):
    """与 probe_ppl.domain_ppl 同口径，但序列前加 prefix（prefix 不计分）。"""
    import torch
    prefix_ids = (tok(prefix, add_special_tokens=False)["input_ids"]
                  if prefix else [])
    total_nll, total_tok, n_docs = 0.0, 0, 0
    batch_labels: list[list[int]] = []

    def flush():
        nonlocal total_nll, total_tok, batch_labels
        if not batch_labels:
            return
        pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
        maxlen = max(len(x) for x in batch_labels)
        input_ids = torch.full((len(batch_labels), maxlen), pad_id, dtype=torch.long)
        labels = torch.full((len(batch_labels), maxlen), -100, dtype=torch.long)
        attn = torch.zeros((len(batch_labels), maxlen), dtype=torch.long)
        for i, lab in enumerate(batch_labels):
            ids = [x if x >= 0 else pad_id for x in lab]
            input_ids[i, :len(lab)] = torch.tensor(ids)
            labels[i, :len(lab)] = torch.tensor(lab)
            attn[i, :len(lab)] = 1
        input_ids, labels, attn = (input_ids.cuda(), labels.cuda(), attn.cuda())
        with torch.no_grad():
            out = model(input_ids=input_ids, attention_mask=attn, labels=labels)
        n_tok = int((labels != -100).sum())
        total_nll += float(out.loss) * n_tok
        total_tok += n_tok
        batch_labels = []

    for t in texts:
        ids = tok(t, add_special_tokens=False)["input_ids"]
        if not ids:
            continue
        n_docs += 1
        full = prefix_ids + ids
        wins = chunk_windows(full, max_len, stride)
        if prefix_ids and wins:
            w0 = wins[0]
            for i in range(min(len(prefix_ids), len(w0))):
                w0[i] = -100          # 前缀不计分
        for win in wins:
            batch_labels.append(win)
            if len(batch_labels) >= batch_size:
                flush()
    flush()
    return {"ppl": math.exp(total_nll / total_tok) if total_tok else None,
            "nll": total_nll / total_tok if total_tok else None,
            "tokens": total_tok, "docs": n_docs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True,
                    help="name:path 形式，可多个；第一个视为参照系")
    ap.add_argument("--probes", default="data/probes/v0.4")
    ap.add_argument("--domains", nargs="+",
                    default=["general_en", "general_zh", "sec", "ais"])
    ap.add_argument("--docs", type=int, default=60, help="每域取前 N 篇（0=全量）")
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--stride", type=int, default=1536)
    ap.add_argument("--out", default="reports/diag-ppl-framing.json")
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    probes = ROOT / args.probes
    texts_by_dom = {}
    for dom in args.domains:
        p = probes / f"{dom}.jsonl"
        if not p.exists():
            print(f"  [skip] {dom}: 探针不存在")
            continue
        ts = [json.loads(l)["text"] for l in
              p.read_text(encoding="utf-8").splitlines() if l.strip()]
        texts_by_dom[dom] = ts[:args.docs] if args.docs else ts

    rep = {"probes": args.probes, "docs_per_domain": args.docs,
           "frames": list(FRAMES), "models": {}, "matrix": {}}
    t_all = time.time()
    for spec in args.models:
        name, path = spec.split(":", 1)
        print(f"\n=== {name}  ({path}) ===", flush=True)
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForCausalLM.from_pretrained(
            path, dtype=torch.bfloat16, device_map="cuda",
            attn_implementation="sdpa")
        model.eval()
        rep["models"][name] = path
        for dom, texts in texts_by_dom.items():
            for fname, prefix in FRAMES.items():
                t0 = time.time()
                r = domain_ppl_framed(model, tok, texts, prefix,
                                      args.max_len, args.stride)
                rep["matrix"].setdefault(dom, {}).setdefault(fname, {})[name] = r
                print(f"  {dom:12} {fname:5} PPL={r['ppl']:8.3f} "
                      f"({r['docs']} docs / {r['tokens']:,} tok, "
                      f"{time.time() - t0:.0f}s)", flush=True)
        del model
        torch.cuda.empty_cache()

    # 比值表 + 判据
    base = args.models[0].split(":", 1)[0]
    print("\n" + "=" * 74)
    print(f"m25/m15 PPL 比值（参照系={base}；塌缩=框架位移，持平=能力退化）")
    print("=" * 74)
    print(f"  {'域':12} " + " ".join(f"{f:>10}" for f in FRAMES))
    verdict = {}
    for dom, frames in rep["matrix"].items():
        cells = []
        for fname in FRAMES:
            b = frames.get(fname, {}).get(base, {}).get("ppl")
            others = [v["ppl"] for k, v in frames.get(fname, {}).items()
                      if k != base and v.get("ppl")]
            cells.append(others[0] / b if b and others else float("nan"))
        verdict[dom] = {"ratio": {f: round(c, 4)
                                  for f, c in zip(FRAMES, cells)}}
        print(f"  {dom:12} " + " ".join(f"{c:10.4f}" for c in cells))
    rep["ratio"] = verdict
    rep["elapsed_s"] = round(time.time() - t_all, 1)
    out = ROOT / args.out
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport -> {out}  (总耗时 {rep['elapsed_s']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
