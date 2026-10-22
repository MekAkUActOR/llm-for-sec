# -*- coding: utf-8 -*-
"""T4 G2/G3 pre-assembly decomposition (arch 19:5x): FP flag-source split.

For every dev-plane benign row that T4 flags, classify the flag source:
doc-driven (doc band fires, no spans) / span-driven (spans nonempty, doc
band quiet) / both. Span channel is trunk-independent (token path) -- if
FPs are span-driven, trunkB's doc upgrade cannot move G2/G3 and the
architectural lever is span-extractor contextualization instead.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_infer import M6Inferencer  # noqa: E402
from m6_train import load_config, rows_for_split, TASKS  # noqa: E402

CKPT = REPO / "checkpoints/m6-v2-4"
CFG = REPO / "configs/m6-v2-4.yaml"

cfg = load_config(CFG)
rows = {r["id"]: r for r in rows_for_split(cfg, "dev")}
D = np_load = None
import numpy as np  # noqa: E402
D = np.load(CKPT / "feat_cache/feats_dev.npz", allow_pickle=True)
ids = [str(i) for i in D["ids"]]
Y, neg_all = D["Y"], D["neg_all"]
COL = {t: j for j, t in enumerate(TASKS)}

benign = set()
for k, rid in enumerate(ids):
    if Y[k, COL["T4"]] == 0 or neg_all[k]:
        benign.add(rid)
print(f"dev benign pool (T4-neg OR neg_all): {len(benign)} rows")

inf = M6Inferencer(str(CKPT))
thr_t4 = inf.thresholds["T4"]
records = [rows[rid] for rid in ids if rid in benign]
print(f"inferring {len(records)} rows ...")

doc_only = span_only = both = 0
span_fp_examples = []
for i in range(0, len(records), 64):
    outs = inf.infer_records(records[i:i + 64])
    for o in outs:
        t4 = o["tasks"]["T4"]
        if not t4["flag"]:
            continue
        doc_fire = t4["detail"]["doc_score"] > thr_t4["flag"]
        span_fire = len(t4["spans"]) > 0
        if doc_fire and span_fire:
            both += 1
        elif doc_fire:
            doc_only += 1
        else:
            span_only += 1
            if len(span_fp_examples) < 5:
                span_fp_examples.append(
                    {"id": o.get("id", o.get("request_id", "?")),
                     "doc_score": t4["detail"]["doc_score"],
                     "spans": t4["spans"][:3]})

tot = doc_only + span_only + both
print(f"\nT4 flagged benign rows: {tot}")
print(f"  doc-only : {doc_only} ({100*doc_only/max(1,tot):.1f}%)")
print(f"  span-only: {span_only} ({100*span_only/max(1,tot):.1f}%)")
print(f"  both     : {both} ({100*both/max(1,tot):.1f}%)")
if span_fp_examples:
    print("span-only examples:")
    for e in span_fp_examples:
        print(" ", json.dumps(e, ensure_ascii=False)[:300])
out = {"flagged_benign": tot, "doc_only": doc_only,
       "span_only": span_only, "both": both,
       "span_only_examples": span_fp_examples}
(REPO / "reports/m6/t4-fp-source-decomposition.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("-> reports/m6/t4-fp-source-decomposition.json")
