# -*- coding: utf-8 -*-
"""v2 checkpoint re-measured on the NEW dev plane (arch plane-consistency
suggestion): produces plane-consistent guard-baseline readings for v2.1.

Loads v2 heads + LoRA adapter, extracts the NEW dev (12,468 rows) through
the adapted backbone, runs the logit-domain calibrate() machinery, prints
per-task zero-FP recalls. Official v2 calib (old plane) stays untouched.
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_infer import M6Inferencer  # noqa: E402
from m6_render import normalize_input, render, tokenize_windowed  # noqa: E402
from m6_train import (calibrate, derive_labels, load_config,  # noqa: E402
                      rows_for_split)

cfg = load_config(REPO / sys.argv[1] if len(sys.argv) > 1
                  else "configs/m6-v2-1.yaml")
CKPT_DIR = sys.argv[2] if len(sys.argv) > 2 else "checkpoints/m6-v2"
cfgp = sys.argv[1] if len(sys.argv) > 1 else "configs/m6-v2-1.yaml"
print(f"# plane remeasure: {CKPT_DIR} on {cfgp} data plane")
rows = rows_for_split(cfg, "dev")
n = len(rows)
out = derive_labels(rows)
Y, t6c, neg_all, mirror = out[0], out[1], out[2], out[3]
print(f"new-plane dev rows: {n}")

inf = M6Inferencer(str(REPO / CKPT_DIR))
model = inf.model
model.eval()

prepared = []
for r in rows:
    inp = normalize_input(r)
    rendered, msg_spans, fmap = render(inf.tok, inp)
    tw = tokenize_windowed(inf.tok, rendered)
    prepared.append(tw["input_ids"])

from m6_feat_probe import forward_extract  # noqa: E402

X = np.zeros((n, 10240), dtype=np.float32)
pos = 0
with torch.no_grad():
    while pos < n:
        chunk = list(range(pos, min(pos + 16, n)))
        mx = max(len(prepared[i]) for i in chunk)
        ids = torch.full((len(chunk), mx), inf.pad_id, dtype=torch.long)
        attn = torch.zeros((len(chunk), mx), dtype=torch.long)
        for k, i in enumerate(chunk):
            s = prepared[i]
            ids[k, :len(s)] = torch.tensor(s, dtype=torch.long)
            attn[k, :len(s)] = 1
        f, _ = forward_extract(
            inf.backbone, ids.to(inf.device), attn.to(inf.device),
            [4, 12, 20, 24, 28], "mean+last", [12, 28])
        X[chunk] = f.numpy()
        pos += len(chunk)
        if pos % 4096 == 0:
            print(f"  dev extracted {pos}/{n}")

D = {"pooled": X, "Y": Y.astype(np.float32), "t6c": t6c,
     "neg_all": neg_all, "mirror": mirror}
# A (train subsample for Mahalanobis centers): reuse the v2 finalize
# convention -- capped adapted-train subsample; centers are not part of the
# guard baseline readings but calibrate() requires them.
rows_tr = rows_for_split(cfg, "train")
rng = np.random.default_rng(42)
sel = rng.choice(len(rows_tr), size=min(1500, len(rows_tr)),
                 replace=False).tolist()
prep_tr = []
for i in sel:
    inp = normalize_input(rows_tr[int(i)])
    rendered, msg_spans, fmap = render(inf.tok, inp)
    prep_tr.append(tokenize_windowed(inf.tok, rendered)["input_ids"])
out_tr = derive_labels(rows_tr)
Ytr, t6tr, negtr, mirtr = out_tr[0], out_tr[1], out_tr[2], out_tr[3]
Xtr = np.zeros((len(sel), 10240), dtype=np.float32)
pos = 0
with torch.no_grad():
    while pos < len(sel):
        chunk = list(range(pos, min(pos + 16, len(sel))))
        mx = max(len(prep_tr[i]) for i in chunk)
        ids = torch.full((len(chunk), mx), inf.pad_id, dtype=torch.long)
        attn = torch.zeros((len(chunk), mx), dtype=torch.long)
        for k, i in enumerate(chunk):
            s = prep_tr[i]
            ids[k, :len(s)] = torch.tensor(s, dtype=torch.long)
            attn[k, :len(s)] = 1
        f, _ = forward_extract(
            inf.backbone, ids.to(inf.device), attn.to(inf.device),
            [4, 12, 20, 24, 28], "mean+last", [12, 28])
        Xtr[chunk] = f.numpy()
        pos += len(chunk)
A = {"pooled": Xtr, "Y": Ytr[sel].astype(np.float32), "t6c": t6tr[sel],
     "neg_all": negtr[sel], "mirror": mirtr[sel]}

tmp_out = REPO / "outputs/m6/_v2_newplane"
tmp_out.mkdir(parents=True, exist_ok=True)
centers, tau_ood, thresholds, curves, scores, ddev = calibrate(
    model, A, D, tmp_out, cfg)

# logit-space recalls (guard semantics, 18e02a4): fp32-sigmoid ties are
# measurement artifacts on saturated planes
with torch.no_grad():
    out_d = model(torch.tensor(X).to(inf.device))
lg = {t: out_d[t].cpu().numpy() for t in ("T1", "T2", "T3", "T4doc", "T5")}
readings = {}
for lt, ht in [("T1", "T1"), ("T2", "T2"), ("T3", "T3"), ("T4", "T4doc"),
               ("T5", "T5")]:
    s = lg[ht]
    g = D["Y"][:, ["T1", "T2", "T3", "T4", "T5", "T6"].index(lt)]
    m = g >= 0
    pos_s, neg_s = s[m & (g == 1)], s[m & neg_all]
    r = round(float((pos_s > float(neg_s.max())).mean()), 4) if len(pos_s) and len(neg_s) else None
    readings[lt] = r
    print(f"{lt}: recall@zeroFP(new plane, logit domain)={r} "
          f"FP=0/{len(neg_s)} tau_logit={thresholds[lt].get('flag_logit')}")
# T6 log-P domain (calibrate semantics)
p6 = torch.softmax(out_d["T6"].double(), dim=-1)[:, 0].cpu().numpy()
m = D["Y"][:, 5] >= 0
pos_s, neg_s = p6[m & (D["Y"][:, 5] == 1)], p6[m & neg_all]
r6 = round(float((np.log(pos_s) > float(np.log(neg_s).max())).mean()), 4) \
    if len(pos_s) and len(neg_s) else None
readings["T6"] = r6
print(f"T6: recall@zeroFP(new plane, log-P)={r6}")
print("\nplane-consistent guard baseline:",
      json.dumps(readings))
json.dump({"readings": readings, "thresholds": thresholds},
          open(tmp_out / "newplane_baseline.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"-> {tmp_out / 'newplane_baseline.json'}")
