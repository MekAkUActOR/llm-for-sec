# -*- coding: utf-8 -*-
"""v2.1 wave loader verification (CPU-only)."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_train import derive_labels, load_config, rows_for_split  # noqa: E402

cfg = load_config(REPO / "configs/m6-v2-2.yaml")
for split in ("train", "dev"):
    rows = rows_for_split(cfg, split)
    out = derive_labels(rows)
    Y, t6c, neg_all, mirror = out[0], out[1], out[2], out[3]
    print(f"[{split}] rows={len(rows)}")
    for j, t in enumerate(["T1", "T2", "T3", "T4", "T5", "T6"]):
        lab = int((Y[:, j] >= 0).sum())
        pos = int((Y[:, j] == 1).sum())
        print(f"  {t}: labeled={lab} pos={pos} neg={lab-pos}")
    print(f"  neg_all={int(neg_all.sum())} mirror={int(mirror.sum())}")
