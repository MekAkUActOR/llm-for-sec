# -*- coding: utf-8 -*-
"""Branch A (arch ruling 18:4x): ADAPTED feature cache for the composite.

Extracts train/dev pooled + PII token features through the v2.2-ep1
adapted backbone (adapter from checkpoints/m6-v2-2/adapter) into
checkpoints/m6-v2-3a/feat_cache -- then the standard stage-A/B head-only
run (--reuse-cache) trains fresh heads on frozen adapted features.
Deterministic post-processing: no joint dynamics, fresh init (no
saturation trap), v1-x recipe.
"""
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_feat_probe import load_backbone  # noqa: E402
from m6_train import load_config, rows_for_split, stage_a  # noqa: E402

CFG = REPO / "configs/m6-v2-3a.yaml"
ADAPTER = REPO / "checkpoints/m6-v2-2/adapter"
OUT = REPO / "checkpoints/m6-v2-3a"
OUT.mkdir(parents=True, exist_ok=True)
DEVICE = "cuda"

cfg = load_config(CFG)
backbone, tok = load_backbone(cfg["base"]["model_name_or_path"],
                              cfg["base"].get("dtype", "bf16"), DEVICE)
from peft import PeftModel  # noqa: E402
pmodel = PeftModel.from_pretrained(backbone, str(ADAPTER))
pmodel.eval()
print(f"[branchA] adapter loaded: {ADAPTER}")

base = pmodel.get_base_model()
for split in ("train", "dev"):
    rows = rows_for_split(cfg, split)
    print(f"[branchA] extracting {split}: {len(rows)} rows")
    stage_a(cfg, base, tok, rows, split, OUT, DEVICE)
print("[branchA] adapted cache complete ->", OUT / "feat_cache")
