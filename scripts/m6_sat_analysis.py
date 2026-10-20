# -*- coding: utf-8 -*-
"""Saturated-benign decomposition per arch decision tree:
task-view positives vs pool vs dev-mirror, by eval_family/source family.
Exports sample rows for dataeng content review."""
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from m6_train import M6Probe, load_config, rows_for_split  # noqa: E402

cfg = load_config(REPO / "configs/m6-v1-2.yaml")
rows = rows_for_split(cfg, "dev")
z = np.load(REPO / "checkpoints/m6-v1-2/feat_cache/feats_dev.npz",
            allow_pickle=True)
X, neg, Y = z["pooled"], z["neg_all"], z["Y"]
TASK_LIST = ["T1", "T2", "T3", "T4", "T5", "T6"]

model = M6Probe(X.shape[1])
ckpt = torch.load(REPO / "checkpoints/m6-v1-2/probe-heads.pt",
                  map_location="cpu", weights_only=True)
model.load_state_dict(ckpt["state"] if "state" in ckpt else ckpt)
model.eval()
with torch.no_grad():
    out = model(torch.tensor(X.astype(np.float32)))

calib = json.loads((REPO / "checkpoints/m6-v1-2/calib.json").read_text(
    encoding="utf-8-sig"))

any_pos = (Y == 1).any(axis=1)          # row is a positive in SOME task view
mirror = z["mirror"].astype(bool)

def fam(r):
    m = r.get("meta") or {}
    ef = m.get("eval_family")
    if ef:
        return str(ef)
    src = r.get("source")
    if isinstance(src, dict):
        return str(src.get("family", "?"))
    return str(src or "?")[:28]

# cross-task head-saturation union (hard-benign subpopulation probe)
sat_union = np.zeros(len(rows), dtype=bool)
per_task = {}
for t in ("T1", "T2", "T3", "T4", "T5"):
    lg = out["T4doc" if t == "T4" else t].numpy()
    thr = calib["thresholds"][t]
    sl = thr.get("strong_logit")
    m_sat = neg & (lg > 16.6)
    m_strong = neg & (lg > sl) if sl is not None else np.zeros(len(rows), bool)
    sat_union |= m_sat
    per_task[t] = (m_sat, m_strong)

print("=== saturated benign rows: composition (arch decision tree) ===")
for t, (m_sat, m_strong) in per_task.items():
    n = int(m_sat.sum())
    print(f"\n[{t}] display-sat n={n} | >strong n={int(m_strong.sum())}")
    print(f"  task-view positive (pos in SOME task): "
          f"{int((m_sat & any_pos).sum())}")
    print(f"  all-task-negative rows: {int((m_sat & ~any_pos).sum())}")
    print(f"  mirror rows: {int((m_sat & mirror).sum())}")
    fams = {}
    for i in np.where(m_sat)[0]:
        fams[fam(rows[int(i)])] = fams.get(fam(rows[int(i)]), 0) + 1
    top = sorted(fams.items(), key=lambda x: -x[1])[:6]
    print(f"  top source families: {top}")

u = sat_union
print(f"\n=== union across heads: {int(u.sum())} unique benign rows saturate "
      f">=1 head ===")
print(f"  of which task-view positives: {int((u & any_pos).sum())}")
print(f"  of which ALL-task-negative (pure benign): {int((u & ~any_pos).sum())}")
print(f"  of which mirror: {int((u & mirror).sum())}")
pure = u & ~any_pos
fams = {}
for i in np.where(pure)[0]:
    fams[fam(rows[int(i)])] = fams.get(fam(rows[int(i)]), 0) + 1
print(f"  pure-benign source families: "
      f"{sorted(fams.items(), key=lambda x: -x[1])[:8]}")

# export samples for dataeng review: strongest T2 saturators among pure benign
exp = []
for t in ("T2", "T1", "T3", "T5"):
    lg = out["T4doc" if t == "T4" else t].numpy()
    cand = np.where(pure)[0]
    order = cand[np.argsort(-lg[cand])][:10]
    for i in order:
        r = rows[int(i)]
        inp = r.get("input") or {}
        txt = inp.get("text") or str(inp.get("messages") or "")[:110]
        exp.append({"task_head": t, "logit": round(float(lg[i]), 1),
                    "id": r["id"], "family": fam(r),
                    "labels": sorted((r.get("labels") or {}).keys()),
                    "text": txt[:110]})
outp = REPO / "reports/m6/saturated_benign_samples.jsonl"
outp.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in exp)
                + "\n", encoding="utf-8")
print(f"\nsamples exported: {outp} ({len(exp)} rows)")
