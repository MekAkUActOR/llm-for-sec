r"""LF 训练栈显存分解探针（fp32 谱系复刻）：定位 23.8GB 的构成。

复刻 m16-32k 训练态：fp32 模型（auto 加载谱系）+ AdamW（fp32 状态）
+ 梯度检查点 + bf16 autocast + 分块 CE。逐阶段打点峰值，并测试
chunk 2048/1024 与无 autocast 对照。

用法： python -X utf8 scripts\probe_lf_vram_breakdown.py [--seq 32768]
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


def _peak(tag, results):
    alloc = torch.cuda.max_memory_allocated() / 2**30
    res = torch.cuda.max_memory_reserved() / 2**30
    results.append({"phase": tag, "peak_alloc_gb": round(alloc, 2),
                    "peak_reserved_gb": round(res, 2)})
    print(json.dumps(results[-1], ensure_ascii=False))
    torch.cuda.reset_peak_memory_stats()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq", type=int, default=32768)
    ap.add_argument("--chunks", default="4096,2048,1024")
    args = ap.parse_args(argv)

    import patch_chunked_ce as pce
    from transformers import AutoModelForCausalLM

    results = []
    model = AutoModelForCausalLM.from_pretrained(str(MODEL)).to("cuda")
    model.train()
    model.gradient_checkpointing_enable()
    _peak("load_fp32+ckpt_enable", results)

    opt = torch.optim.AdamW(model.parameters(), lr=1e-5)
    gen = torch.Generator(device="cuda").manual_seed(9)
    # 优化器状态物化（64 tok warmup）
    warm = torch.randint(0, model.config.vocab_size, (1, 64),
                         generator=gen, device="cuda")
    with torch.autocast("cuda", dtype=torch.bfloat16):
        wl = model(input_ids=warm, labels=warm.clone()).loss
    wl.backward()
    opt.step()
    model.zero_grad(set_to_none=True)
    del warm, wl
    gc.collect(); torch.cuda.empty_cache()
    _peak("after_adamw_states", results)

    vocab = model.config.vocab_size
    ids = torch.randint(0, vocab, (1, args.seq), generator=gen,
                        device="cuda")
    labels = ids.clone()

    def _arm(tag, chunk, autocast, with_labels):
        pce.patch(chunk) if chunk else pce.unpatch()
        gc.collect(); torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        try:
            import contextlib
            ctx = (torch.autocast("cuda", dtype=torch.bfloat16)
                   if autocast else contextlib.nullcontext())
            with ctx:
                if with_labels:
                    out = model(input_ids=ids, labels=labels)
                else:  # 纯 backbone：直调主干（不过 lm_head），末隐之和反传
                    hs = model.model(input_ids=ids).last_hidden_state
                    out = type("L", (), {"loss": hs.float().sum()})()
            out.loss.backward()
            _peak(f"{tag}", results)
        except torch.cuda.OutOfMemoryError as e:
            results.append({"phase": tag, "oom": True,
                            "err": str(e)[:60]})
            print(json.dumps(results[-1], ensure_ascii=False))
        model.zero_grad(set_to_none=True)
        gc.collect(); torch.cuda.empty_cache()

    # 对照臂矩阵：定位峰值归属（backbone vs 分块 CE vs autocast vs chunk）
    _arm("32k_bwd_autocast_chunk4096", 4096, True, True)
    _arm("32k_bwd_autocast_chunk512", 512, True, True)
    _arm("32k_bwd_NOautocast_chunk4096", 4096, False, True)
    _arm("32k_bwd_autocast_backbone_only", None, True, False)

    out = ROOT / "reports" / "lf-vram-breakdown.json"
    out.write_text(json.dumps(
        {"model": str(MODEL), "seq": args.seq,
         "note": "fp32 谱系复刻（LF auto 加载）+ AdamW fp32 状态 + "
                 "梯度检查点 + bf16 autocast + 分块 CE", "results": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
