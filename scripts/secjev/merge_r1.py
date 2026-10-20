# -*- coding: utf-8 -*-
"""sec-jev r1 合并导出：base(soup) + LoRA → 自包含模型 + 决策头 + 槽配置。

注意：决策头(head.pt)不可并入 safetensors 主干（peft 只合并 LoRA）——
发布包 = 合并后的完整模型目录 + head.pt + slots.json + render_eval.py 用法说明。
"""
import json
import shutil
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(r"J:\Projects\llm_for_sec")
CKPT = ROOT / "checkpoints" / "secjev-0.6b-r1"
OUT = ROOT / "checkpoints" / "secjev-0.6b-r1-merged"

cfg = json.loads((CKPT / "slots.json").read_text(encoding="utf-8"))
base = AutoModelForCausalLM.from_pretrained(cfg["base"], dtype=torch.bfloat16, device_map="cpu")
model = PeftModel.from_pretrained(base, CKPT / "adapter")
merged = model.merge_and_unload()
OUT.mkdir(parents=True, exist_ok=True)
merged.save_pretrained(OUT, safe_serialization=True)
tok = AutoTokenizer.from_pretrained(cfg["base"])
tok.save_pretrained(OUT)
# 决策头与槽配置随包
shutil.copy(CKPT / "head.pt", OUT / "head.pt")
shutil.copy(CKPT / "slots.json", OUT / "slots.json")
files = sorted(p.name for p in OUT.iterdir())
total = sum(p.stat().st_size for p in OUT.iterdir()) / 1e9
print(f"MERGE-SECJEV=OK files={files} total={total:.2f}GB -> {OUT}")
