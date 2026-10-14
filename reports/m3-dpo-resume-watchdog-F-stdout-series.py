# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog F: parse the DPO metric dicts out of the trainer stdout
logs (they ARE there -- block-buffered, lagging) and use them to
 (a) extend the rewards/* series past the last checkpoint,
 (b) calibrate run-to-run noise on the SAME batch via the 5 steps that were
     logged twice (pre-kill and post-resume: 205,210,215,220,225).

CPU only, read-only. Writes reports/m3-dpo-resume-watchdog-F-stdout-series.csv/.json
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
LOGS = {
    "pre_kill_original": ROOT / "reports" / "logs" / "m3-dpo-launch.log",
    "resume_tee_run": ROOT / "reports" / "logs" / "m3-dpo-run.log",
    "resume_console": ROOT / "reports" / "logs" / "m3-dpo-resume-launch.log",
}
DICT_RE = re.compile(r"^\{'loss':")


def read_any(path: Path) -> str:
    """The emitter's Tee-Object writes UTF-16LE (ff fe BOM) in PS 5.1."""
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8-sig", "gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_log(path: Path) -> list[dict]:
    rows = []
    for ln, line in enumerate(read_any(path).splitlines(), 1):
        s = line.strip()
        if not DICT_RE.match(s):
            continue
        try:
            o = ast.literal_eval(s)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        rec = {"src": path.name, "lineno": ln}
        for k in ("loss", "grad_norm", "learning_rate", "rewards/chosen", "rewards/rejected",
                  "rewards/accuracies", "rewards/margins", "logps/chosen", "logps/rejected",
                  "logits/chosen", "logits/rejected", "epoch"):
            v = o.get(k)
            try:
                rec[k.replace("/", "_")] = float(v)
            except (TypeError, ValueError):
                rec[k.replace("/", "_")] = None
        rows.append(rec)
    return rows


def main() -> int:
    out: dict = {"logs": {}}
    seqs: dict[str, list[dict]] = {}
    for tag, p in LOGS.items():
        if not p.exists():
            out["logs"][tag] = {"exists": False}
            continue
        rows = parse_log(p)
        seqs[tag] = rows
        steps = [round(r["epoch"] * 28842 / 16) for r in rows]
        out["logs"][tag] = {
            "path": str(p), "exists": True, "n_dict_lines": len(rows),
            "size": p.stat().st_size,
            "implied_steps_first_last": (steps[0], steps[-1]) if steps else None,
            "first_line": rows[0] if rows else None,
            "last_line": rows[-1] if rows else None,
        }

    # Prefer the console log (most complete) for the continuous series, but merge by step.
    merged: dict[int, dict] = {}
    for tag in ("pre_kill_original", "resume_console", "resume_tee_run"):
        for r in seqs.get(tag, []):
            st = round(r["epoch"] * 28842 / 16)
            merged.setdefault(st, {}).setdefault(tag, r)
    out["merged_steps"] = sorted(merged)

    # --- (b) same-batch reproducibility: steps logged by BOTH segments ---
    pairs = []
    for st in sorted(merged):
        d = merged[st]
        a = d.get("pre_kill_original")
        b = d.get("resume_console") or d.get("resume_tee_run")
        if a and b:
            pairs.append({
                "step": st,
                "d_loss": b["loss"] - a["loss"],
                "d_chosen": b["rewards_chosen"] - a["rewards_chosen"],
                "d_rejected": b["rewards_rejected"] - a["rewards_rejected"],
                "d_acc": b["rewards_accuracies"] - a["rewards_accuracies"],
                "d_margins": b["rewards_margins"] - a["rewards_margins"],
                "pre": {k: a[k] for k in ("loss", "rewards_chosen", "rewards_rejected",
                                          "rewards_accuracies", "rewards_margins")},
                "post": {k: b[k] for k in ("loss", "rewards_chosen", "rewards_rejected",
                                           "rewards_accuracies", "rewards_margins")},
            })
    out["same_batch_pairs"] = pairs
    if pairs:
        for k in ("d_loss", "d_chosen", "d_rejected", "d_margins", "d_acc"):
            v = [p[k] for p in pairs]
            out.setdefault("same_batch_noise", {})[k] = {
                "max_abs": max(abs(x) for x in v),
                "mean_abs": sum(abs(x) for x in v) / len(v),
            }

    # --- (a) continuous series CSV (from stdout; may extend past last checkpoint) ---
    csv = ["step,src,loss,grad_norm,lr,acc,margins,chosen,rejected,logps_chosen,logps_rejected"]
    for st in sorted(merged):
        d = merged[st]
        r = d.get("resume_console") or d.get("resume_tee_run") or d.get("pre_kill_original")
        csv.append(",".join(str(x) for x in (
            st, r["src"], r["loss"], r["grad_norm"], r["learning_rate"],
            r["rewards_accuracies"], r["rewards_margins"], r["rewards_chosen"],
            r["rewards_rejected"], r["logps_chosen"], r["logps_rejected"])))
    # --- cross-check: does the stdout channel agree with log_history point by point? ---
    # Two independent capture paths (teed console vs trainer_state.json snapshots). Agreement
    # makes the stdout channel a legitimate real-time view of the SAME quantities, including
    # for steps newer than the newest checkpoint.
    OUT = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo"
    lh = {}
    for ck in sorted(OUT.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1])):
        ts = ck / "trainer_state.json"
        if not ts.exists():
            continue
        try:
            stj = json.loads(ts.read_text(encoding="utf-8"))
        except Exception:
            continue
        for e in stj.get("log_history", []):
            if "rewards/chosen" in e:
                lh[int(e["step"])] = e
    pairs_keys = {"rewards_chosen": "rewards/chosen", "rewards_rejected": "rewards/rejected",
                  "rewards_accuracies": "rewards/accuracies", "rewards_margins": "rewards/margins",
                  "loss": "loss"}
    diffs = {k: [] for k in pairs_keys}
    n_ov = 0
    for stp, per in merged.items():
        row = per.get("resume_console") or per.get("resume_tee_run") or per.get("pre_kill_original")
        if stp in lh and row:
            n_ov += 1
            for sk, lk in pairs_keys.items():
                if row.get(sk) is not None and lh[stp].get(lk) is not None:
                    diffs[sk].append(abs(float(row[sk]) - float(lh[stp][lk])))
    out["stdout_vs_log_history"] = {
        "n_overlapping_steps": n_ov,
        "max_abs_diff": {k: (max(v) if v else None) for k, v in diffs.items()},
        "agree_to_1e-9": all((max(v) if v else 0.0) < 1e-9 for v in diffs.values()),
    }

    # Is every difference explained by the console printing 4 SIGNIFICANT digits?
    # If so, |stdout - log_history| <= half an ULP of %.4g for EVERY step and field.
    import math
    viol = []
    n_checked = 0
    for stp, per in merged.items():
        row = per.get("resume_console") or per.get("resume_tee_run") or per.get("pre_kill_original")
        if stp not in lh or not row:
            continue
        for sk, lk in pairs_keys.items():
            a, b = row.get(sk), lh[stp].get(lk)
            if a is None or b is None or b == 0:
                continue
            n_checked += 1
            ulp = 10.0 ** (math.floor(math.log10(abs(b))) - 3)   # %.4g
            if abs(float(a) - float(b)) > 0.5 * ulp * (1 + 1e-9):
                viol.append({"step": stp, "field": sk, "stdout": a, "log_history": b,
                             "abs_diff": abs(float(a) - float(b)), "half_ulp": 0.5 * ulp})
    out["stdout_vs_log_history"]["rendering_4sigdigits_test"] = {
        "n_values_checked": n_checked,
        "n_violations": len(viol),
        "violations_first5": viol[:5],
        "verdict": ("every difference is explained by the console printing 4 significant "
                    "digits (the two channels are the same numbers, two renderings)"
                    if not viol else "NOT explained by rendering -- investigate"),
    }

    (R / "m3-dpo-resume-watchdog-F-stdout-series.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")
    (R / "m3-dpo-resume-watchdog-F-stdout-series.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    for tag, v in out["logs"].items():
        print(f"{tag:20} exists={v.get('exists')} n_dict_lines={v.get('n_dict_lines')} "
              f"steps={v.get('implied_steps_first_last')}")
    print("\n== same-batch (pre-kill vs post-resume) pairs ==")
    if pairs:
        print(f"  {'step':>5} {'pre_cho':>8} {'post_cho':>9} {'d_cho':>8} "
              f"{'pre_rej':>8} {'post_rej':>9} {'d_rej':>8} {'d_loss':>8}")
        for p in pairs:
            print(f"  {p['step']:>5} {p['pre']['rewards_chosen']:>8} {p['post']['rewards_chosen']:>9} "
                  f"{p['d_chosen']:>+8.4f} {p['pre']['rewards_rejected']:>8} {p['post']['rewards_rejected']:>9} "
                  f"{p['d_rejected']:>+8.4f} {p['d_loss']:>+8.5f}")
        print("\n  same-batch noise (this is run-to-run numerical noise, NOT batch sampling noise):")
        print(json.dumps(out["same_batch_noise"], indent=1))
    print("\nlongest stdout step:", out["merged_steps"][-1] if out["merged_steps"] else None)
    print("WROTE", R / "m3-dpo-resume-watchdog-F-stdout-series.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
