# -*- coding: utf-8 -*-
"""Gate recall-risk check (arch 20:0x): on dev T4-POSITIVE rows, count rows
whose spans are ALL shorter than min_span_len (gate empties their span
channel) AND whose doc channel does not fire (no doc fallback) -> the only
rows where the gate could cost recall.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import numpy as np  # noqa: E402
from m6_infer import M6Inferencer  # noqa: E402
from m6_train import load_config, rows_for_split, TASKS  # noqa: E402

CKPT = REPO / "checkpoints/m6-v2-4dt"
cfg = load_config(REPO / "configs/m6-v2-4dt.yaml")
rows = {r["id"]: r for r in rows_for_split(cfg, "dev")}
D = np.load(CKPT / "feat_cache/feats_dev.npz", allow_pickle=True)
ids = [str(i) for i in D["ids"]]
Y = D["Y"]
COL = {t: j for j, t in enumerate(TASKS)}

pos_ids = [rid for k, rid in enumerate(ids) if Y[k, COL["T4"]] == 1]
records = [rows[rid] for rid in pos_ids]
print(f"T4-positive dev rows: {len(records)}")

inf = M6Inferencer(str(CKPT))
thr = inf.thresholds["T4"]["flag"]
at_risk = 0
examples = []
for i in range(0, len(records), 64):
    for o in inf.infer_records(records[i:i + 64]):
        t4 = o["tasks"]["T4"]
        spans = t4["spans"]
        doc_fire = t4["detail"]["doc_score"] > thr
        if spans and not doc_fire and all(
                s["end"] - s["start"] < inf.min_span_len for s in spans):
            at_risk += 1
            if len(examples) < 5:
                examples.append({"id": o.get("id", "?"),
                                 "spans": spans[:3],
                                 "doc_score": t4["detail"]["doc_score"]})
print(f"gate recall-risk rows (all spans < min_len AND doc quiet): "
      f"{at_risk}/{len(records)}")
for e in examples:
    print(" ", json.dumps(e, ensure_ascii=False)[:300])
