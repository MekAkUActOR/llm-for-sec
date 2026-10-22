# -*- coding: utf-8 -*-
"""Span-subordination counts (arch 20:0x order, data-before-ruling).

Count 1: T4-POSITIVE rows whose ONLY T4 flag source is the span channel
(doc-quiet + >=min_len spans nonempty, gate active) -- the empirical risk
of subordinating the span flag to the doc channel.
  planes: dev (cache labels, exact) / challenge (m6-sample labels, exact)
          / heldout T4-relevant suites (no six-task gold: incidence only)
Count 2: OOD-suite rows T4-flagged via span-only (subordination would
un-flag these; OOD-bypass semantic change) -> G4 interaction analysis.
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


def span_only(o, thr):
    t4 = o["tasks"]["T4"]
    doc_fire = t4["detail"]["doc_score"] > thr
    return (not doc_fire) and len(t4["spans"]) > 0


def run(name, records, t4_pos_ids=None):
    inf = run.inf
    thr = inf.thresholds["T4"]["flag"]
    n_pos = n_spanonly_pos = n_spanonly_any = 0
    ex = []
    for i in range(0, len(records), 64):
        for o in inf.infer_records(records[i:i + 64]):
            so = span_only(o, thr)
            if so:
                n_spanonly_any += 1
                if len(ex) < 3:
                    ex.append({"id": o.get("id", o.get("request_id", "?")),
                               "spans": o["tasks"]["T4"]["spans"][:2]})
            if t4_pos_ids is not None:
                rid = o.get("id", o.get("request_id", "?"))
                if rid in t4_pos_ids:
                    n_pos += 1
                    if so:
                        n_spanonly_pos += 1
    print(f"[{name}] rows={len(records)} T4pos={n_pos} "
          f"span-only-flags(any)={n_spanonly_any} "
          f"span-only-among-T4pos={n_spanonly_pos}")
    for e in ex:
        print("   ", json.dumps(e, ensure_ascii=False)[:200])
    return {"rows": len(records), "t4_pos": n_pos,
            "span_only_any": n_spanonly_any,
            "span_only_among_t4pos": n_spanonly_pos, "examples": ex}


cfg = load_config(REPO / "configs/m6-v2-4dt.yaml")
run.inf = M6Inferencer(str(CKPT))
out = {}

# ---- dev (exact labels from cache) ----
rows = {r["id"]: r for r in rows_for_split(cfg, "dev")}
D = np.load(CKPT / "feat_cache/feats_dev.npz", allow_pickle=True)
ids = [str(i) for i in D["ids"]]
Y = D["Y"]
COL = {t: j for j, t in enumerate(TASKS)}
pos_ids = {rid for k, rid in enumerate(ids) if Y[k, COL["T4"]] == 1}
out["dev"] = run("dev", [rows[r] for r in ids if r in rows], pos_ids)

# ---- challenge (m6-sample labels) ----
ch = [json.loads(l) for l in open(
    REPO / "data/m6/challenge/all.jsonl", encoding="utf-8-sig") if l.strip()]
ch_pos = {r["id"] for r in ch
          if (r.get("labels") or {}).get("T4") == 1}
out["challenge"] = run("challenge", ch, ch_pos)

# ---- heldout T4-relevant suites (incidence; no six-task gold) ----
for key, p in (("ho-privacy", "data/heldout/v0.2.3/privacy.jsonl"),
               ("ho-toolout", "data/heldout/v0.4-toolout/tool_output.jsonl"),
               ("ho-toolout-reg",
                "data/heldout/v0.5-toolout-reg/toolout_primary.jsonl"),
               ("ho-document", "data/heldout/v0.6-document/document.jsonl")):
    recs = [json.loads(l) for l in open(
        REPO / p, encoding="utf-8-sig") if l.strip()]
    # normalize m5-era rows to m6 input shape the inferencer accepts
    for r in recs:
        r.setdefault("id", r.get("id", r.get("request_id", key)))
        if "input" not in r:
            r["input"] = {"text": r.get("query", "")}
    out[key] = run(key, recs)

# ---- count 2: OOD suite ----
ood = [json.loads(l) for l in open(
    REPO / "data/m6/ood/all.jsonl", encoding="utf-8-sig") if l.strip()]
out["ood_suite"] = run("ood_suite", ood)

(REPO / "reports/m6/span-subordination-counts.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("-> reports/m6/span-subordination-counts.json")
