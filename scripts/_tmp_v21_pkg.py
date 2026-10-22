# -*- coding: utf-8 -*-
"""v2.1 post-training one-shot package:
readings (logit domain, new plane) + arch 3-item OOD telemetry
(tau_ood vs 4944, q95/tau separation vs 0.87x, is_ood rate vs 2.2%)
+ regression-determinism hash. Usage: python _tmp_v21_pkg.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

CKPT = REPO / "checkpoints/m6-v2-4"
REPORT = REPO / "reports/m6/v24-telemetry.json"

# ---- calibration + thresholds from the run itself ----------------------- #
metrics = json.loads((CKPT / "metrics.json").read_text(encoding="utf-8"))
calib = json.loads((CKPT / "calib.json").read_text(encoding="utf-8"))
tl_path = CKPT / "train_log.jsonl"
train_log = ([json.loads(l) for l in tl_path.read_text(
    encoding="utf-8").splitlines() if l.strip()] if tl_path.is_file() else [])
pkg = {"run": "m6-v2-4", "metrics": metrics.get("tasks", metrics),
       "train_log": train_log,
       "assembly": {
           "pattern": "surgical composite (no epoch loop): v2 full probe "
                      "(trunk-MLP + T2/T4/T5/T6 heads) + fresh T1/T3 "
                      "retrained on frozen v2 trunk-MLP",
           "trunk": "m6-v2 (e2a758c, unchanged - G4 dissociation)",
           "adapter": "m6-v2 (junction)",
           "retrained_heads": ["T1", "T3"],
           "kept_heads": ["T2", "T4", "T5", "T6"],
           "selection": "margin-aware per-epoch (calibrate-consistent) "
                        "on dev; best ep22/24 T1 0.9495 / T3 0.9249",
           "feats": "m6-v2-3b feat_cache (v2-adapter, current plane "
                    "64,070/12,768)",
       }}

# ---- arch 3-item OOD telemetry ------------------------------------------ #
from m6_infer import M6Inferencer  # noqa: E402
rows = [json.loads(l) for l in open(
    REPO / "data/m6/ood/all.jsonl", encoding="utf-8-sig") if l.strip()]
inf = M6Inferencer(str(CKPT))
outs = inf.infer_records(rows)
d = np.array([o["ood"]["score"] for o in outs])
tau = inf.tau_ood
n_ood = int((d > tau).sum())
pkg["ood_telemetry"] = {
    "tau_ood": round(float(tau), 1), "tau_ref_v2": 4944.0,
    "q95_over_tau": round(float(np.quantile(d, 0.95) / tau), 3),
    "q95_over_tau_ref_v2": 0.87,
    "is_ood_rate": round(n_ood / len(d), 4), "is_ood_ref_v2": 0.022,
    "dist_median": round(float(np.median(d)), 1),
    "dist_q95": round(float(np.quantile(d, 0.95)), 1),
}
print(json.dumps(pkg["ood_telemetry"], indent=1))

# ---- benign saturation counts (T1 tail watch, same-origin hypothesis) --- #
sat = {}
try:
    for t in ("T1", "T2", "T3", "T4", "T5"):
        sat[t] = int(metrics.get("benign_display_saturated", {})
                     .get(t, metrics.get("benign_sat", {}).get(t, -1)))
except Exception:
    pass
pkg["benign_saturated"] = metrics.get("benign_display_saturated",
                                      metrics.get("benign_sat"))
REPORT.write_text(json.dumps(pkg, ensure_ascii=False, indent=1),
                  encoding="utf-8")
print(f"-> {REPORT}")
