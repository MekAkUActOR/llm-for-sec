# -*- coding: utf-8 -*-
"""检查能否用 Liger/fused-linear-CE 或 flash-attn 压掉 4096 长序列的 logits 峰值。"""
import importlib

for m in ("liger_kernel", "flash_attn", "bitsandbytes"):
    try:
        mod = importlib.import_module(m)
        print(f"{m}: OK {getattr(mod, '__version__', '?')}")
    except Exception as e:  # noqa: BLE001
        print(f"{m}: 缺失 ({type(e).__name__})")

import torch  # noqa: E402

print("torch", torch.__version__, "cuda", torch.version.cuda)
try:
    print("flash_attn_available =", torch.backends.cuda.is_flash_attention_available())
except Exception:  # noqa: BLE001
    print("flash_attn_available = n/a")
print("sdpa_enabled =", torch.backends.cuda.flash_sdp_enabled(),
      "mem_efficient =", torch.backends.cuda.mem_efficient_sdp_enabled())

from transformers import AutoConfig  # noqa: E402

c = AutoConfig.from_pretrained(r"J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m2-calib")
print("vocab", c.vocab_size, "layers", c.num_hidden_layers, "hidden", c.hidden_size,
      "max_pos", getattr(c, "max_position_embeddings", "?"),
      "attn_impl", getattr(c, "_attn_implementation", None))

# Liger 需要 trainer flag；LLaMA-Factory 的开关名
try:
    import inspect

    from llamafactory.hparams import FinetuningArguments  # noqa: E402

    ks = [k for k in inspect.signature(FinetuningArguments.__init__).parameters
          if "liger" in k.lower()]
    print("LF FinetuningArguments 里 liger 相关开关:", ks)
except Exception as e:  # noqa: BLE001
    print("LF 开关探测失败:", type(e).__name__, e)
