# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog L: below-reference EPISODES and the current distance to the
pre-registered early-stop rule.

Answers, per episode of "policy is below its own frozen reference on the chosen side":
  - when it started / how long / how deep
  - what the rejected side did at the same time (=> separation vs suppression vs hollow)
  - what the pre-registered early-stop rule would have done at each point of it

CPU only, read-only.  Writes reports/m3-dpo-resume-watchdog-L-episodes.json
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
STEP = [r["step"] for r in S]
CH = [r["chosen"] for r in S]


def centered5(vals, i):
    lo, hi = max(0, i - 2), min(len(vals), i + 3)
    return st.mean(vals[lo:hi]), STEP[lo], STEP[hi - 1], hi - lo


c5, r5, inprog = [], [], []
for i, r in enumerate(S):
    m, a, b, n = centered5(CH, i)
    c5.append(m)
    r5.append(centered5([x["rejected"] for x in S], i)[0])
    inprog.append(n < 5)

# ---------------- episodes of c5 < 0 ----------------
eps = []
i = 0
while i < len(S):
    if c5[i] < 0:
        j = i
        while j + 1 < len(S) and c5[j + 1] < 0:
            j += 1
        seg = S[i:j + 1]
        dch = c5[j] - c5[i]
        dre = r5[j] - r5[i]
        lam_in = [c5[t] / (c5[t] + abs(r5[t])) for t in range(i, j + 1)
                  if (c5[t] + abs(r5[t]))]
        eps.append({
            "steps_from_to": [STEP[i], STEP[j]],
            "n_logging_points": j - i + 1,
            "span_steps": STEP[j] - STEP[i] + (STEP[1] - STEP[0]),
            "min_centered5_chosen": min(c5[i:j + 1]),
            "min_centered5_chosen_step": STEP[i + c5[i:j + 1].index(min(c5[i:j + 1]))],
            "min_raw_chosen": min(x["chosen"] for x in seg),
            "min_raw_chosen_step": [x["step"] for x in seg
                                    if x["chosen"] == min(y["chosen"] for y in seg)][0],
            "mean_acc": st.mean([x["acc"] for x in seg]),
            "max_acc": max(x["acc"] for x in seg),
            "mean_margins": st.mean([x["margins"] for x in seg]),
            "chosen_delta_centered5": dch,
            "rejected_delta_centered5": dre,
            "both_sides_fell": dch < 0 and dre < 0,
            "rejected_fell": dre < 0,
            "mean_lambda_level_centered5": st.mean(lam_in) if lam_in else None,
            "min_lambda_level_centered5": min(lam_in) if lam_in else None,
            "still_in_progress_at_last_point": j == len(S) - 1,
            "points_with_acc_ge_097": sum(1 for x in seg if x["acc"] >= 0.97),
            "n_points": len(seg),
        })
        i = j + 1
    else:
        i += 1

# ---------------- current distance to the pre-registered rule ----------------
last = S[-1]
run = 0
for r in reversed(S):
    if r["acc"] >= 0.97:
        run += 1
    else:
        break
m_ratio = last["margins"] / S[0]["margins"]
w5 = S[-5:]
m_ratio_span = w5[-1]["margins"] / w5[0]["margins"]

out = {
    "n_points": len(S),
    "coverage_steps": [STEP[0], STEP[-1]],
    "episodes_centered5_chosen_below_zero": eps,
    "n_episodes": len(eps),
    "n_episodes_both_sides_fell": sum(1 for e in eps if e["both_sides_fell"]),
    "total_episode_points": sum(e["n_logging_points"] for e in eps),
    "total_points_in_episodes_frac": (sum(e["n_logging_points"] for e in eps) / len(S)) if S else None,
    # robust pointers: the report must never rely on "the last episode" being the
    # interesting one (a 1-point blip can appear at any time and would silently
    # wreck every narrative sentence).
    "longest_episode": (max(eps, key=lambda e: (e["span_steps"], -e["min_centered5_chosen"]))
                        if eps else None),
    "deepest_episode": (min(eps, key=lambda e: e["min_centered5_chosen"]) if eps else None),
    "in_progress_episode": (eps[-1] if eps and eps[-1]["still_in_progress_at_last_point"] else None),
    "current": {
        "step": last["step"],
        "chosen": last["chosen"], "rejected": last["rejected"],
        "acc": last["acc"], "margins": last["margins"],
        "centered5_chosen": c5[-1], "centered5_rejected": r5[-1],
        "lambda_level_centered5": c5[-1] / (c5[-1] + abs(r5[-1])) if (c5[-1] + abs(r5[-1])) else None,
        "acc_ge_097_consecutive_points_ending_here": run,
        "margins_vs_run_start_ratio": m_ratio,
        "margins_span_ratio_last5": m_ratio_span,
        "early_stop_triggered": bool(run >= 5 and m_ratio_span > 2.0),
        "short_by_points": max(0, 5 - run),
    },
    "worst_centered5_chosen": min(c5), "worst_centered5_step": STEP[c5.index(min(c5))],
    "worst_raw_chosen": min(CH), "worst_raw_step": STEP[CH.index(min(CH))],
    "n_points_raw_chosen_below_zero": sum(1 for x in CH if x < 0),
}
(R / "m3-dpo-resume-watchdog-L-episodes.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"points={len(S)} steps {STEP[0]}..{STEP[-1]}")
print(f"episodes of centered5(chosen)<0 : {len(eps)}")
for e in eps:
    print(f"  steps {e['steps_from_to'][0]:>4}-{e['steps_from_to'][1]:<4} "
          f"({e['n_logging_points']:>2} pts / {e['span_steps']:>3} steps) "
          f"min_c5={e['min_centered5_chosen']:+.3f}@{e['min_centered5_chosen_step']} "
          f"min_raw={e['min_raw_chosen']:+.3f}@{e['min_raw_chosen_step']} "
          f"acc_mean={e['mean_acc']:.3f} acc>=0.97:{e['points_with_acc_ge_097']}/{e['n_points']} "
          f"| dChosen={e['chosen_delta_centered5']:+.3f} dRej={e['rejected_delta_centered5']:+.3f} "
          f"both_fell={e['both_sides_fell']} {'<-- IN PROGRESS' if e['still_in_progress_at_last_point'] else ''}")
c = out["current"]
print(f"\ncurrent step {c['step']}: chosen={c['chosen']:+.4f} rejected={c['rejected']:+.4f} "
      f"acc={c['acc']:.4f} margins={c['margins']:.3f} lambda={c['lambda_level_centered5']:.4f}")
print(f"  acc>=0.97 consecutive points now = {c['acc_ge_097_consecutive_points_ending_here']} "
      f"(need 5; short by {c['short_by_points']})")
print(f"  margins vs run start = {c['margins_vs_run_start_ratio']:.2f}x ; "
      f"margins span ratio over last 5 points = {c['margins_span_ratio_last5']:.3f}x (need >2)")
print(f"  EARLY STOP TRIGGERED = {c['early_stop_triggered']}")
print(f"\nworst centered5 chosen = {out['worst_centered5_chosen']:+.4f} @ step {out['worst_centered5_step']}")
print(f"worst raw chosen      = {out['worst_raw_chosen']:+.4f} @ step {out['worst_raw_step']}")
print(f"raw chosen<0 points   = {out['n_points_raw_chosen_below_zero']}/{len(S)}")
print("WROTE", R / "m3-dpo-resume-watchdog-L-episodes.json")
