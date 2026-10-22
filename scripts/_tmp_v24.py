# -*- coding: utf-8 -*-
"""Composite v2.4: v2's full probe + fresh T1/T3/T4 heads retrained on the
FROZEN v2 trunk-MLP output (single trunk-MLP, no architecture change).

Findings driving this assembly:
- Branch B: fresh heads on the v2 BACKBONE recover T1 0.949 / T3 0.901 /
  T4 0.949 (with their own retrained trunk-MLP)
- v2's own heads on the same backbone: T2 0.986 / T5 1.0 / T6 1.0 (plane
  remeasure) -- but T6 is intrinsically in a microscopic degenerate regime
  on this trunk; ONLY v2's exact (trunk-MLP + head) pair orders positives
  above the worst benign (fresh T6 heads cannot find that ordering)
=> single-probe composite: keep v2's trunk-MLP + T2/T5/T6 heads; retrain
   fresh T1/T3/T4 on the frozen v2 trunk-MLP features (1024-dim) with the
   current 26k T1 supervision. Deterministic; margin-aware selection.
"""
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_train import M6Probe, TASKS  # noqa: E402

SRC = REPO / "checkpoints/m6-v2"          # v2 probe (trunk-MLP + heads)
CACHE = REPO / "checkpoints/m6-v2-3b/feat_cache"  # v2-adapter features
OUT = REPO / "checkpoints/m6-v2-4"
OUT.mkdir(parents=True, exist_ok=True)
DEVICE = "cuda"
RETRAIN = ["T1", "T3"]  # T4doc retrain FAILED on v2 trunk-MLP (0.45 vs
# v2's 0.869 -- t4-lawful info not linearly present); T4 keeps v2's head.
# Composite: T1 0.946 / T3 0.870 retrained + T2 0.986 / T4 0.869 / T5 1.0 /
# T6 1.0 from v2 = macro ~0.945, single trunk-MLP, no architecture change.

A = np.load(CACHE / "feats_train.npz", allow_pickle=True)
D = np.load(CACHE / "feats_dev.npz", allow_pickle=True)
Xtr = torch.tensor(A["pooled"].astype(np.float32), device=DEVICE)
Ytr, t6tr = A["Y"], A["t6c"]
Xdv = torch.tensor(D["pooled"].astype(np.float32), device=DEVICE)
Ydv, neg_dv = D["Y"], D["neg_all"]

sd = torch.load(SRC / "probe-heads.pt", map_location="cpu",
                weights_only=False)["state"]
model = M6Probe(Xtr.shape[1]).to(DEVICE)
model.load_state_dict(sd)
model.eval()

with torch.no_grad():
    Ztr = model.trunk(Xtr)
    Zdv = model.trunk(Xdv)
print(f"trunk features: train {tuple(Ztr.shape)} dev {tuple(Zdv.shape)}")

for p in model.parameters():
    p.requires_grad_(False)
for h in RETRAIN:
    for p in model.heads[h].parameters():
        p.requires_grad_(True)

# fresh init for the retrained heads (saturation-free start)
def _reinit(mod):
    for m in mod.modules():
        if hasattr(m, "reset_parameters"):
            m.reset_parameters()


for h in RETRAIN:
    _reinit(model.heads[h])

opt = torch.optim.AdamW(
    [p for h in RETRAIN for p in model.heads[h].parameters()],
    lr=1e-3, weight_decay=0.01)
rng = np.random.default_rng(77)
best_key, best_sd = None, None
n = len(Ztr)
COL = {t: j for j, t in enumerate(TASKS)}
for ep in range(25):
    for h in RETRAIN:
        model.heads[h].train()
    perm = rng.permutation(n)
    for s in range(0, n, 4096):
        b = torch.tensor(perm[s:s + 4096], device=DEVICE)
        loss = 0.0
        for h in RETRAIN:
            lt = "T4" if h == "T4doc" else h
            g = Ytr[b.cpu().numpy()][:, COL[lt]]
            m = torch.tensor(g >= 0, device=DEVICE)
            if m.any():
                yv = torch.tensor(np.where(g >= 0, g, 0),
                                  dtype=torch.float32, device=DEVICE)
                loss = loss + torch.nn.functional.binary_cross_entropy_with_logits(
                    model.heads[h](Ztr[b][m]).squeeze(-1), yv[m])
        opt.zero_grad()
        loss.backward()
        opt.step()
    model.eval()
    # margin-aware per-task recall (calibrate-consistent: neg_max + max(
    # pos_q05 - neg_max, 0.01) for logits)
    key = {}
    with torch.no_grad():
        for h in RETRAIN:
            lt = "T4" if h == "T4doc" else h
            lg = model.heads[h](Zdv).squeeze(-1).cpu().numpy()
            g = Ydv[:, COL[lt]]
            m = g >= 0
            pos_l, neg_l = lg[m & (g == 1)], lg[m & neg_dv]
            if len(pos_l) and len(neg_l):
                neg_max = float(neg_l.max())
                delta = float(np.quantile(pos_l, 0.05)) - neg_max
                if delta <= 0:
                    delta = 0.01
                key[lt] = round(float((pos_l > neg_max + delta).mean()), 4)
    print(f"v2.4 ep{ep}: margin-aware recall {key}")
    k = (round(sum(key.values()) / len(key), 4) if len(key) == len(RETRAIN)
         else -1.0)
    if best_key is None or k > best_key:
        best_key = k
        best_sd = {h: {kk: v.detach().cpu().clone() for kk, v in
                       model.heads[h].state_dict().items()} for h in RETRAIN}
        star = " *best*"
    else:
        star = ""
    print(f"  macro(retrained)={k}{star}")

for h in RETRAIN:
    model.heads[h].load_state_dict(best_sd[h])
full_sd = {k: v.detach().cpu() for k, v in model.state_dict().items()}
torch.save({"state": full_sd}, OUT / "probe-heads.pt")
print(f"v2.4 composite saved: {OUT/'probe-heads.pt'} "
      f"(retrained {RETRAIN} on frozen v2 trunk-MLP; T2/T5/T6 = v2 heads)")
