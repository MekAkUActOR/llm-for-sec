# -*- coding: utf-8 -*-
"""G4 branch-2 discriminator: is_ood trigger rates on the OOD suite,
v1-3 vs v2 runpoints (arch decision tree step 2)."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_infer import M6Inferencer  # noqa: E402

rows = [json.loads(l) for l in open(
    REPO / "data/m6/ood/all.jsonl", encoding="utf-8-sig") if l.strip()]
print(f"ood suite rows: {len(rows)}")

for name in ("m6-v1-3", "m6-v2", "m6-v2-4", "_tmp_v2plane2"):
    inf = M6Inferencer(str(REPO / "checkpoints" / name))
    outs = inf.infer_records(rows)
    n_ood = sum(1 for o in outs if o["ood"]["is_ood"])
    n_abstain = sum(1 for o in outs if o["abstain"])
    d = [o["ood"]["score"] for o in outs]
    import numpy as np
    d = np.array(d)
    tau = inf.tau_ood
    print(f"\n[{name}] is_ood={n_ood}/{len(rows)} ({100*n_ood/len(rows):.1f}%) "
          f"abstain={n_abstain} tau_ood={tau:.1f}")
    print(f"  dist: median={np.median(d):.1f} q95={np.quantile(d,0.95):.1f} "
          f"max={d.max():.1f} | over-tau: {int((d > tau).sum())}")
