# -*- coding: utf-8 -*-
"""v2 T1 benign-saturation family decomposition (arch three-hypothesis test)."""
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_infer import M6Inferencer  # noqa: E402
from m6_render import normalize_input, render, tokenize_windowed  # noqa: E402
from m6_train import derive_labels, load_config, rows_for_split  # noqa: E402

cfg = load_config(REPO / "configs/m6-v2.yaml")
rows = rows_for_split(cfg, "dev")
n = len(rows)
out = derive_labels(rows)
Y, mirror = out[0], out[3]
print(f"dev rows: {n}")

inf = M6Inferencer(str(REPO / "checkpoints" / "m6-v2"))
model = inf.model
model.eval()

prepared = []
for r in rows:
    inp = normalize_input(r)
    rendered, msg_spans, fmap = render(inf.tok, inp)
    tw = tokenize_windowed(inf.tok, rendered)
    prepared.append(tw["input_ids"])

X = np.zeros((n, 10240), dtype=np.float32)
pos = 0
from m6_feat_probe import forward_extract  # noqa: E402
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
        if pos % 2048 == 0:
            print(f"  extracted {pos}/{n}")

with torch.no_grad():
    o = model(torch.tensor(X).to(inf.device))
t1 = o["T1"].cpu().numpy()
np.save(REPO / "outputs/m6/_t1sat_logits.npy", t1)


def fam(r):
    m = r.get("meta") or {}
    ef = m.get("eval_family")
    if ef:
        return str(ef)
    src = r.get("source")
    if isinstance(src, dict):
        return str(src.get("family", "?"))
    return str(src or "?")[:28]


sat = (t1 > 16.6) & (Y[:, 0] == 0)
idx = np.where(sat)[0]
print(f"\nT1 benign saturators (T1-labeled neg, logit>16.6): {len(idx)}")
fams = Counter(fam(rows[int(i)]) for i in idx)
print("by family:", dict(fams.most_common(10)))

sup = Counter()
for i in idx:
    if bool(mirror[i]):
        sup["H2 mirror (calib-only)"] += 1
    else:
        sup["T1-labeled supervised neg"] += 1
print("supervision:", dict(sup))

# near-miss family (synth-jailbreak) overall posture on T1
nm = np.array([fam(r).startswith("synth-jailbreak") for r in rows])
if nm.any():
    l_nm = t1[nm]
    lab = Y[nm, 0]
    print(f"\nsynth-jailbreak-v1: n={int(nm.sum())} "
          f"T1-labeled={int((lab >= 0).sum())} "
          f"(neg {int((lab == 0).sum())}) unlabeled={int((lab < 0).sum())}")
    print(f"  T1 logit median={np.median(l_nm):.1f} "
          f">16.6: {int((l_nm > 16.6).sum())} "
          f">tau(35.76): {int((l_nm > 35.76).sum())}")

unlab_sat = (t1 > 16.6) & (Y[:, 0] < 0)
fu = Counter(fam(rows[int(i)]) for i in np.where(unlab_sat)[0])
print(f"\nT1-saturated UNLABELED rows (not in calib pool): "
      f"{int(unlab_sat.sum())}")
print("  by family:", dict(fu.most_common(8)))

if len(idx):
    ls = t1[idx]
    print(f"\nsaturated logit range {ls.min():.1f}..{ls.max():.1f} "
          f"median {np.median(ls):.1f}; tau_flag_logit=35.76")
    with open(REPO / "outputs/m6/_t1sat_ids.json", "w",
              encoding="utf-8") as f:
        import json
        json.dump([{"id": rows[int(i)]["id"], "family": fam(rows[int(i)]),
                    "mirror": bool(mirror[i]),
                    "logit": round(float(t1[i]), 1)} for i in idx], f,
                  ensure_ascii=False, indent=1)
    print("ids -> outputs/m6/_t1sat_ids.json")
