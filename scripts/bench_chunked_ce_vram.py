r"""分块 CE 显存基准：补丁前后 12k/16k/32k 峰值实测。

忠实还原训练占用：bf16 模型 + AdamW 状态（fp32 双动量，warmup 步
物化）+ 梯度 + 一次 fwd+bwd（labels，packing 全注意力，无 pad 掩码）。
报告 torch.cuda.max_memory_allocated 峰值与预留（reserved）。

用法（GPU 空闲时）：
    python -X utf8 scripts\bench_chunked_ce_vram.py [--model PATH] \
        [--seq 12288,16384,32768] [--chunk 4096]
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

MODEL = ROOT / "checkpoints" / "qwen3-06b-sec-c1-full"


def _free():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()


def _run_one(model, opt, L, vocab, gen, patched_label):
    """单序列长度一次 fwd+bwd（含优化器状态已物化）。返回峰值 dict。"""
    torch.cuda.reset_peak_memory_stats()
    ids = torch.randint(0, vocab, (1, L), generator=gen,
                        device="cuda")
    labels = ids.clone()
    out = model(input_ids=ids, labels=labels)
    out.loss.backward()
    peak_alloc = torch.cuda.max_memory_allocated() / 2**30
    peak_res = torch.cuda.max_memory_reserved() / 2**30
    model.zero_grad(set_to_none=True)
    del ids, labels, out
    return {"label": patched_label, "seq": L,
            "peak_alloc_gb": round(peak_alloc, 2),
            "peak_reserved_gb": round(peak_res, 2),
            "oom": False}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(MODEL))
    ap.add_argument("--seq", default="12288,16384,32768")
    ap.add_argument("--chunk", type=int,
                    default=int(__import__("os").environ.get(
                        "CHUNKED_CE_CHUNK", "1024")))
    ap.add_argument("--out", default="reports/chunked-ce-vram.json")
    args = ap.parse_args(argv)
    seqs = [int(x) for x in args.seq.split(",")]

    import patch_chunked_ce as pce
    from transformers import AutoModelForCausalLM

    assert torch.cuda.is_available(), "需要 GPU（8k 主线结束后再跑）"
    dev = "cuda"
    results = []

    def bench_round(patched: bool, seq_list):
        pce.patch(args.chunk) if patched else pce.unpatch()
        _free()
        model = AutoModelForCausalLM.from_pretrained(
            args.model, torch_dtype=torch.bfloat16).to(dev)
        model.train()
        model.gradient_checkpointing_enable()
        vocab = model.config.vocab_size
        # 优化器状态物化（AdamW fp32 双动量）：64-token warmup 步
        opt = torch.optim.AdamW(model.parameters(), lr=1e-5, fused=True)
        gen = torch.Generator(device=dev).manual_seed(9)
        warm_ids = torch.randint(0, vocab, (1, 64), generator=gen,
                                 device=dev)
        loss = model(input_ids=warm_ids,
                     labels=warm_ids.clone()).loss
        loss.backward()
        opt.step()
        model.zero_grad(set_to_none=True)
        del warm_ids, loss
        _free()
        static_alloc = torch.cuda.memory_allocated() / 2**30
        for L in seq_list:
            try:
                r = _run_one(model, opt, L, vocab, gen,
                             "patched" if patched else "unpatched")
                r["static_alloc_gb"] = round(static_alloc, 2)
                results.append(r)
                print(json.dumps(r, ensure_ascii=False))
            except torch.cuda.OutOfMemoryError as e:
                model.zero_grad(set_to_none=True)
                results.append({"label": "patched" if patched else
                                "unpatched", "seq": L, "oom": True,
                                "err": str(e)[:80]})
                print(json.dumps(results[-1], ensure_ascii=False))
                _free()
        del model, opt
        _free()

    bench_round(False, [s for s in seqs if s <= 16384])  # 原版：16k 内
    bench_round(True, seqs)                               # 补丁：全部

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"model": args.model, "chunk": args.chunk,
         "note": "峰值含 bf16 模型+AdamW fp32 状态+梯度+单步 fwd/bwd；"
                 "reserved 为 PyTorch 缓存池口径", "results": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
