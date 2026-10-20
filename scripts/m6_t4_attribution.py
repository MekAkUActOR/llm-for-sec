# -*- coding: utf-8 -*-
"""T4 sub-head attribution analysis (task-10 deveng data supply).

Attributes T4 flags/FNs to the doc-head vs BIO-span sub-head using a
qa-eval per-item file + heldout/challenge source rows. Used to diagnose
the v1-2 challenge-FPR failure (both heads learned "contains-PII"; benign
documents with legitimate PII entities flag). Outputs:
  reports/m6/_t4_fp_ids.json   - FP id lists (heldout-neg, challenge)
  outputs/m6/_t4fp_infer.jsonl - own re-inference of FP sample
  outputs/m6/_t4pos_infer.jsonl- own re-inference of POS sample

Usage:
  python scripts/m6_t4_attribution.py --per-item <per-item.jsonl> \
      --head checkpoints/m6-v1-2 [--sample 120]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
TASKS = ["T1", "T2", "T3", "T4", "T5", "T6"]


def doc_of(resp):
    t4 = (resp.get("tasks") or {}).get("T4") or {}
    return float(((t4.get("detail") or {}).get("doc_score")) or 0.0)


def spans_of(resp):
    return (resp.get("tasks") or {}).get("T4", {}).get("spans") or []


def find_rows(ids):
    src = {}
    for f in (REPO / "data").rglob("*.jsonl"):
        if "heldout" not in str(f) and "challenge" not in str(f):
            continue
        try:
            for ln in f.read_text(encoding="utf-8-sig").splitlines():
                if not ln.strip():
                    continue
                r = json.loads(ln)
                if r.get("id") in ids and r["id"] not in src:
                    src[r["id"]] = r
        except Exception:
            pass
    return list(src.values())


def attribute(responses, thr=0.999):
    doc_only = span_only = both = 0
    for r in responses:
        d, s = doc_of(r) > thr, len(spans_of(r)) > 0
        if d and s:
            both += 1
        elif d:
            doc_only += 1
        elif s:
            span_only += 1
    return {"doc_only": doc_only, "span_only": span_only, "both": both,
            "neither": len(responses) - doc_only - span_only - both}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-item", required=True)
    ap.add_argument("--head", default="checkpoints/m6-v1-2")
    ap.add_argument("--sample", type=int, default=120)
    args = ap.parse_args()

    rows = [json.loads(l) for l in
            Path(args.per_item).read_text(encoding="utf-8-sig").splitlines()
            if l.strip()]

    # OOD suite flag composition
    ood = [r for r in rows if str(r.get("suite", "")).startswith("m6-ood")]
    fl = Counter(t for r in ood for t in TASKS if r["flag"].get(t))
    print(f"OOD suite n={len(ood)} flag-by-task: {dict(fl)}")

    # frozen-suite per-task recall
    from collections import defaultdict
    su = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        s = r.get("suite", "")
        if not s.startswith("frozen-"):
            continue
        for t in TASKS:
            if (r.get("gold") or {}).get(t) == "pos":
                su[s][t][1] += 1
                if r["flag"].get(t):
                    su[s][t][0] += 1
    print("frozen suites per-task recall:")
    for s in sorted(su):
        parts = [f"{t} {h}/{p}={h/p:.2f}" for t, (h, p) in su[s].items() if p]
        if parts:
            print(f"  {s}: {' | '.join(parts)}")

    # T4 FP + POS samples -> own re-inference for sub-head attribution
    fp_ids = [r["id"] for r in rows
              if (r.get("gold") or {}).get("T4") == "neg" and r["flag"].get("T4")]
    pos_ids = [r["id"] for r in rows
               if (r.get("gold") or {}).get("T4") == "pos"]
    (REPO / "reports/m6/_t4_fp_ids.json").write_text(
        json.dumps({"heldout_neg": fp_ids, "challenge": [
            r["id"] for r in rows if r.get("suite") == "m6-challenge"
            and r["flag"].get("T4")]}), encoding="utf-8")
    from m6_infer import M6Inferencer
    inf = M6Inferencer(
        backbone_ckpt="checkpoints/qwen3-06b-sec-m5a-dpo-r5",
        head_dir=REPO / args.head, device="cpu")
    for name, ids in (("FP", fp_ids[:args.sample]),
                      ("POS", pos_ids[:args.sample])):
        rs = find_rows(ids)
        if not rs:
            print(f"[{name}] no source rows found; skipping")
            continue
        tmp = REPO / f"reports/m6/_t4_{name.lower()}_rows.jsonl"
        tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                 for r in rs) + "\n", encoding="utf-8")
        out = REPO / f"outputs/m6/_t4{name.lower()}_infer.jsonl"
        inf.infer_file(str(tmp), str(out))
        res = [json.loads(l) for l in out.read_text(
            encoding="utf-8-sig").splitlines() if l.strip()]
        print(f"T4 {name} (n={len(res)}): {attribute(res)}")
        types = Counter(s.get("type") or "?" for r in res for s in spans_of(r))
        print(f"  span types: {sorted(types.items(), key=lambda x: -x[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
