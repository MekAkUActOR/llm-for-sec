# -*- coding: utf-8 -*-
"""Cross-task FP separability analysis on v1 dev cache (CPU only).

Question: can a threshold separate T2 positives from cross-task attack rows
(rows pos for OTHER tasks, neg for T2)? Informs the Lead ruling on the QA-1
FPR denominator + v2 planning.
"""
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from m6_train import TASKS, M6Probe, derive_labels, load_config, rows_for_split

cfg = load_config(REPO / "configs" / "m6-v1.yaml")
rows = rows_for_split(cfg, "dev")
Y, t6c, neg_all, mirror, pii_idx, pii_spans = derive_labels(rows)
cache = np.load(REPO / "checkpoints/m6-v1/feat_cache/feats_dev.npz")
X = cache["pooled"] if "pooled" in cache.files else cache[list(cache.keys())[0]]

model = M6Probe(in_dim=X.shape[1])
ckpt = torch.load(REPO / "checkpoints/m6-v1/probe-heads.pt", map_location="cpu",
                  weights_only=True)
sd = ckpt["state"] if "state" in ckpt else ckpt
model.load_state_dict(sd)
model.eval()

with torch.no_grad():
    out = model(torch.tensor(X.astype(np.float32)))
scores = {t: torch.sigmoid(out[h]).numpy() for t, h in
          [("T1", "T1"), ("T2", "T2"), ("T3", "T3"), ("T4", "T4doc"),
           ("T5", "T5")]}
p6 = torch.softmax(out["T6"], dim=-1).numpy()[:, 0]
scores["T6"] = p6

print(f"dev rows: {len(rows)}  (from cache {X.shape})")
for t in TASKS:
    pos = scores[t][(Y[:, TASKS.index(t)] == 1)]
    benign_neg = scores[t][neg_all]           # all-task-negative (benign)
    cross_neg = scores[t][(Y[:, TASKS.index(t)] == 0) & ~neg_all]  # other-task attacks
    own_neg_max = benign_neg.max() if len(benign_neg) else 0
    cross_max = cross_neg.max() if len(cross_neg) else 0
    # separability: is there a tau with zero cross FP and decent recall?
    tau = max(own_neg_max, cross_max)
    rec_at_crosszero = float((pos > tau).mean()) if len(pos) else float("nan")
    print(f"\n[{t}] pos n={len(pos)} benign_neg n={len(benign_neg)} "
          f"cross_neg n={len(cross_neg)}")
    print(f"  pos scores:  min={pos.min():.4f} p05={np.quantile(pos, .05):.4f} "
          f"med={np.median(pos):.4f} max={pos.max():.4f}" if len(pos) else "  no pos")
    print(f"  benign neg:  max={own_neg_max:.4f}")
    print(f"  cross  neg:  max={cross_max:.4f} "
          f"n>0.99={int((cross_neg > 0.99).sum())} n>0.999={int((cross_neg > 0.999).sum())}"
          if len(cross_neg) else "  no cross neg")
    print(f"  recall @ zero-cross-FP tau={tau:.4f}: {rec_at_crosszero:.3f}")
    # how many cross rows sit ABOVE the current calibrated tau_flag?
    import json
    calib = json.loads((REPO / "checkpoints/m6-v1/calib.json").read_text(
        encoding="utf-8-sig"))
    tf = calib["thresholds"][t]["flag"]
    print(f"  calibrated tau_flag={tf:.4f} -> cross FP={int((cross_neg > tf).sum())}"
          if len(cross_neg) else "")
