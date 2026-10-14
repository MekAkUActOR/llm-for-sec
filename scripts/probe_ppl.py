"""逐模型 × 逐域困惑度评测（M1 出口探针，docs/05 §7）。

对 data/probes/vX.Y/<域>.jsonl 计算每域平均 PPL（按 token 加权），
输出 JSON 报告，用于 base vs 训练 checkpoint 的对比：
- sec 域 PPL 相对 base 下降 ≥25%（M1 达标线）
- 通用域（general_en/general_zh）PPL 回升 ≤10%

用法：
    python scripts/probe_ppl.py --model <模型路径> --name <报告名> \
        [--probes data/probes/v0.1] [--max-len 2048] [--stride 1536]
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


def chunk_windows(ids: list[int], max_len: int, stride: int):
    """长文档滑窗切分：[(窗口 token 列表, 本窗口计分 token 数), ...]。

    非首窗口将前 (max_len - stride) 个 token 置为 -100（不计分），
    避免重复计分。返回的每个元素为 (labels 列表, 计分数)。
    """
    if len(ids) <= max_len:
        return [ids]
    windows = []
    start = 0
    while start < len(ids):
        end = min(start + max_len, len(ids))
        windows.append((start, end))
        if end == len(ids):
            break
        start += stride
    # 转为 labels：非首窗口开头 pad 段置 -100
    out = []
    for i, (s, e) in enumerate(windows):
        if i == 0:
            out.append(ids[s:e])
        else:
            skip = windows[i - 1][1] - s  # 与上一窗口重叠且已计分的部分
            out.append([-100] * skip + ids[s + skip:e])
    return out


def domain_ppl(model, tok, texts, max_len, stride, batch_size=4):
    """单域 PPL：所有窗口 NLL 按 token 加权平均。"""
    import torch
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
        # HF loss 是对非 -100 token 的均值 → 还原为总 NLL
        n_tok = int((labels != -100).sum())
        total_nll += float(out.loss) * n_tok
        total_tok += n_tok
        batch_labels = []

    for t in texts:
        ids = tok(t, add_special_tokens=False)["input_ids"]
        if not ids:
            continue
        n_docs += 1
        for win in chunk_windows(ids, max_len, stride):
            batch_labels.append(win)
            if len(batch_labels) >= batch_size:
                flush()
    flush()
    import math
    return {"ppl": math.exp(total_nll / total_tok) if total_tok else None,
            "nll": total_nll / total_tok if total_tok else None,
            "tokens": total_tok, "docs": n_docs}


def main():
    ap = argparse.ArgumentParser(description="探针 PPL 评测")
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True, help="报告名（如 base / stage1-202m）")
    ap.add_argument("--probes", default="data/probes/v0.1")
    ap.add_argument("--tokenizer", default=None)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--stride", type=int, default=1536)
    ap.add_argument("--out", default=None)
    # 2026-09-30 新增：batch 只影响**速度/显存**，几乎不影响 PPL 数值
    # （窗口集合不变；batch 内 padding 位置已用 -100 掩码，loss 按非 -100 token
    #  计数还原为总 NLL，PPL = 总 NLL / 总 token）。
    # 实测等价性（m2calib，v0.4 探针，batch4 vs batch1）：general_en 10.714 vs 10.716、
    # general_zh 19.193、ais 31.663 vs 31.695 —— 相对差 ≤0.1%，**非逐位相同**
    # （bf16 分批归约顺序不同），远低于任何门禁阈值（G2 用 ±10~25%）。
    # 实测动机：本机 24 GB 卡上 batch=4 时 4×2048×151936 的 fp32 logits 造成
    # ~23 GB 峰值 → WDDM 分页抖动，同口径 PPL 从 107 s 劣化到 >15 min；
    # batch=1 实测 123.6 s、峰值显存仅数百 MB。
    ap.add_argument("--batch-size", type=int, default=4,
                    help="默认 4（历史口径）；显存紧张时用 1，数值差 ≤0.1%%")
    # ★注意：argparse 的 help 走 %-格式化，正文里的百分号必须写成 %%
    #   （2026-09-30 实测：单个 % 会抛 ValueError: badly formed help string，
    #    整个脚本连 --help 都跑不起来；本次由 eval_needlefix.ps1 暴露）
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer or args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="cuda",
        attn_implementation="sdpa")
    model.eval()

    probes = ROOT / args.probes
    # 排除行为索引文件（v0.3 的 *-index.jsonl：{id,title,query} 结构，
    # 属 baseline_eval 查询式探针，无 text 字段，PPL 探针消费会 KeyError）
    domains = sorted(p for p in probes.glob("*.jsonl")
                     if not p.name.endswith("-index.jsonl"))
    if not domains:
        raise SystemExit(f"no probe jsonl under {probes}")

    report = {"model": args.model, "name": args.name, "probes": args.probes,
              "max_len": args.max_len, "stride": args.stride,
              "domains": {}}
    t0 = time.time()
    for p in domains:
        texts = [json.loads(l)["text"] for l in
                 p.read_text(encoding="utf-8").splitlines() if l.strip()]
        r = domain_ppl(model, tok, texts, args.max_len, args.stride, args.batch_size)
        report["domains"][p.stem] = r
        print(f"  {p.stem}: PPL={r['ppl']:.3f}  "
              f"({r['docs']} docs / {r['tokens']:,} tokens)", flush=True)

    report["elapsed_s"] = round(time.time() - t0, 1)
    out = Path(args.out) if args.out else ROOT / "reports" / f"ppl-{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
