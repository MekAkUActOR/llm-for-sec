"""单卡 Llama 架构从零预训练脚本(Windows 原生,适配 RTX 5090 / 24GB)。

用法示例(项目根目录执行):

  # 1) 端到端冒烟测试(tiny 模型 + 合成数据,约 1 分钟,验证整条训练管线)
  .venv\\Scripts\\python.exe scripts\\pretrain_1b.py --preset tiny --synthetic --max-steps 20 --save-steps 20

  # 2) 吞吐基准(125M 模型 + 合成数据;用于实测 MFU,推算 1B 训练时长)
  .venv\\Scripts\\python.exe scripts\\pretrain_1b.py --preset 125m --synthetic --max-steps 60 --peak-tflops 400

  # 3) 正式 1B 预训练(先用 scripts/tokenize_text.py 生成 data\\tokens.npy)
  .venv\\Scripts\\python.exe scripts\\pretrain_1b.py --preset 1b --data data\\tokens.npy --tokenizer Qwen/Qwen2.5-1.5B

  # 4) 断点续训
  .venv\\Scripts\\python.exe scripts\\pretrain_1b.py --preset 1b --data data\\tokens.npy --tokenizer Qwen/Qwen2.5-1.5B --resume

预设规模(参数量按 Qwen 词表 151936 估算,tie embeddings):
  tiny  ~10M   | 125m  ~130M | 350m ~0.5B | 1b ~1.3B

显存策略:
  1b 预设默认 bf16 权重 + bf16 梯度 + bf16 优化器状态(约 10.2GB 常驻),
  梯度检查点开启,micro_bs=2 + accum=32(131k tokens/step),24GB 卡可跑。
  显存富余时可上调 --micro-bs(4 约需 +6GB 的 logits 瞬时开销)。
"""

import argparse
import glob
import os
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoTokenizer,
    LlamaConfig,
    LlamaForCausalLM,
    Trainer,
    TrainerCallback,
    TrainingArguments,
    default_data_collator,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PRESETS = {
    #            d     L    heads  kv   ffn    vocab    ctx
    "tiny": dict(d=256, L=4, heads=8, kv=4, ffn=1024, vocab=32000, ctx=512),
    "125m": dict(d=768, L=12, heads=12, kv=12, ffn=3072, vocab=32000, ctx=1024),
    "350m": dict(d=1024, L=24, heads=16, kv=16, ffn=4096, vocab=151936, ctx=2048),
    "1b": dict(d=2048, L=16, heads=32, kv=8, ffn=8192, vocab=151936, ctx=2048),
}
LR_DEFAULTS = {"tiny": 1e-3, "125m": 6e-4, "350m": 4e-4, "1b": 3e-4}
# (micro_bs, grad_accum):tokens/step 分别约 4k / 65k / 131k / 131k
BS_DEFAULTS = {"tiny": (8, 1), "125m": (16, 4), "350m": (8, 8), "1b": (2, 32)}


class PackedTokenDataset(Dataset):
    """预打包定长序列:memmap 读取,支持远大于内存的语料。"""

    def __init__(self, path: str, seq_len: int):
        self.arr = np.load(path, mmap_mode="r")
        self.seq_len = seq_len
        self.n = (len(self.arr) - 1) // seq_len
        if self.n <= 0:
            raise ValueError(f"语料太小:{len(self.arr)} tokens,不足一个 seq_len={seq_len} 的序列")

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        j = i * self.seq_len
        x = torch.from_numpy(self.arr[j : j + self.seq_len].astype(np.int64))
        return {"input_ids": x, "labels": x.clone()}


class SyntheticTokenDataset(Dataset):
    """随机 token,仅用于冒烟测试与吞吐基准(loss 不会收敛,属预期)。"""

    def __init__(self, vocab: int, seq_len: int, n: int = 20_000, seed: int = 1234):
        g = torch.Generator().manual_seed(seed)
        self.tokens = torch.randint(0, vocab, (n * seq_len,), generator=g, dtype=torch.int32)
        self.seq_len = seq_len
        self.n = n

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        x = self.tokens[i * self.seq_len : (i + 1) * self.seq_len].to(torch.int64)
        return {"input_ids": x, "labels": x.clone()}


class ThroughputCallback(TrainerCallback):
    """在日志里附加 tokens/s 与 MFU。"""

    def __init__(self, n_params: int, tokens_per_step: int, peak_tflops: float | None):
        self.n_params = n_params
        self.tokens_per_step = tokens_per_step
        self.peak_tflops = peak_tflops
        self.tokens = 0
        self.t0 = None

    def on_train_begin(self, args, state, control, **kwargs):
        self.t0 = time.perf_counter()
        self.tokens = 0

    def on_step_end(self, args, state, control, **kwargs):
        self.tokens += self.tokens_per_step

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None or self.t0 is None:
            return
        elapsed = max(time.perf_counter() - self.t0, 1e-9)
        tps = self.tokens / elapsed
        logs["tokens_per_sec"] = round(tps, 1)
        logs["billion_tokens_per_day"] = round(tps * 86400 / 1e9, 2)
        if self.peak_tflops:
            logs["mfu_pct"] = round(100 * 6 * self.n_params * tps / (self.peak_tflops * 1e12), 1)


def build_model(preset: str, vocab_size: int, seq_len: int, precision: str):
    p = PRESETS[preset]
    cfg = LlamaConfig(
        vocab_size=vocab_size,
        hidden_size=p["d"],
        intermediate_size=p["ffn"],
        num_hidden_layers=p["L"],
        num_attention_heads=p["heads"],
        num_key_value_heads=p["kv"],
        max_position_embeddings=max(seq_len, p["ctx"]),
        rms_norm_eps=1e-5,
        rope_theta=500_000.0,
        tie_word_embeddings=True,
        attention_bias=False,
        mlp_bias=False,
        use_cache=False,
    )
    model = LlamaForCausalLM(cfg)
    n = sum(x.numel() for x in model.parameters())
    print(f"模型参数量:{n / 1e9:.3f} B(preset={preset}, d={p['d']}, L={p['L']}, vocab={vocab_size}, tied embed)")
    if precision == "bf16":
        model = model.to(torch.bfloat16)
    return model, n


def latest_checkpoint(out_dir: str):
    cks = glob.glob(os.path.join(out_dir, "checkpoint-*"))
    cks = [c for c in cks if c.rsplit("-", 1)[-1].isdigit()]
    return max(cks, key=lambda s: int(s.rsplit("-", 1)[-1])) if cks else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", choices=list(PRESETS), default="1b")
    ap.add_argument("--tokenizer", default=None, help="HF tokenizer id(建议 Qwen/Qwen2.5-1.5B,zh+en 均优)")
    ap.add_argument("--data", default=None, help="tokenize_text.py 输出的 .npy 路径")
    ap.add_argument("--synthetic", action="store_true", help="随机 token(冒烟/基准)")
    ap.add_argument("--seq-len", type=int, default=None)
    ap.add_argument("--micro-bs", type=int, default=None)
    ap.add_argument("--accum", type=int, default=None)
    ap.add_argument("--precision", choices=["bf16", "fp32"], default="bf16")
    ap.add_argument("--optimizer", choices=["fused", "bnb8bit"], default="fused")
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--max-steps", type=int, default=-1)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--warmup-ratio", type=float, default=0.02)
    ap.add_argument("--save-steps", type=int, default=500)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--peak-tflops", type=float, default=None, help="verify_env.py 实测 BF16 TFLOPS,用于打印 MFU")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    p = PRESETS[args.preset]
    seq_len = args.seq_len or p["ctx"]
    micro_bs = args.micro_bs if args.micro_bs is not None else BS_DEFAULTS[args.preset][0]
    accum = args.accum if args.accum is not None else BS_DEFAULTS[args.preset][1]
    lr = args.lr or LR_DEFAULTS[args.preset]
    out_dir = args.output_dir or os.path.join(ROOT, "checkpoints", f"pretrain_{args.preset}")

    tok = None
    if args.tokenizer:
        tok = AutoTokenizer.from_pretrained(args.tokenizer)
        vocab = len(tok)
        print(f"tokenizer: {args.tokenizer}(vocab={vocab})")
    else:
        vocab = p["vocab"]

    if args.synthetic:
        ds = SyntheticTokenDataset(vocab, seq_len)
        if args.max_steps < 0:
            args.max_steps = 100
    elif args.data:
        ds = PackedTokenDataset(args.data, seq_len)
    else:
        raise SystemExit("需要 --data <tokens.npy> 或 --synthetic 之一")

    tokens_per_step = micro_bs * accum * seq_len
    print(f"tokens/step = {tokens_per_step:,}(micro_bs={micro_bs} x accum={accum} x seq={seq_len})")

    model, n_params = build_model(args.preset, vocab, seq_len, args.precision)

    targs = TrainingArguments(
        output_dir=out_dir,
        per_device_train_batch_size=micro_bs,
        gradient_accumulation_steps=accum,
        learning_rate=lr,
        lr_scheduler_type="cosine",
        warmup_ratio=args.warmup_ratio,
        weight_decay=0.1,
        adam_beta1=0.9,
        adam_beta2=0.95,
        max_grad_norm=1.0,
        bf16=True,
        tf32=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="adamw_torch_fused" if args.optimizer == "fused" else "adamw_bnb_8bit",
        max_steps=args.max_steps,
        num_train_epochs=args.epochs,
        logging_steps=10,
        save_steps=args.save_steps,
        save_total_limit=3,
        report_to=["tensorboard"],
        logging_dir=os.path.join(ROOT, "logs", f"pretrain_{args.preset}"),
        dataloader_num_workers=0,
        seed=args.seed,
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=ds,
        data_collator=default_data_collator,
        callbacks=[ThroughputCallback(n_params, tokens_per_step, args.peak_tflops)],
    )

    resume_ckpt = latest_checkpoint(out_dir) if args.resume else None
    if resume_ckpt:
        print(f"从 checkpoint 恢复:{resume_ckpt}")
    trainer.train(resume_from_checkpoint=resume_ckpt)

    trainer.save_model(out_dir)
    trainer.save_state()
    if tok is not None:
        tok.save_pretrained(out_dir)

    peak = torch.cuda.max_memory_allocated() / 2**30
    print(f"\n训练完成。峰值显存 {peak:.2f} GiB;模型与 tokenizer 已保存到 {out_dir}")


if __name__ == "__main__":
    main()
