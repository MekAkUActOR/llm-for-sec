# -*- coding: utf-8 -*-
"""Branch B (arch pre-authorized): v2 trunk + fresh heads + current data.

Dual hypothesis test: T1 recovery via linear-probe logic on the HEALTHY
v2 trunk (which kept T2/T3/T5/T6 separability; its T1 weakness was a head
trained on OLD data without the 26k T1 supervision). If a fresh T1 head
recovers on v2 features -> Composite-B = optimal artifact.
"""
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_feat_probe import load_backbone  # noqa: E402
from m6_train import load_config, rows_for_split, stage_a  # noqa: E402

CFG = REPO / "configs/m6-v2-3b.yaml"
ADAPTER = REPO / "checkpoints/m6-v2/adapter"
OUT = REPO / "checkpoints/m6-v2-3b"
OUT.mkdir(parents=True, exist_ok=True)
DEVICE = "cuda"

cfg = load_config(CFG)
backbone, tok = load_backbone(cfg["base"]["model_name_or_path"],
                              cfg["base"].get("dtype", "bf16"), DEVICE)
from peft import PeftModel  # noqa: E402
pmodel = PeftModel.from_pretrained(backbone, str(ADAPTER))
pmodel.eval()
print(f"[branchB] adapter loaded: {ADAPTER}")

base = pmodel.get_base_model()
for split in ("train", "dev"):
    rows = rows_for_split(cfg, split)
    print(f"[branchB] extracting {split}: {len(rows)} rows")
    stage_a(cfg, base, tok, rows, split, OUT, DEVICE)
print("[branchB] adapted cache complete ->", OUT / "feat_cache")
