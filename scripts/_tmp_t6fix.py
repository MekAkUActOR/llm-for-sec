# -*- coding: utf-8 -*-
"""T6 surgical fix for the branch-B artifact (saturation-preventing retrain).

The fresh T6 head overfits into a saturated regime (benign P0 -> 1.0 in
fp32, lp ceiling): the guard's boundary metric can't see it, but ANY
positive margin makes tau unreachable -> final calibrate recall 0.0.

Fix: freeze everything except the T6 head; retrain fresh at LOW lr with
per-epoch selection on the CALIBRATE-CONSISTENT metric (recall at the
actual calibrate-formula tau, margin included). Then the artifact is
re-calibrated via --recalibrate.
"""
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_train import M6Probe  # noqa: E402

CKPT = REPO / "checkpoints/m6-v2-3b"
CACHE = CKPT / "feat_cache"
DEVICE = "cuda"

A = np.load(CACHE / "feats_train.npz", allow_pickle=True)
D = np.load(CACHE / "feats_dev.npz", allow_pickle=True)
Xtr = torch.tensor(A["pooled"].astype(np.float32), device=DEVICE)
t6tr = A["t6c"]
Xdv = torch.tensor(D["pooled"].astype(np.float32), device=DEVICE)
t6dv, neg_dv = D["t6c"], D["neg_all"]

sd = torch.load(CKPT / "probe-heads.pt", map_location="cpu",
                weights_only=False)["state"]
model = M6Probe(Xtr.shape[1]).to(DEVICE)
model.load_state_dict(sd)
model.eval()

for p in model.parameters():
    p.requires_grad_(False)
for p in model.heads["T6"].parameters():
    p.requires_grad_(True)

lab = t6tr >= 0
X6, y6 = Xtr[torch.tensor(lab)], torch.tensor(
    t6tr[lab].astype(np.int64), device=DEVICE)
m6d = t6dv >= 0
pos_mask = m6d & (t6dv == 1)
neg_mask = m6d & neg_dv

opt6 = torch.optim.AdamW(model.heads["T6"].parameters(), lr=1e-4,
                         weight_decay=0.01)
rng = np.random.default_rng(321)
best_r, best_sd = -1.0, None
n = len(X6)
for ep in range(12):
    model.heads["T6"].train()
    perm = rng.permutation(n)
    for s in range(0, n, 4096):
        b = torch.tensor(perm[s:s + 4096], device=DEVICE)
        loss = torch.nn.functional.cross_entropy(
            model(X6[b])["T6"], y6[b])
        opt6.zero_grad()
        loss.backward()
        opt6.step()
    model.eval()
    with torch.no_grad():
        o = model(Xdv)["T6"]
    lp = torch.log_softmax(o.double(), dim=-1)[:, 0].cpu().numpy()
    neg_max = float(lp[neg_mask].max())
    pos_l = lp[pos_mask]
    # calibrate-formula tau (margin included) + recall at it
    delta = float(np.quantile(pos_l, 0.05)) - neg_max
    if delta <= 0:
        delta = 0.001
    tau = neg_max + delta
    r = round(float((pos_l > tau).mean()), 4)
    ceil = neg_max > -1e-3  # saturated-benign regime
    print(f"T6fix ep{ep}: neg_max_lp={neg_max:.3e} tau={tau:.3e} "
          f"recall@tau={r} ceiling_regime={ceil}")
    if not ceil and r > best_r:
        best_r, best_sd = r, {k: v.detach().cpu().clone() for k, v in
                              model.heads["T6"].state_dict().items()}
    if ep >= 3 and best_sd is not None:
        break  # healthy head found; stop early (anti-overfit)

if best_sd is None:
    print("NO healthy epoch found (all ceiling-regime)")
    sys.exit(1)
model.heads["T6"].load_state_dict(best_sd)
full_sd = {k: v.detach().cpu() for k, v in model.state_dict().items()}
torch.save({"state": full_sd}, CKPT / "probe-heads.pt")
print(f"T6 surgical fix saved (best recall@calibrate-tau={best_r})")
