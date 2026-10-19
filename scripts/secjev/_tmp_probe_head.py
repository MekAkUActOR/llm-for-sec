# -*- coding: utf-8 -*-
"""临时调试：探决策头各组 logits（用后即删）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

CKPT = Path(r"J:\Projects\llm_for_sec\checkpoints\secjev-0.6b-r1")
cfg = json.loads((CKPT / "slots.json").read_text(encoding="utf-8"))
tok = AutoTokenizer.from_pretrained(cfg["base"])
base = AutoModelForCausalLM.from_pretrained(cfg["base"], dtype=torch.bfloat16, device_map="cuda")
model = PeftModel.from_pretrained(base, CKPT / "adapter").eval()

import torch.nn as nn
head = nn.ModuleDict({g: nn.Linear(base.config.hidden_size, len(n), dtype=torch.float32)
                      for g, n in cfg["slots"].items()}).to("cuda")
sd = torch.load(CKPT / "head.pt", map_location="cuda")
head.load_state_dict(sd)
head.eval()
print("state_dict 键:", list(sd.keys()))
for g, lin in head.items():
    w = lin.weight
    print(f"{g}: weight norm/行 = {[round(float(x), 2) for x in w.norm(dim=1)]}  bias={[round(float(b),3) for b in lin.bias]}")

# 训练集里的一条 benign 行
rows = [json.loads(l) for l in Path(r"J:\Projects\llm_for_sec\data\secjev\decisions.jsonl").read_text(encoding="utf-8").splitlines()]
ben = next(r for r in rows if r["decision"]["action"] == "comply")
risk = next(r for r in rows if r["decision"]["action"] == "refuse")
for tag, r in [("benign行", ben), ("risk行", risk)]:
    text = tok.apply_chat_template(r["conversations"], tokenize=False, add_generation_prompt=True)
    ids = tok(text, add_special_tokens=False, return_tensors="pt").input_ids.to("cuda")
    with torch.no_grad():
        h = model(input_ids=ids, output_hidden_states=True).hidden_states[-1][0, -1].float()
    print(f"--- {tag} 标签={r['decision']} ---")
    for g, lin in head.items():
        lg = lin(h)
        sm = torch.softmax(lg, -1)
        top = sm.argsort(descending=True)[:2]
        print(f"  {g}: " + " ".join(f"{cfg['slots'][g][i]}={float(sm[i]):.3f}" for i in top))
