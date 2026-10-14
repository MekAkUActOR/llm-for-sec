# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog A: (1) resume-point independent confirmation incl. LR
reverse-derivation; (2) DPO metric series from trainer_state.json log_history only.

CPU only, read-only. Writes reports/m3-dpo-resume-watchdog-A.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
OUT = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo"
R = ROOT / "reports"
TL = OUT / "trainer_log.jsonl"

PEAK_LR = 2.0e-6
WARMUP = 60
TOTAL = 1803


def cosine_lr(step: float, total: int = TOTAL, warmup: int = WARMUP,
              peak: float = PEAK_LR) -> float:
    if step < warmup:
        return peak * (step + 1) / warmup
    progress = (step - warmup) / max(1, total - warmup)
    return peak * 0.5 * (1.0 + math.cos(math.pi * progress))


def lr_to_step(lr: float, total: int = TOTAL, warmup: int = WARMUP,
               peak: float = PEAK_LR) -> float:
    """Invert the cosine branch: which step would produce this lr?"""
    r = lr / peak
    if r > 1.0 or r < 0.0:
        return float("nan")
    cosv = 2.0 * r - 1.0
    cosv = max(-1.0, min(1.0, cosv))
    x = math.acos(cosv) / math.pi
    return warmup + x * (total - warmup)


def main() -> int:
    res: dict = {"peak_lr": PEAK_LR, "warmup": WARMUP, "total_steps": TOTAL}

    # ---------- 1) trainer_log.jsonl ----------
    raw = [json.loads(l) for l in TL.read_text(encoding="utf-8").splitlines() if l.strip()]
    steps = [r["current_steps"] for r in raw]
    res["jsonl"] = {
        "path": str(TL),
        "n_lines": len(raw),
        "steps_in_file_order": steps,
        "duplicate_steps": sorted({s for s in steps if steps.count(s) > 1}),
    }
    # find the split: last index of the max step of the first (pre-kill) block
    first_block_end = None
    for i in range(1, len(raw)):
        if raw[i]["current_steps"] <= raw[i - 1]["current_steps"]:
            first_block_end = i
            break
    if first_block_end is not None:
        pre = raw[:first_block_end]
        post = raw[first_block_end:]
        res["jsonl"]["pre_kill_block_last_step"] = pre[-1]["current_steps"]
        res["jsonl"]["post_resume_first_step"] = post[0]["current_steps"]
        res["jsonl"]["post_resume_first_line"] = post[0]
        res["jsonl"]["post_resume_n_points"] = len(post)
        res["jsonl"]["post_resume_last_step"] = post[-1]["current_steps"]

    # ---------- 2) LR reverse-derivation on post-resume points ----------
    lr_table = []
    if first_block_end is not None:
        for r in raw[first_block_end:]:
            if "lr" not in r:
                # the trainer's final 100% marker row (step 1803) carries no lr --
                # it is a progress marker, not a metric point. Skip it.
                continue
            st = r["current_steps"]
            lr = r["lr"]
            inv = lr_to_step(lr)
            lr_table.append({
                "step": st, "lr": lr, "lr_from_cosine_at_step": cosine_lr(st),
                "step_reverse_derived_from_lr": round(inv, 3),
                "residual_steps": round(st - inv, 3),
                "epoch": r["epoch"], "epoch_expected_st16": st * 16 / 28842,
                "elapsed": r["elapsed_time"], "remaining_reported": r["remaining_time"],
            })
    res["lr_reverse"] = lr_table
    if lr_table:
        res["lr_reverse_summary"] = {
            "residual_min": min(t["residual_steps"] for t in lr_table),
            "residual_max": max(t["residual_steps"] for t in lr_table),
            "abs_residual_mean": sum(abs(t["residual_steps"]) for t in lr_table) / len(lr_table),
            "note": "residual = logged_step - step_implied_by_lr (via cosine inversion)",
        }
    # key contrast: what lr would step 5 / step 0 have?
    res["lr_landmarks"] = {
        "lr(0)": cosine_lr(0), "lr(5)": cosine_lr(5), "lr(200)": cosine_lr(200),
        "lr(205)": cosine_lr(205),
    }
    if first_block_end is not None:
        res["lr_landmarks"]["observed_first_post_resume_lr"] = raw[first_block_end].get("lr")
        res["lr_landmarks"]["observed_first_post_resume_step"] = raw[first_block_end]["current_steps"]
        res["lr_landmarks"]["observed_last_lr"] = next(
            (r["lr"] for r in reversed(raw) if "lr" in r), None)
        res["lr_landmarks"]["observed_last_lr_step"] = next(
            (r["current_steps"] for r in reversed(raw) if "lr" in r), None)

    # ---------- 3) trainer_state.json log_history (DPO metrics) ----------
    series: dict[int, dict] = {}
    src = {}
    for ck in sorted(OUT.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1])):
        ts = ck / "trainer_state.json"
        if not ts.exists():
            continue
        st = json.loads(ts.read_text(encoding="utf-8"))
        src[ck.name] = {
            "global_step": st.get("global_step"),
            "epoch": st.get("epoch"),
            "n_log_history": len(st.get("log_history", [])),
            "best_metric": st.get("best_metric"),
            "max_steps": st.get("max_steps"),
            "mtime": ts.stat().st_mtime,
        }
        for e in st.get("log_history", []):
            if "step" not in e:
                continue
            if "rewards/chosen" in e or "loss" in e:
                series.setdefault(int(e["step"]), {}).update(e)
    res["trainer_state_sources"] = src
    keys = sorted({k for v in series.values() for k in v})
    res["log_history_keys"] = keys

    rows = []
    for s in sorted(series):
        e = series[s]
        rows.append({
            "step": s,
            "loss": e.get("loss"),
            "acc": e.get("rewards/accuracies"),
            "margins": e.get("rewards/margins"),
            "chosen": e.get("rewards/chosen"),
            "rejected": e.get("rewards/rejected"),
            "logps_chosen": e.get("logps/chosen"),
            "logps_rejected": e.get("logps/rejected"),
            "grad_norm": e.get("grad_norm"),
            "lr": e.get("learning_rate"),
            "epoch": e.get("epoch"),
        })
    res["dpo_series"] = rows

    # ---------- 4) early-stop rule, item by item ----------
    es = {"rule": "rewards/accuracies >= 0.97 for 5 CONSECUTIVE logging points AND rewards/margins >= 2x over that same span",
          "acc_ge_097_steps": [], "longest_consecutive_run": 0, "longest_run_steps": [],
          "margins_doubling": None, "triggered": False, "distances": {}}
    thr = [r for r in rows if r["acc"] is not None and r["acc"] >= 0.97]
    es["acc_ge_097_steps"] = [{"step": r["step"], "acc": r["acc"]} for r in thr]
    # consecutive runs (logging points are 5 apart)
    best_run, best_steps, cur_run, cur_steps = 0, [], 0, []
    prev = None
    for r in rows:
        if r["acc"] is not None and r["acc"] >= 0.97:
            if prev is not None and r["step"] - prev == 5:
                cur_run += 1
                cur_steps.append(r["step"])
            else:
                cur_run, cur_steps = 1, [r["step"]]
            if cur_run > best_run:
                best_run, best_steps = cur_run, list(cur_steps)
            prev = r["step"]
        else:
            prev = None
    es["longest_consecutive_run"] = best_run
    es["longest_run_steps"] = best_steps
    if rows:
        first, last = rows[0], rows[-1]
        es["margins_doubling"] = {
            "first_step": first["step"], "first_margins": first["margins"],
            "last_step": last["step"], "last_margins": last["margins"],
            "ratio": (last["margins"] / first["margins"]) if first["margins"] else None,
            "doubled": bool(first["margins"] and last["margins"] and last["margins"] >= 2 * first["margins"]),
        }
        mx = max(r["acc"] for r in rows if r["acc"] is not None)
        es["distances"] = {
            "peak_acc": mx, "peak_acc_distance_to_0.97": round(mx - 0.97, 4),
            "consecutive_points_needed": 5, "consecutive_points_achieved": best_run,
            "consecutive_points_short_by": max(0, 5 - best_run),
            "steps_short_by": max(0, 5 - best_run) * 5,
            "n_points_total": len(rows),
            "n_points_above_health_band_0.85": sum(1 for r in rows if r["acc"] is not None and r["acc"] > 0.85),
            "last_acc": rows[-1]["acc"],
            "last_acc_distance_to_0.97": round(rows[-1]["acc"] - 0.97, 4),
        }
    es["triggered"] = bool(best_run >= 5 and es["margins_doubling"] and es["margins_doubling"]["doubled"])
    res["early_stop"] = es

    # ---------- 5) chosen/rejected separation diagnosis ----------
    diag = {}
    if rows:
        f, l = rows[0], rows[-1]
        if f["chosen"] is not None and l["chosen"] is not None:
            dc = l["chosen"] - f["chosen"]
            dr = l["rejected"] - f["rejected"]
            diag = {
                "step_first": f["step"], "step_last": l["step"],
                "chosen": [f["chosen"], l["chosen"]], "delta_chosen": dc,
                "rejected": [f["rejected"], l["rejected"]], "delta_rejected": dr,
                "ratio_abs_drej_over_dcho": (abs(dr) / abs(dc)) if dc else None,
                "acc": [f["acc"], l["acc"]],
                "margins": [f["margins"], l["margins"]],
                "verdict": ("both sides move in DPO-expected direction => preference separation"
                            if dc > 0 and dr < 0 else
                            "chosen flat/down + rejected collapse => pure suppression"
                            if dr < 0 and dc <= 0.15 * abs(dr) else
                            "both down => hollow refusal"
                            if dc < 0 and dr < 0 else "mixed"),
                "mid_window_chosen_min": min(r["chosen"] for r in rows if r["chosen"] is not None),
                "mid_window_chosen_min_step": min(
                    (r for r in rows if r["chosen"] is not None), key=lambda r: r["chosen"])["step"],
                "rejected_min": min(r["rejected"] for r in rows if r["rejected"] is not None),
                "rejected_min_step": min(
                    (r for r in rows if r["rejected"] is not None), key=lambda r: r["rejected"])["step"],
            }
    res["separation_diagnosis"] = diag
    res["separation_diagnosis"]["ENDPOINT_WARNING"] = (
        "This block compares the FIRST and LAST logging point only. Endpoint ratios are "
        "NOT stable identifiers of the composition: on this run the same statistic reads "
        "33x at step 300 and 2.4x at step 400. For any claim, use the window means / OLS "
        "slopes in m3-dpo-resume-watchdog-E-windows.json and "
        "m3-dpo-resume-watchdog-G-stats.json instead.")

    (R / "m3-dpo-resume-watchdog-A.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- console ----------
    print("== 1) trainer_log.jsonl ==")
    print("  n_lines", res["jsonl"]["n_lines"], "dupes", res["jsonl"]["duplicate_steps"])
    if first_block_end is not None:
        print("  pre-kill block last step :", res["jsonl"]["pre_kill_block_last_step"])
        print("  post-resume FIRST step   :", res["jsonl"]["post_resume_first_step"])
        print("  post-resume last step    :", res["jsonl"]["post_resume_last_step"],
              f"({res['jsonl']['post_resume_n_points']} pts)")
        print("  first post-resume line   :", json.dumps(res["jsonl"]["post_resume_first_line"], ensure_ascii=False))
    print("\n== 2) LR reverse-derivation (post-resume) ==")
    print(f"  {'step':>5} {'lr':>14} {'lr(cos,step)':>14} {'step_from_lr':>13} {'resid':>7} {'epoch_exp':>10}")
    for t in lr_table:
        print(f"  {t['step']:>5} {t['lr']:>14.10g} {t['lr_from_cosine_at_step']:>14.10g} "
              f"{t['step_reverse_derived_from_lr']:>13.2f} {t['residual_steps']:>7.2f} {t['epoch_expected_st16']:>10.6f}")
    print("  landmarks:", json.dumps(res["lr_landmarks"], indent=1))
    print("\n== 3) trainer_state sources ==")
    for k, v in src.items():
        print(f"  {k}: global_step={v['global_step']} epoch={v['epoch']} n_log_history={v['n_log_history']} max_steps={v['max_steps']}")
    print("\n== 4) DPO series (trainer_state log_history) ==")
    print(f"  {'step':>5} {'acc':>7} {'margins':>9} {'chosen':>9} {'rejected':>9} {'loss':>8}")
    for r in rows:
        print(f"  {r['step']:>5} {r['acc']:>7.4f} {r['margins']:>9.4f} {r['chosen']:>9.4f} "
              f"{r['rejected']:>9.4f} {r['loss']:>8.4f}")
    print("\n== 5) early stop ==")
    print(json.dumps(es, ensure_ascii=False, indent=1))
    print("\n== 6) separation ==")
    print(json.dumps(diag, ensure_ascii=False, indent=1))
    print("\nWROTE", R / "m3-dpo-resume-watchdog-A.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
