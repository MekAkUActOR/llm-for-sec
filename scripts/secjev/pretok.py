# -*- coding: utf-8 -*-
"""sec-jev 一次性预分词：decisions.jsonl → tokenized.pt 缓存（多进程 Jinja 渲染+分词）。

动机：apply_chat_template 的 Jinja 渲染 ~50-100ms/行，训练在线分词 10s+/步；
缓存后训练启动即跑（~0.3s/步）。缓存含 (ids, labels) 全量，种子固定可复现。
"""
import json
from multiprocessing import Pool
from pathlib import Path

import torch
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "secjev" / "decisions.jsonl"
DST = ROOT / "data" / "secjev" / "tokenized.pt"
BASE = ROOT / "checkpoints" / "soup-needlefix-a050"
ROLE = {"system": "system", "human": "user", "gpt": "assistant"}

_tok = None


def _init():
    global _tok
    _tok = AutoTokenizer.from_pretrained(BASE)


def _one(r):
    conv = [{"role": ROLE[m["from"]], "content": m["value"]} for m in r["conversations"]]
    text = _tok.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
    ids = _tok(text, add_special_tokens=False).input_ids
    d = r["decision"]
    return ids, [d["verdict"], d["action"], d["finding"], d["confidence"]]


def main():
    rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l.strip()]
    with Pool(8, initializer=_init) as p:
        out = p.map(_one, rows, chunksize=64)
    lens = sorted(len(x[0]) for x in out)
    torch.save(out, DST)
    print(f"PRETOK=OK rows={len(out)} p50={lens[len(lens)//2]} max={lens[-1]} -> {DST}")


if __name__ == "__main__":
    main()
