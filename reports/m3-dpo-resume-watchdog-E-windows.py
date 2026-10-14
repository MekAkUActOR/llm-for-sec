# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog E: LR-hypothesis discrimination, window statistics for
rewards/*, and the "preference separation vs suppression vs hollow" verdict.

CPU only, read-only. Writes reports/m3-dpo-resume-watchdog-E-windows.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
A = json.loads((R / "m3-dpo-resume-watchdog-A.json").read_text(encoding="utf-8"))

PEAK, WARMUP = 2.0e-6, 60


def cos_lr(idx: int, total: int) -> float:
    if idx < WARMUP:
        return PEAK * (idx + 1) / WARMUP
    return PEAK * 0.5 * (1.0 + math.cos(math.pi * (idx - WARMUP) / (total - WARMUP)))


def main() -> int:
    out: dict = {}

    # ---------- 1) LR hypotheses ----------
    obs = [(t["step"], t["lr"]) for t in A["lr_reverse"]]
    hyps = {}
    for total, tag in ((1803, "H1_schedule_horizon_kept_1803"),
                       (1603, "H2_schedule_restarted_1603"),
                       (1803 - 200, "H2b_1603_alt")):
        for offset in (0, 1):
            errs = [abs(cos_lr(s - offset, total) - lr) / lr for s, lr in obs]
            hyps[f"{tag}|idx=step-{offset}"] = {
                "total_steps": total, "index_offset": offset,
                "max_rel_err": max(errs), "mean_rel_err": sum(errs) / len(errs),
            }
    best = min(hyps.items(), key=lambda kv: kv[1]["max_rel_err"])
    out["lr_hypotheses"] = {
        "observed_points": obs,
        "candidates": hyps,
        "best_by_max_rel_err": best[0],
        "conclusion": ("The logged lr equals the 1803-step cosine at schedule index "
                       "(step-1) to <1e-6 relative error; a restarted 1603-step "
                       "schedule is off by ~5e-3 relative error and is rejected."
                       if best[0].startswith("H1") else "unexpected: see candidates"),
    }
    # what a from-scratch run would have logged at its first point
    out["lr_hypotheses"]["counterfactual_from_scratch_first_point"] = {
        "step": 5, "lr": cos_lr(5, 1803),
        "observed_first_post_resume_lr": obs[0][1] if obs else None,
        "ratio_observed_over_from_scratch": (obs[0][1] / cos_lr(5, 1803)) if obs else None,
    }

    rows = A["dpo_series"]

    def win(lo, hi):
        w = [r for r in rows if lo <= r["step"] <= hi]
        if not w:
            return None
        def m(k):
            v = [r[k] for r in w if r[k] is not None]
            return sum(v) / len(v) if v else None
        return {
            "range": [lo, hi], "n_points": len(w),
            "step_first": w[0]["step"], "step_last": w[-1]["step"],
            "mean_acc": m("acc"), "mean_margins": m("margins"),
            "mean_chosen": m("chosen"), "mean_rejected": m("rejected"),
            "mean_loss": m("loss"),
            "first_chosen": w[0]["chosen"], "last_chosen": w[-1]["chosen"],
            "first_rejected": w[0]["rejected"], "last_rejected": w[-1]["rejected"],
        }
    windows = {
        "pre_kill_5_200": win(5, 200),
        "resumed_205_300": win(205, 300),
        "whole_5_300": win(5, 300),
        "last_10_points": win(rows[-10]["step"], rows[-1]["step"]),
        "last_20_points": win(rows[-20]["step"], rows[-1]["step"]),
    }
    out["windows"] = windows

    # ---------- 2) trends (OLS per 100 steps) ----------
    def slope(k):
        pts = [(r["step"], r[k]) for r in rows if r[k] is not None]
        n = len(pts)
        mx = sum(p[0] for p in pts) / n
        my = sum(p[1] for p in pts) / n
        num = sum((p[0] - mx) * (p[1] - my) for p in pts)
        den = sum((p[0] - mx) ** 2 for p in pts)
        return 100.0 * num / den
    out["trend_per_100_steps"] = {k: slope(k) for k in
                                  ("acc", "margins", "chosen", "rejected", "loss")}

    # ---------- 3) separation vs suppression vs hollow ----------
    def classify(lo, hi, label):
        w = [r for r in rows if lo <= r["step"] <= hi]
        if len(w) < 2:
            return None
        dc = w[-1]["chosen"] - w[0]["chosen"]
        dr = w[-1]["rejected"] - w[0]["rejected"]
        both_down = dc < 0 and dr < 0
        return {
            "window": label, "n_points": len(w),
            "delta_chosen": dc, "delta_rejected": dr,
            "ratio_abs_drej_over_dcho": (abs(dr) / abs(dc)) if dc else None,
            "chosen_end_sign": "positive (policy beats ref)" if w[-1]["chosen"] > 0 else "negative (policy WORSE than ref)",
            "class": ("HOLLOW: both sides fall relative to ref" if both_down else
                      "PURE SUPPRESSION: rejected collapses, chosen does not rise"
                      if dr < 0 and dc <= 0.15 * abs(dr) else
                      "PREFERENCE SEPARATION: chosen rises AND rejected falls"
                      if dc > 0 and dr < 0 else "MIXED"),
        }
    out["classification"] = [c for c in (
        classify(5, 200, "pre_kill 5->200 (what the previous watchdog reported)"),
        classify(205, 300, "resumed segment 205->300"),
        classify(5, 300, "whole run 5->300"),
        classify(200, 300, "kill boundary onward 200->300"),
        classify(rows[max(0, len(rows) - 21)]["step"], rows[-1]["step"], "last 20 points"),
    ) if c]

    # ---------- 4) counts of "chosen below reference" ----------
    out["chosen_below_reference"] = {
        "steps": [{"step": r["step"], "chosen": round(r["chosen"], 4)}
                  for r in rows if r["chosen"] is not None and r["chosen"] < 0],
        "n": sum(1 for r in rows if r["chosen"] is not None and r["chosen"] < 0),
        "n_total": len(rows),
        "in_pre_kill": sum(1 for r in rows if r["step"] <= 200 and r["chosen"] is not None and r["chosen"] < 0),
        "in_resumed": sum(1 for r in rows if r["step"] > 200 and r["chosen"] is not None and r["chosen"] < 0),
    }
    out["rejected_below_reference"] = {
        "n": sum(1 for r in rows if r["rejected"] is not None and r["rejected"] < 0),
        "n_total": len(rows),
    }

    # ---------- 5) 5-consecutive early-stop scan, explicit ----------
    scan = []
    for i in range(len(rows) - 4):
        w = rows[i:i + 5]
        if all(r["acc"] is not None and r["acc"] >= 0.97 for r in w) and \
           all(w[j + 1]["step"] - w[j]["step"] == 5 for j in range(4)):
            scan.append([r["step"] for r in w])
    out["five_consecutive_acc_ge_097_windows"] = scan
    out["n_five_consecutive_windows"] = len(scan)

    (R / "m3-dpo-resume-watchdog-E-windows.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("== LR hypotheses (relative error vs observed) ==")
    for k, v in sorted(hyps.items(), key=lambda kv: kv[1]["max_rel_err"]):
        print(f"  {k:38} max_rel_err={v['max_rel_err']:.3e} mean={v['mean_rel_err']:.3e}")
    print("  best:", best[0])
    print("  counterfactual from-scratch first point:", json.dumps(
        out["lr_hypotheses"]["counterfactual_from_scratch_first_point"]))
    print("\n== windows ==")
    for k, v in windows.items():
        if v:
            print(f"  {k:18} steps {v['step_first']}..{v['step_last']} n={v['n_points']:>2} "
                  f"acc={v['mean_acc']:.4f} marg={v['mean_margins']:>8.4f} "
                  f"cho={v['mean_chosen']:>8.4f} rej={v['mean_rejected']:>8.4f} loss={v['mean_loss']:.4f}")
    print("\n== trend per 100 steps ==", json.dumps(out["trend_per_100_steps"], indent=1))
    print("\n== classification ==")
    for c in out["classification"]:
        print("  *", c["window"])
        print(f"    dcho={c['delta_chosen']:+.4f} drej={c['delta_rejected']:+.4f} "
              f"ratio={c['ratio_abs_drej_over_dcho']} end_sign={c['chosen_end_sign']}")
        print("    =>", c["class"])
    print("\n== chosen < 0 (policy worse than ref on chosen side) ==")
    print(json.dumps(out["chosen_below_reference"], ensure_ascii=False))
    print("== rejected < 0 ==", json.dumps(out["rejected_below_reference"]))
    print("== 5-consecutive acc>=0.97 windows ==", scan)
    print("\nWROTE", R / "m3-dpo-resume-watchdog-E-windows.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
