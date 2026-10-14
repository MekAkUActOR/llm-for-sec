# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog M: is `loss` consistent with `rewards/accuracies` at sample
resolution, and what does the falling loss actually measure?

Derivation.  With pref_loss=sigmoid and label_smoothing=0, the per-sample loss is
    l_i = -log sigmoid(m_i),  m_i = rewards/chosen_i - rewards/rejected_i.
Every sample with m_i <= 0 contributes >= log 2 = 0.693147.  The logged `loss` is the
mean over the interval's samples (5 logging steps x 16 micro-batch samples = 80), and the
logged `accuracy` is the fraction with m_i > 0.  Therefore

    loss >= log(2) * (1 - accuracy)          <-- falsifiable, needs no extra data

and the EXCESS = loss - log(2)*(1-acc) is the part of the loss contributed by samples that
ARE ordered correctly but with a small margin.  If the identity holds over the whole run it
proves (a) `accuracy` is a genuine per-sample count on a 1/80 grid, and (b) the loss trend is
dominated by how MANY samples flip, not by how far apart the two sides are.

CPU only, read-only.  Writes reports/m3-dpo-resume-watchdog-M-loss-consistency.json
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
A = json.loads((R / "m3-dpo-resume-watchdog-A.json").read_text(encoding="utf-8"))
S = A["dpo_series"]
LOG2 = 0.6931471805599453
N_SAMPLES = 80.0   # 5 logging steps x gradient_accumulation 16

rows, viol = [], []
for r in S:
    n_lo = LOG2 * (1.0 - r["acc"])
    excess = r["loss"] - n_lo
    rows.append({"step": r["step"], "loss": r["loss"], "acc": r["acc"],
                 "flipped_samples": round(N_SAMPLES * (1 - r["acc"]), 2),
                 "loss_lower_bound_from_flipped": n_lo, "excess": excess,
                 "excess_per_correct_sample": (excess / (N_SAMPLES * r["acc"] - 1)) if r["acc"] > 0 else None})
    if r["loss"] < n_lo - 1e-6:
        viol.append({"step": r["step"], "loss": r["loss"], "lower_bound": n_lo})

exc = [x["excess"] for x in rows]
out = {
    "n_points": len(rows),
    "identity": "loss >= log(2) * (1 - accuracy)",
    "n_violations": len(viol),
    "violations": viol,
    "verdict": ("holds at every logging point" if not viol else "VIOLATED -- accuracy/loss disagree"),
    "excess_stats": {"min": min(exc), "median": st.median(exc), "max": max(exc),
                     "mean_first20": st.mean(exc[:20]), "mean_last20": st.mean(exc[-20:])},
    "flipped_fraction": {"first20_mean": st.mean([1 - x["acc"] for x in rows[:20]]),
                         "last20_mean": st.mean([1 - x["acc"] for x in rows[-20:]])},
    "loss_trend_decomposition": {
        "note": ("loss = log2*(1-acc) + excess. Over the run, compare which term moved."),
        "term1_first20": st.mean([x["loss_lower_bound_from_flipped"] for x in rows[:20]]),
        "term1_last20": st.mean([x["loss_lower_bound_from_flipped"] for x in rows[-20:]]),
        "term2_first20": st.mean([x["excess"] for x in rows[:20]]),
        "term2_last20": st.mean([x["excess"] for x in rows[-20:]]),
    },
    "rows": rows,
}
(R / "m3-dpo-resume-watchdog-M-loss-consistency.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"identity  loss >= log2*(1-acc) : violations {len(viol)}/{len(rows)}  -> {out['verdict']}")
print(f"  excess (loss - log2*(1-acc)): min={min(exc):.4f} median={st.median(exc):.4f} max={max(exc):.4f}")
d = out["loss_trend_decomposition"]
print("  decomposition (mean of first 20 points vs last 20):")
print(f"    log2*(1-acc)  : {d['term1_first20']:.4f} -> {d['term1_last20']:.4f}")
print(f"    excess        : {d['term2_first20']:.4f} -> {d['term2_last20']:.4f}")
print(f"  flipped fraction: {out['flipped_fraction']['first20_mean']:.4f} -> {out['flipped_fraction']['last20_mean']:.4f}")
print("  last 4 points:")
for x in rows[-4:]:
    print(f"    step {x['step']}: loss={x['loss']:.4f} acc={x['acc']:.4f} "
          f"flipped~{x['flipped_samples']:.1f}/80 lower_bound={x['loss_lower_bound_from_flipped']:.4f} "
          f"excess={x['excess']:+.4f}")
print("WROTE", R / "m3-dpo-resume-watchdog-M-loss-consistency.json")
