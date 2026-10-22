# -*- coding: utf-8 -*-
"""tmp: H6 scale-gate stats from final data (label_counts per file + gate check)."""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(r"J:\Projects\llm_for_sec")
DM = REPO / "data" / "m6"
TASKS = ("T1", "T2", "T3", "T4", "T5", "T6")


def split_of(p: Path) -> str:
    if "dev-mirror" in p.parts:
        return "dev-mirror"
    if "heldout-shared" in p.parts:
        return "heldout-shared"
    if "challenge" in p.parts:
        return "challenge"
    if "ood" in p.parts:
        return "ood"
    return p.stem  # train / dev / heldout


files = sorted(f for f in DM.rglob("*.jsonl")
               if not any(part.startswith("_") for part in f.parts))
per_file = {}
agg = {}  # (split, task) -> Counter(pos/neg)
for f in files:
    sp = split_of(f)
    c = {}
    n = 0
    with open(f, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n += 1
            row = json.loads(line)
            labels = row.get("labels") or {}
            for t, g in labels.items():
                lab = g.get("label")
                d = c.setdefault(t, Counter())
                d["pos" if lab == "pos" else "neg"] += 1
    per_file[str(f.relative_to(DM)).replace("\\", "/")] = {
        "split": sp, "n": n,
        "label_counts": {t: {"pos": d["pos"], "neg": d["neg"]}
                         for t, d in sorted(c.items())}}
    for t, d in c.items():
        a = agg.setdefault((sp, t), Counter())
        a.update(d)

print(json.dumps({"files": per_file}, ensure_ascii=False, indent=1))
print("\n=== per split x task ===")
for (sp, t), d in sorted(agg.items()):
    print(f"{sp:15s} {t}: pos={d['pos']:6d} neg={d['neg']:6d}")

print("\n=== scale gates (manifest thresholds) ===")
gates = {
    "train pos>=2000/task": all(agg.get(("train", t), Counter())["pos"] >= 2000 for t in TASKS),
    "train neg>=2000/task": all(agg.get(("train", t), Counter())["neg"] >= 2000 for t in TASKS),
    "heldout pos>=200/task": all(agg.get(("heldout", t), Counter())["pos"] >= 200 for t in TASKS),
    "heldout neg>=1000/task": all(agg.get(("heldout", t), Counter())["neg"] >= 1000 for t in TASKS),
    "challenge>=1200": sum(d["pos"] + d["neg"] for (sp, t), d in agg.items()
                            if sp == "challenge") >= 1200,
    "ood>=500": sum(d["pos"] + d["neg"] for (sp, t), d in agg.items()
                      if sp == "ood") >= 500,
}
for k, ok in gates.items():
    print(f"{'PASS' if ok else 'FAIL'} {k}")
sys.exit(0 if all(gates.values()) else 1)
