# -*- coding: utf-8 -*-
"""M3 DPO watchdog: extract full DPO observables from checkpoint-*/trainer_state.json
log_history (the only place rewards/margins, logps/chosen, logps/rejected live).
Read-only. Writes reports/m3-dpo-watchdog-dpo-metrics.json and .csv."""
import csv
import glob
import json
import os

ROOT = r"J:\Projects\llm_for_sec"
OUTDIR = os.path.join(ROOT, "checkpoints", "qwen3-06b-sec-m3-dpo")
OUT_JSON = os.path.join(ROOT, "reports", "m3-dpo-watchdog-dpo-metrics.json")
OUT_CSV = os.path.join(ROOT, "reports", "m3-dpo-watchdog-dpo-metrics.csv")

KEYS = ["loss", "rewards/accuracies", "rewards/margins", "rewards/chosen", "rewards/rejected",
        "logps/chosen", "logps/rejected", "logits/chosen", "logits/rejected",
        "learning_rate", "epoch", "grad_norm", "num_tokens"]


def main():
    rows = []
    meta = {}
    for p in sorted(glob.glob(os.path.join(OUTDIR, "checkpoint-*", "trainer_state.json"))):
        with open(p, "r", encoding="utf-8") as f:
            st = json.load(f)
        ck = os.path.basename(os.path.dirname(p))
        meta[ck] = {
            "global_step": st.get("global_step"),
            "epoch": st.get("epoch"),
            "best_metric": st.get("best_metric"),
            "log_history_len": len(st.get("log_history", [])),
            "keys_seen": sorted({k for e in st.get("log_history", []) for k in e.keys()}),
            "mtime": os.path.getmtime(p),
        }
        for e in st.get("log_history", []):
            if "loss" not in e:
                continue
            r = {"ckpt": ck, "step": e.get("step")}
            for k in KEYS:
                r[k] = e.get(k)
            rows.append(r)
    # de-dup by step, keep the entry with the most non-null DPO keys
    best = {}
    for r in rows:
        n = sum(1 for k in KEYS if r.get(k) is not None)
        s = r["step"]
        if s not in best or n > sum(1 for k in KEYS if best[s].get(k) is not None):
            best[s] = r
    rows = [best[s] for s in sorted(best)]
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "rows": rows}, f, ensure_ascii=False, indent=1)
    cols = ["step"] + KEYS
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("META", json.dumps(meta, ensure_ascii=False, indent=1))
    print("steps:", [r["step"] for r in rows])
    print("rows:", len(rows))
    # key question: rejected collapse vs chosen
    if rows:
        f0, f1 = rows[0], rows[-1]
        print("\nFIRST", json.dumps(f0, ensure_ascii=False))
        print("LAST ", json.dumps(f1, ensure_ascii=False))
        for k in ("logps/chosen", "logps/rejected", "rewards/margins", "rewards/accuracies", "loss"):
            a, b = f0.get(k), f1.get(k)
            if a is not None and b is not None:
                print("DELTA %-20s %+ .6f  (%s -> %s)" % (k, b - a, a, b))
    print("WROTE", OUT_JSON, OUT_CSV)


if __name__ == "__main__":
    main()
