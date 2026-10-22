# -*- coding: utf-8 -*-
"""Final subordination count (arch 20:2x): heldout gold join.

Runs the GATED v2.4-dt inferencer over qa's heldout eval plane
(in-heldout.jsonl, 14,144 rows) and joins labels-heldout.jsonl gold:
  (1) T4-POS rows whose only flag source is spans (doc-quiet, gate active)
      = exact G1 cost of subordination. Criterion: <=2% of TPs -> GO.
  (2) benign (T4-neg) rows with span-only flag = G2 exact gain share.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_infer import M6Inferencer  # noqa: E402

CKPT = REPO / "checkpoints/m6-v2-4dt"
RUN = REPO / "reports/m6/preds/run-v24-191512"

gold = {json.loads(l)["id"]: json.loads(l)
        for l in open(RUN / "labels-heldout.jsonl", encoding="utf-8-sig")
        if l.strip()}
records = [json.loads(l) for l in open(
    RUN / "in-heldout.jsonl", encoding="utf-8-sig") if l.strip()]
print(f"heldout eval rows: {len(records)} | gold rows: {len(gold)}")

inf = M6Inferencer(str(CKPT))
thr = inf.thresholds["T4"]["flag"]

n_pos = pos_spanonly = 0
n_neg = neg_spanonly = 0
pos_ex, neg_ex = [], []
for i in range(0, len(records), 64):
    for o in inf.infer_records(records[i:i + 64]):
        rid = o.get("id", o.get("request_id", "?"))
        g = gold.get(rid)
        if g is None:
            continue
        t4gold = (g.get("labels") or {}).get("T4")
        t4 = o["tasks"]["T4"]
        doc_fire = t4["detail"]["doc_score"] > thr
        so = (not doc_fire) and len(t4["spans"]) > 0
        if t4gold == 1:
            n_pos += 1
            if so:
                pos_spanonly += 1
                if len(pos_ex) < 5:
                    pos_ex.append({"id": rid, "spans": t4["spans"][:2],
                                   "doc": t4["detail"]["doc_score"]})
        elif t4gold == 0:
            n_neg += 1
            if so:
                neg_spanonly += 1
                if len(neg_ex) < 3:
                    neg_ex.append({"id": rid, "spans": t4["spans"][:2]})

pct = 100 * pos_spanonly / max(1, n_pos)
share = 100 * neg_spanonly / max(1, neg_spanonly and n_neg or 1)
print(f"\n(1) G1 cost: T4-pos={n_pos} span-only-flag={pos_spanonly} "
      f"({pct:.1f}% of TPs)")
print(f"    criterion: <=2% GO | >5% NO-GO")
for e in pos_ex:
    print("    ", json.dumps(e, ensure_ascii=False)[:220])
print(f"(2) G2 gain share: T4-neg={n_neg} span-only-flag={neg_spanonly} "
      f"({100*neg_spanonly/max(1,n_neg):.1f}% of benigns flagged via span-only)")
out = {"t4_pos": n_pos, "pos_span_only": pos_spanonly,
       "pos_span_only_pct": round(pct, 2),
       "t4_neg": n_neg, "neg_span_only": neg_spanonly,
       "neg_span_only_pct": round(100 * neg_spanonly / max(1, n_neg), 2),
       "pos_examples": pos_ex, "neg_examples": neg_ex}
(REPO / "reports/m6/span-subord-final-count.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("-> reports/m6/span-subord-final-count.json")
