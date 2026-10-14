# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog O: wall-clock / GPU-time accounting across the kill+resume.

The log is UTF-16LE with BOM (PowerShell Tee-Object default), so decode accordingly.
Reads checkpoints/qwen3-06b-sec-m3-dpo/trainer_log.jsonl (append-only: the pre-kill
block steps 5..225 and the post-resume block steps 205.. are both in it).

CPU only, read-only.  Writes reports/m3-dpo-resume-watchdog-O-duration.json
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
LOG = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo" / "trainer_log.jsonl"
RUNLOG = ROOT / "reports" / "logs" / "m3-dpo-run.log"


def read_any(p: Path) -> str:
    b = p.read_bytes()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("utf-16", errors="replace")


def secs(t: str) -> float:
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


rows = []
for line in read_any(LOG).splitlines():
    line = line.strip()
    if not line.startswith("{"):
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    if isinstance(d, dict) and "current_steps" in d:
        rows.append(d)

# split into blocks: a new block starts when current_steps does not increase
blocks, cur = [], []
for r in rows:
    if cur and r["current_steps"] <= cur[-1]["current_steps"]:
        blocks.append(cur)
        cur = []
    cur.append(r)
if cur:
    blocks.append(cur)

info = {"n_logged_rows": len(rows), "n_blocks": len(blocks), "blocks": []}
for bi, b in enumerate(blocks):
    step0, step1 = b[0]["current_steps"], b[-1]["current_steps"]
    el0, el1 = secs(b[0]["elapsed_time"]), secs(b[-1]["elapsed_time"])
    n_steps = step1 - step0                      # <- steps, not logging points
    per_step = (el1 - el0) / n_steps if n_steps else None
    total_steps = b[-1].get("total_steps") or 1803
    rep = secs(b[-1]["remaining_time"]) if b[-1].get("remaining_time") else None
    act = (total_steps - step1) * per_step if per_step else None
    # the trainer's very last row reports remaining_time = 0:00:00 (it is the 100%
    # marker), so the ETA comparison must use the last row that still reports a
    # positive remaining time.
    eta_row = next((r for r in reversed(b)
                    if r.get("remaining_time") and secs(r["remaining_time"]) > 0), None)
    eta_rep = eta_act = eta_fac = None
    if eta_row and per_step:
        eta_rep = secs(eta_row["remaining_time"])
        eta_act = (total_steps - eta_row["current_steps"]) * per_step
        eta_fac = eta_act / eta_rep if eta_rep else None
    # per-row understatement of the self-reported ETA vs the observed average rate
    facs = []
    for r in b:
        try:
            rs = secs(r["remaining_time"])
            es = secs(r["elapsed_time"])
            done = r["current_steps"] - step0
            if rs > 0 and done > 0:
                rate = (es - el0) / done                      # observed s/step so far
                act_r = (total_steps - r["current_steps"]) * rate
                facs.append((act_r / rs, r["current_steps"]))
        except Exception:
            pass
    info["blocks"].append({
        "block": bi,
        "first_step": step0, "last_step": step1,
        "elapsed_first": b[0]["elapsed_time"], "elapsed_last": b[-1]["elapsed_time"],
        "elapsed_last_seconds": el1,
        "n_steps_covered": n_steps,
        "implied_seconds_per_step": per_step,
        "remaining_time_reported_at_last": b[-1].get("remaining_time"),
        "remaining_time_actual_at_last_seconds": act,
        "remaining_time_understatement_factor": (act / rep) if (rep and act) else None,
        "eta_row_step": eta_row["current_steps"] if eta_row else None,
        "eta_row_reported": eta_row["remaining_time"] if eta_row else None,
        "eta_row_actual_seconds": eta_act,
        "eta_row_understatement_factor": eta_fac,
        "remaining_time_factor_range": ([min(f for f, _ in facs), max(f for f, _ in facs)]
                                        if facs else None),
        "total_steps": total_steps,
        "epoch_at_last": b[-1].get("epoch"),
        "last_loss": b[-1].get("loss"), "last_accuracy": b[-1].get("accuracy"),
        "last_lr": b[-1].get("lr"),
    })

# wall clock from the run log (Resuming training lines) and the log file mtime
wall = {}
if RUNLOG.exists():
    txt = read_any(RUNLOG)
    for pat, key in [(r"Resuming training from [^\s]*checkpoint-(\d+)", "resume_from_ckpt"),
                     (r"(\d{2}:\d{2}:\d{2})", "first_clock")]:
        m = re.search(pat, txt)
        if m:
            wall[key] = m.group(1) if m.lastindex else m.group(0)
    wall["run_log_bytes"] = RUNLOG.stat().st_size
    wall["run_log_mtime"] = RUNLOG.stat().st_mtime
    for kw in ("Resuming training from", "global step", "Training completed",
               "train_runtime", "train_samples_per_second"):
        for line in txt.splitlines():
            if kw in line:
                wall.setdefault("matched:" + kw, line.strip()[:160])

info["wall"] = wall
(R / "m3-dpo-resume-watchdog-O-duration.json").write_text(
    json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(json.dumps(info, ensure_ascii=False, indent=1))
print("WROTE", R / "m3-dpo-resume-watchdog-O-duration.json")
