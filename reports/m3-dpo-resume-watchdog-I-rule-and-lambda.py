# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog I: adjudicate the pre-registered early-stop rule's
discriminative power, and build the composition-aware alternative observables.

Outputs: reports/m3-dpo-resume-watchdog-I-rule-and-lambda.json
CPU only, read-only.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
A = json.loads((R / "m3-dpo-resume-watchdog-A.json").read_text(encoding="utf-8"))
rows = [r for r in A["dpo_series"]]

ACC_THR = 0.97
K = 5


def windows(k=K):
    """All sliding windows of k CONSECUTIVE logging points (step spacing == 5)."""
    for i in range(len(rows) - k + 1):
        w = rows[i:i + k]
        if all(w[j + 1]["step"] - w[j]["step"] == 5 for j in range(k - 1)):
            yield w


def main() -> int:
    out: dict = {"acc_threshold": ACC_THR, "k": K, "n_points": len(rows)}

    # ---------- 1) feasible-region analysis of the conjunctive rule ----------
    acc_ok, marg_ok_span, marg_ok_base, both = [], [], [], []
    ratios = []
    for w in windows():
        a_ok = all(r["acc"] >= ACC_THR for r in w)
        m_ratio = w[-1]["margins"] / w[0]["margins"]
        m_ok = m_ratio >= 2.0
        ratios.append({"steps": [w[0]["step"], w[-1]["step"]], "ratio": round(m_ratio, 3)})
        if a_ok:
            acc_ok.append([w[0]["step"], w[-1]["step"]])
        if m_ok:
            marg_ok_span.append([w[0]["step"], w[-1]["step"]])
        if w[-1]["margins"] >= 2 * rows[0]["margins"]:
            marg_ok_base.append([w[0]["step"], w[-1]["step"]])
        if a_ok and m_ok:
            both.append([w[0]["step"], w[-1]["step"]])
    out["rule_feasibility"] = {
        "n_windows": len(list(windows())),
        "acc_condition_windows": acc_ok,
        "n_acc_condition": len(acc_ok),
        "margins_doubling_within_same_span_windows": len(marg_ok_span),
        "margins_doubling_within_same_span_first_last": (
            marg_ok_span[0], marg_ok_span[-1]) if marg_ok_span else None,
        "margins_doubling_vs_run_start_windows": len(marg_ok_base),
        "both_conditions_windows": both,
        "n_both": len(both),
        "margin_ratio_distribution": {
            "min": min(r["ratio"] for r in ratios),
            "median": st.median([r["ratio"] for r in ratios]),
            "max": max(r["ratio"] for r in ratios),
            "n_ge_2": sum(1 for r in ratios if r["ratio"] >= 2),
            "n_lt_1": sum(1 for r in ratios if r["ratio"] < 1),
        },
        "first_window_where_margins_cannot_double_anymore": None,
    }
    # when does the span-doubling condition stop being achievable at all?
    last_double = None
    for i, w in enumerate(windows()):
        if w[-1]["margins"] / w[0]["margins"] >= 2.0:
            last_double = [w[0]["step"], w[-1]["step"]]
    out["rule_feasibility"]["last_window_satisfying_span_doubling"] = last_double
    # smallest achievable doubling ratio per window-start
    per_start = {}
    for w in windows():
        per_start[w[0]["step"]] = round(w[-1]["margins"] / w[0]["margins"], 3)
    out["rule_feasibility"]["span_ratio_by_window_start"] = per_start

    # ---------- 2) composition-aware observable lambda ----------
    def lam(w, mode="endpoints"):
        if mode == "endpoints":
            dc = w[-1]["chosen"] - w[0]["chosen"]
            dr = w[-1]["rejected"] - w[0]["rejected"]
        else:
            dc = w[-1]["chosen"] - w[0]["chosen"]
            dr = w[-1]["rejected"] - w[0]["rejected"]
        den = dc + abs(dr)
        return (dc / den) if den else None, dc, dr
    lam_points = []
    for w in windows():
        v, dc, dr = lam(w)
        lam_points.append({"window_start": w[0]["step"], "window_end": w[-1]["step"],
                           "lambda": round(v, 4) if v is not None else None,
                           "d_chosen": round(dc, 4), "d_rejected": round(dr, 4)})
    segs = {
        "pre_kill_5_200": (5, 200), "resumed_205_300": (205, 300),
        "whole_5_300": (5, 300), "last_10_points": (rows[-10]["step"], rows[-1]["step"]),
    }
    lam_seg = {}
    for name, (lo, hi) in segs.items():
        w = [r for r in rows if lo <= r["step"] <= hi]
        dc = w[-1]["chosen"] - w[0]["chosen"]
        dr = w[-1]["rejected"] - w[0]["rejected"]
        lam_seg[name] = {
            "steps": [w[0]["step"], w[-1]["step"]],
            "d_chosen": round(dc, 4), "d_rejected": round(dr, 4),
            "lambda_endpoint": round(dc / (dc + abs(dr)), 4) if (dc + abs(dr)) else None,
            "mean_chosen": round(st.mean([r["chosen"] for r in w]), 4),
            "mean_rejected": round(st.mean([r["rejected"] for r in w]), 4),
            "note_on_slope_lambda": ("endpoint lambda is a ratio of two noisy deltas; "
                                     "it is undefined/unstable when both deltas ~ 0"),
        }
    out["lambda"] = {
        "definition": "lambda = d_chosen / (d_chosen + |d_rejected|) over a fixed window; "
                      "1 = pure chosen-raising, 0 = pure rejected-suppression, "
                      "0.5 = equal moves",
        "per_window": lam_points,
        "lambda_range": [min(x["lambda"] for x in lam_points if x["lambda"] is not None),
                         max(x["lambda"] for x in lam_points if x["lambda"] is not None)],
        "by_segment": lam_seg,
    }

    # robust variant: level-based lambda over a centered rolling window of MEANS
    def lam_level(w):
        c = st.mean([r["chosen"] for r in w])
        rj = st.mean([r["rejected"] for r in w])
        den = c + abs(rj)
        return (c / den) if den else None, c, rj
    lam_level_rows = []
    for i in range(len(rows)):
        lo, hi = max(0, i - 2), min(len(rows), i + 3)
        w = rows[lo:hi]
        if len(w) >= 3:
            v, c, rj = lam_level(w)
            lam_level_rows.append({"step": rows[i]["step"], "n_window": len(w),
                                   "lambda_level": round(v, 4) if v is not None else None,
                                   "mean_chosen": round(c, 4), "mean_rejected": round(rj, 4)})
    out["lambda"]["lambda_level_centered5_per_point"] = lam_level_rows
    out["lambda"]["lambda_level_centered5_range"] = [
        min(x["lambda_level"] for x in lam_level_rows if x["lambda_level"] is not None),
        max(x["lambda_level"] for x in lam_level_rows if x["lambda_level"] is not None)]
    out["lambda"]["lambda_level_by_segment"] = {
        name: (lambda v: {"lambda_level": round(v[0], 4), "mean_chosen": round(v[1], 4),
                          "mean_rejected": round(v[2], 4)})(lam_level([r for r in rows if lo <= r["step"] <= hi]))
        for name, (lo, hi) in segs.items()}
    out["lambda"]["stability_warning"] = (
        "endpoint-delta lambda is a ratio of two noisy deltas: on this run it spans "
        f"{out['lambda']['lambda_range']}, is undefined when both deltas vanish, and goes "
        "to -inf for the 'both fall by a similar amount' (hollow) regime. It must NOT be "
        "used as a threshold statistic. Use the level-based lambda over window MEANS, "
        "whose centered-5 range is "
        f"{out['lambda']['lambda_level_centered5_range']}.")

    # ---------- 3) chosen-side absolute displacement (vs the frozen reference) ----------
    def roll(k):
        vals = []
        for i in range(len(rows) - k + 1):
            w = rows[i:i + k]
            if all(w[j + 1]["step"] - w[j]["step"] == 5 for j in range(k - 1)):
                vals.append({"from": w[0]["step"], "to": w[-1]["step"],
                             "mean_chosen": round(st.mean([r["chosen"] for r in w]), 4)})
        return vals
    rollings = {f"roll{k}": roll(k) for k in (1, 5, 10, 20)}
    out["chosen_displacement"] = {
        "per_point": [{"step": r["step"], "chosen": round(r["chosen"], 4),
                       "rejected": round(r["rejected"], 4), "acc": r["acc"],
                       "margins": round(r["margins"], 4)} for r in rows],
        "rolling_means": {k: {"min": min(v["mean_chosen"] for v in vs),
                              "min_window": min(vs, key=lambda v: v["mean_chosen"]),
                              "max": max(v["mean_chosen"] for v in vs),
                              "n_windows_negative": sum(1 for v in vs if v["mean_chosen"] < 0),
                              "n_windows": len(vs)}
                          for k, vs in rollings.items()},
        "longest_consecutive_negative_points": None,
        "n_points_negative": sum(1 for r in rows if r["chosen"] < 0),
    }
    # longest consecutive run of chosen<0 (step spacing 5)
    best, cur, best_steps, cur_steps = 0, 0, [], []
    for r in rows:
        if r["chosen"] < 0:
            cur += 1
            cur_steps.append(r["step"])
            if cur > best:
                best, best_steps = cur, list(cur_steps)
        else:
            cur, cur_steps = 0, []
    out["chosen_displacement"]["longest_consecutive_negative_points"] = {
        "n": best, "steps": best_steps, "span_steps": (best - 1) * 5 if best else 0}

    (R / "m3-dpo-resume-watchdog-I-rule-and-lambda.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    f = out["rule_feasibility"]
    print("== conjunctive rule feasible region (%d sliding %d-point windows) ==" % (f["n_windows"], K))
    print("  acc>=0.97 windows        :", f["n_acc_condition"], f["acc_condition_windows"])
    print("  margins x2 within span   :", f["margins_doubling_within_same_span_windows"],
          "first/last:", f["margins_doubling_within_same_span_first_last"])
    print("  margins x2 vs run start  :", f["margins_doubling_vs_run_start_windows"])
    print("  BOTH                     :", f["n_both"], f["both_conditions_windows"])
    print("  last window where span-doubling holds:", f["last_window_satisfying_span_doubling"])
    print("  span ratio dist:", json.dumps(f["margin_ratio_distribution"]))
    print("\n  span ratio by window start (step -> ratio):")
    print("   ", json.dumps(f["span_ratio_by_window_start"]))
    print("\n== lambda by segment ==")
    for k, v in lam_seg.items():
        print(f"  {k:18} steps {v['steps']} lambda={v['lambda_endpoint']} "
              f"dcho={v['d_chosen']:+.4f} drej={v['d_rejected']:+.4f} "
              f"mean_cho={v['mean_chosen']:+.4f}")
    print("  per-window lambda range:", out["lambda"]["lambda_range"])
    print("  level-lambda by segment:", json.dumps(out["lambda"]["lambda_level_by_segment"]))
    print("  level-lambda (centered5) range:", out["lambda"]["lambda_level_centered5_range"])
    print("  level-lambda per point (step:value):",
          ", ".join(f"{x['step']}:{x['lambda_level']}" for x in lam_level_rows))
    print("\n== chosen displacement ==")
    print(json.dumps(out["chosen_displacement"]["rolling_means"], indent=1))
    print("  longest consecutive chosen<0:", json.dumps(
        out["chosen_displacement"]["longest_consecutive_negative_points"]))
    print("WROTE", R / "m3-dpo-resume-watchdog-I-rule-and-lambda.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
