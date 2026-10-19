# -*- coding: utf-8 -*-
"""sec-jev 决策模型训练器（单文件，secjev-branch-brief §五）。

形态：Qwen3-0.6B 骨干（soup-needlefix-a050 起点）+ peft LoRA r16 α32 all-linear
     + 21 槽 fp32 决策头（4 组：verdict5/action5/finding8/conf3，自 lm_head 行初始化）。
损失：prompt 末 token 位置的 hidden → 四组并行 CE。
剂量：300 优化器步 × batch16 = 4,800 行（跨形态唯一直接可比量 = 优化器步数；
     行覆盖 22.2% 亚 epoch，登记为已知限，同 r6 剂量混淆家族）。
输出：checkpoints/secjev-0.6b-r1/（adapter + head + slots.json）
"""
import json
import math
import random
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model

ROOT = Path(__file__).resolve().parent.parent.parent
BASE = ROOT / "checkpoints" / "soup-needlefix-a050"
DATA = ROOT / "data" / "secjev" / "decisions.jsonl"
OUT = ROOT / "checkpoints" / "secjev-0.6b-r1"
STEPS, BATCH, LR = 300, 16, 5e-5
SEED = "secjev-20261020"

SLOTS = {
    "verdict": ["benign", "risk", "ambiguous", "malformed", "out-of-scope"],
    "action": ["comply", "refuse", "clarify", "deflect", "escalate"],
    "finding": ["insufficient-context", "harmful-intent", "dual-use", "credential-risk",
                 "policy-violation", "authorization-missing", "scope-exceeded", "no-finding"],
    "confidence": ["high", "medium", "low"],
}


class DecHead(nn.Module):
    """四组并行分类头，fp32；slot j 权重 = lm_head 锚 token 行（JEV-27B 配方）。"""

    def __init__(self, hidden, lm_head_weight, tok):
        super().__init__()
        self.groups = {}
        for g, names in SLOTS.items():
            lin = nn.Linear(hidden, len(names), bias=True, dtype=torch.float32)
            with torch.no_grad():
                for j, name in enumerate(names):
                    ids = tok.encode(name, add_special_tokens=False)
                    lin.weight[j] = lm_head_weight[ids[0]].detach().clone().float()
                lin.bias.zero_()
            self.groups[g] = lin
        self.add_module("verdict", self.groups["verdict"])
        self.add_module("action", self.groups["action"])
        self.add_module("finding", self.groups["finding"])
        self.add_module("confidence", self.groups["confidence"])

    def forward(self, h):  # h: (B, hidden) fp32
        return {g: lin(h) for g, lin in self.groups.items()}


class Rows(Dataset):
    """优先读 tokenized.pt 缓存（ids, 四组标签名）；无缓存回退在线分词（慢）。"""

    def __init__(self, rows, tok):
        self.rows, self.tok = rows, tok
        cache = ROOT / "data" / "secjev" / "tokenized.pt"
        self.cache = torch.load(cache) if cache.exists() else None
        if self.cache is not None:
            assert len(self.cache) == len(rows), "缓存行数与语料不符"
            print(f"tokenized cache HIT ({len(self.cache)} rows)")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        if self.cache is not None:
            ids, lab_names = self.cache[i]
            ids = torch.tensor(ids, dtype=torch.long)
            labs = {g: SLOTS[g].index(n) for g, n in zip(SLOTS, lab_names)}
            return ids, labs
        # 在线路径（勘误 v2：sharegpt {from,value} → {role,content}；v1 空模板教训）
        ROLE = {"system": "system", "user": "user", "human": "user",
                "gpt": "assistant", "assistant": "assistant"}
        conv = [{"role": ROLE[m["from"]], "content": m["value"]} for m in r["conversations"]]
        text = self.tok.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
        ids = self.tok(text, add_special_tokens=False, return_tensors="pt").input_ids[0]
        d = r["decision"]
        labs = {g: SLOTS[g].index(d[g]) for g in SLOTS}
        return ids, labs


def collate(batch, pad_id):
    ids, labs = zip(*batch)
    mx = max(x.numel() for x in ids)
    inp = torch.full((len(ids), mx), pad_id, dtype=torch.long)
    att = torch.zeros((len(ids), mx), dtype=torch.long)
    for i, x in enumerate(ids):
        inp[i, : x.numel()] = x
        att[i, : x.numel()] = 1
    last = att.sum(1) - 1
    return inp, att, last, {g: torch.tensor([l[g] for l in labs]) for g in SLOTS}


def main():
    t0 = time.time()
    rng = random.Random(SEED)
    torch.manual_seed(0)
    dev = "cuda:0"
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map=dev)
    lm_w = model.get_output_embeddings().weight.detach()
    hidden = model.config.hidden_size
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, target_modules="all-linear",
        task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    head = DecHead(hidden, lm_w, tok).to(dev)
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]
    rng.shuffle(rows)
    pad_id = tok.pad_token_id or tok.eos_token_id
    dl = DataLoader(Rows(rows, tok), batch_size=BATCH, shuffle=True,
                    collate_fn=lambda b: collate(b, pad_id), num_workers=0, drop_last=True)
    opt = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad] + list(head.parameters()),
        lr=LR, weight_decay=0.0)
    model.train()
    step, seen, losses = 0, 0, []
    log_every = 30
    import os
    max_steps = int(os.environ.get("SECJEV_STEPS", STEPS))
    dbg = os.environ.get("SECJEV_DEBUG")
    while step < max_steps:
        for inp, att, last, labs in dl:
            if step >= max_steps:
                break
            if dbg and step == 0:
                print(f"DBG batch 就绪 inp={tuple(inp.shape)} att={att.sum(1).tolist()[:4]}", flush=True)
            inp, att, last = inp.to(dev), att.to(dev), last.to(dev)
            if dbg and step == 0:
                print("DBG 已上 GPU", flush=True)
            out = model(input_ids=inp, attention_mask=att, output_hidden_states=True)
            if dbg and step == 0:
                print(f"DBG 前向完成 hidden={tuple(out.hidden_states[-1].shape)}", flush=True)
            h = out.hidden_states[-1][torch.arange(inp.size(0), device=dev), last].float()
            loss = sum(nn.functional.cross_entropy(head(h)[g], labs[g].to(dev)) for g in SLOTS)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            losses.append(loss.item())
            seen += inp.size(0)
            step += 1
            if step % log_every == 0:
                print(f"step {step}/{STEPS} loss {sum(losses[-log_every:])/log_every:.4f} "
                      f"rows {seen} elapsed {time.time()-t0:.0f}s", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUT / "adapter")
    torch.save(head.state_dict(), OUT / "head.pt")
    (OUT / "slots.json").write_text(json.dumps({
        "slots": SLOTS, "base": str(BASE), "steps": STEPS, "batch": BATCH, "lr": LR,
        "rows_total": len(rows), "rows_seen": seen, "seed": SEED,
        "final_loss": round(sum(losses[-30:]) / 30, 4),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"TRAIN-SECJEV=OK steps={step} rows={seen} final_loss={sum(losses[-30:])/30:.4f} "
          f"elapsed={time.time()-t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()
