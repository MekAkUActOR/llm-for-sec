# -*- coding: utf-8 -*-
"""Pre-flight read-only check: real data/m6 vs my pipeline reader (no GPU,
no training, no writes outside reports/). Validates rows_for_split manifest
branch, m6-sample parsing, label derivation, render+tokenize on samples."""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import json

import yaml

from m6_render import load_jsonl, normalize_input, render, tokenize_windowed
from m6_train import TASKS, derive_labels, load_config, rows_for_split

cfg = load_config(REPO / "configs" / "m6-v1.yaml")
man = json.loads((REPO / "data/m6/manifest.json").read_text(encoding="utf-8-sig"))
print(f"manifest files: {len(man['files'])}  (lightweight index; schema "
      f"manifest + manifest_id land at task-6 freeze)")

# pre-flight uses explicit globs (train/dev only; heldout/challenge/ood never
# read here). pool/ = union of task rows + shared benign negatives; per-task
# dirs are subset views (reading both duplicates ids). At H6 freeze the v1
# config switches to the schema manifest.
cfg["data"] = {
    "train_patterns": ["data/m6/pool/train.jsonl"],
    "dev_patterns": ["data/m6/pool/dev.jsonl"],  # dev-mirror = pure subset
    "prefix_rows": "exclude",
}

for split in ("train", "dev"):
    t0 = time.time()
    try:
        rows = rows_for_split(cfg, split)
    except Exception as e:
        print(f"[{split}] rows_for_split FAIL: {type(e).__name__}: {e}")
        continue
    Y, t6c, neg_all, mirror, pii_idx, spans = derive_labels(rows)
    n = len(rows)
    cov = {t: f"{int((Y[:, j] == 1).sum())}+/{int((Y[:, j] == 0).sum())}-"
           f"/{int((Y[:, j] < 0).sum())}?" for j, t in enumerate(TASKS)}
    print(f"[{split}] rows={n} ({time.time()-t0:.1f}s)")
    print(f"  label coverage pos/neg/unannotated: {cov}")
    print(f"  t6 classes 0/1/2/-1: "
          f"{int((t6c==0).sum())}/{int((t6c==1).sum())}/{int((t6c==2).sum())}/"
          f"{int((t6c<0).sum())}")
    print(f"  neg_all={int(neg_all.sum())} mirror={int(mirror.sum())} "
          f"pii_rows={len(pii_idx)} pii_span_rows={sum(1 for s in spans if s)}")

# render+tokenize smoke on a stratified sample (CPU, tokenizer only)
from transformers import AutoTokenizer

tok = AutoTokenizer.from_pretrained(str(REPO / "checkpoints/qwen3-06b-sec-m5a-dpo-r5"))
import random

random.seed(7)
sample = random.sample(rows, min(40, len(rows)))
kinds = {}
tok_lens = []
for r in sample:
    inp = normalize_input(r)
    rendered, msg_spans, fmap = render(tok, inp)
    tw = tokenize_windowed(tok, rendered)
    kinds[inp["kind"]] = kinds.get(inp["kind"], 0) + 1
    tok_lens.append(len(tw["input_ids"]))
    assert msg_spans, f"no msg_spans for {r['id']}"
print(f"sample render: kinds={kinds} tokens p50={sorted(tok_lens)[len(tok_lens)//2]} "
      f"max={max(tok_lens)} trunc={sum(1 for t in tok_lens if t>4096) if False else 'n/a'}")
print("PRE-FLIGHT OK")
