# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog G: step-time from trainer_log elapsed_time, ETA
correction, and descriptive statistics on the chosen/rejected windows.

CPU only, read-only. Writes reports/m3-dpo-resume-watchdog-G-stats.json
"""
from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
TL = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo" / "trainer_log.jsonl"


def secs(s: str) -> int:
    p = [int(x) for x in s.split(":")]
    while len(p) < 3:
        p.insert(0, 0)
    return p[0] * 3600 + p[1] * 60 + p[2]


def main() -> int:
    raw = [json.loads(l) for l in TL.read_text(encoding="utf-8").splitlines() if l.strip()]
    steps = [r["current_steps"] for r in raw]
    cut = next((i for i in range(1, len(raw)) if steps[i] <= steps[i - 1]), None)
    post = raw[cut:] if cut is not None else raw
    pre = raw[:cut] if cut is not None else []

    out: dict = {}
    e0, e1 = secs(post[0]["elapsed_time"]), secs(post[-1]["elapsed_time"])
    s0, s1 = post[0]["current_steps"], post[-1]["current_steps"]
    out["step_time"] = {
        "resumed_segment_first": {"step": s0, "elapsed": e0},
        "resumed_segment_last": {"step": s1, "elapsed": e1},
        "s_per_step_resumed": round((e1 - e0) / (s1 - s0), 4),
        "pre_kill_s_per_step": (round((secs(pre[-1]["elapsed_time"]) - secs(pre[0]["elapsed_time"]))
                                      / (pre[-1]["current_steps"] - pre[0]["current_steps"]), 4)
                                if pre else None),
        "pre_kill_first_last": (pre[0]["current_steps"], pre[-1]["current_steps"]) if pre else None,
        "pre_kill_elapsed": (pre[0]["elapsed_time"], pre[-1]["elapsed_time"]) if pre else None,
    }
    total = post[-1]["total_steps"]
    sps = (e1 - e0) / (s1 - s0)
    out["eta"] = {
        "steps_done_global": s1, "steps_remaining": total - s1,
        "true_eta_seconds": round((total - s1) * sps, 1),
        "true_eta_hms": "%d:%02d:%02d" % ((total - s1) * sps // 3600,
                                          ((total - s1) * sps % 3600) // 60,
                                          (total - s1) * sps % 60),
        "reported_remaining_time_last": post[-1]["remaining_time"],
        "note": ("LF computes remaining_time from the POST-RESUME elapsed only while "
                 "current_steps is the GLOBAL step, so after a resume it understates "
                 "the ETA by the ratio global_step/steps_done_since_resume"),
        "understatement_factor": round(s1 / (s1 - s0), 3),
    }

    A = json.loads((R / "m3-dpo-resume-watchdog-A.json").read_text(encoding="utf-8"))
    rows = A["dpo_series"]

    def window(lo, hi, key):
        return [r[key] for r in rows if lo <= r["step"] <= hi and r[key] is not None]

    def welch(a, b):
        ma, mb = st.mean(a), st.mean(b)
        va, vb = st.variance(a), st.variance(b)
        se = math.sqrt(va / len(a) + vb / len(b))
        t = (ma - mb) / se if se else float("inf")
        return {"mean_a": ma, "mean_b": mb, "diff": ma - mb, "se": se, "t": t,
                "sd_a": math.sqrt(va), "sd_b": math.sqrt(vb),
                "n_a": len(a), "n_b": len(b),
                "note": ("Welch t on logging-point means. Points are NOT independent "
                         "(same model, overlapping batches), so this is descriptive only; "
                         "the per-point SD overstates sampling noise, which makes the test "
                         "CONSERVATIVE for the chosen drop.")}

    out["window_compare"] = {
        "chosen_last10_pre_vs_last10_post": welch(window(155, 200, "chosen"), window(255, 300, "chosen")),
        "chosen_all_pre_vs_all_post": welch(window(5, 200, "chosen"), window(205, 300, "chosen")),
        "rejected_last10_pre_vs_last10_post": welch(window(155, 200, "rejected"), window(255, 300, "rejected")),
        "acc_all_pre_vs_all_post": welch(window(5, 200, "acc"), window(205, 300, "acc")),
        "margins_all_pre_vs_all_post": welch(window(5, 200, "margins"), window(205, 300, "margins")),
    }

    def ols(lo, hi, key):
        pts = [(r["step"], r[key]) for r in rows if lo <= r["step"] <= hi and r[key] is not None]
        n = len(pts)
        mx = sum(p[0] for p in pts) / n
        my = sum(p[1] for p in pts) / n
        num = sum((p[0] - mx) * (p[1] - my) for p in pts)
        den = sum((p[0] - mx) ** 2 for p in pts)
        b = num / den
        a = my - b * mx
        ss_tot = sum((p[1] - my) ** 2 for p in pts)
        ss_res = sum((p[1] - (a + b * p[0])) ** 2 for p in pts)
        return {"slope_per_100_steps": 100 * b, "intercept": a,
                "r2": 1 - ss_res / ss_tot if ss_tot else None, "n": n}
    out["ols"] = {
        f"{k}_{seg}": ols(lo, hi, k)
        for seg, (lo, hi) in {"pre_5_200": (5, 200), "post_205_300": (205, 300), "all_5_300": (5, 300)}.items()
        for k in ("chosen", "rejected", "acc", "margins")
    }

    out["acc_granularity"] = {
        "samples_per_logging_point": 5 * 16,
        "granularity": 1 / 80,
        "observed_acc_values": sorted({round(r["acc"], 6) for r in rows if r["acc"] is not None}),
    }

    (R / "m3-dpo-resume-watchdog-G-stats.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("== step time ==")
    print(json.dumps(out["step_time"], indent=1))
    print("\n== ETA ==")
    print(json.dumps(out["eta"], ensure_ascii=False, indent=1))
    print("\n== window compare (Welch, descriptive) ==")
    for k, v in out["window_compare"].items():
        print(f"  {k:38} meanA={v['mean_a']:>+8.4f} meanB={v['mean_b']:>+8.4f} "
              f"diff={v['diff']:>+8.4f} se={v['se']:.4f} t={v['t']:>7.2f}")
    print("\n== OLS slopes per 100 steps ==")
    for k, v in out["ols"].items():
        print(f"  {k:26} slope={v['slope_per_100_steps']:>+8.4f} r2={v['r2']:.3f} n={v['n']}")
    print("\n== acc granularity ==")
    print(json.dumps(out["acc_granularity"], indent=1))
    print("\nWROTE", R / "m3-dpo-resume-watchdog-G-stats.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
