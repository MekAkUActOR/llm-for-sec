"""Watchdog extractor for the M4 capfix full DPO run. READ-ONLY.

Usage:
  python m4-watchdog-extract.py [OUTDIR] [REFDIR]

Reads the newest readable checkpoint's trainer_state.json (complete log_history) and,
failing that, the stdout log. Prints windowed means of rewards/chosen, rewards/rejected,
rewards/margins, rewards/accuracies and logps/chosen, logps/rejected. With REFDIR it
prints a side-by-side comparison against a reference run (M3). No GPU, no training.
"""
import glob
import json
import os
import re
import sys

ROOT = r"J:\Projects\llm_for_sec"
OUT = os.path.join(ROOT, "checkpoints", "qwen3-06b-sec-m4-capfix-full")
LOG = os.path.join(ROOT, "reports", "logs", "m4-capfix-full.log")
REF = None
if len(sys.argv) > 1:
    OUT = sys.argv[1]
    LOG = os.path.join(OUT, "__no_stdout_log__")
if len(sys.argv) > 2:
    REF = sys.argv[2]
BIN = 200
TOTAL = 1803


def load_points_from_dir(d):
    """Newest trainer_state.json (run root or a checkpoint) that parses with reward history."""
    cands = []
    for x in glob.glob(os.path.join(d, "checkpoint-*")):
        if os.path.isdir(x):
            cands.append(os.path.join(x, "trainer_state.json"))
    cands.append(os.path.join(d, "trainer_state.json"))
    cands = [p for p in cands if os.path.exists(p)]
    cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for p in cands:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                st = json.load(fh)
        except Exception:
            continue
        pts = [e for e in st.get("log_history", []) if "rewards/chosen" in e and "step" in e]
        if pts:
            lbl = os.path.basename(os.path.dirname(p)) or "root"
            if lbl == "root":
                lbl = os.path.basename(os.path.dirname(os.path.dirname(p))) + "/trainer_state.json"
            return pts, lbl
    return None, None


def from_log():
    if not os.path.exists(LOG):
        return []
    with open(LOG, "r", encoding="utf-8", errors="replace") as fh:
        txt = fh.read()
    pts = []
    for line in txt.splitlines():
        if "rewards/chosen" not in line or "'loss'" not in line:
            continue

        def g(key):
            m = re.search(r"'" + key + r"':\s*'?([-0-9.eE+]+)'?", line)
            return float(m.group(1)) if m else None

        ep = g("epoch")
        rec = {"step": round(ep * TOTAL) if ep is not None else None, "epoch": ep, "loss": g("loss")}
        for k in ("rewards/chosen", "rewards/rejected", "rewards/accuracies", "rewards/margins",
                  "logps/chosen", "logps/rejected", "logits/chosen", "logits/rejected"):
            rec[k] = g(k)
        if rec["rewards/chosen"] is not None:
            pts.append(rec)
    return pts


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def f(v, n=3):
    return "   n/a" if v is None else f"{v:+.{n}f}"


def binrow(pts, lo):
    w = [r for r in pts if lo <= (r.get("step") or 0) < lo + BIN]
    if not w:
        return None
    return {
        "n": len(w),
        "ch": mean([r["rewards/chosen"] for r in w]),
        "rj": mean([r.get("rewards/rejected") for r in w]),
        "mg": mean([r.get("rewards/margins") for r in w]),
        "ac": mean([r.get("rewards/accuracies") for r in w]),
        "lpc": mean([r.get("logps/chosen") for r in w]),
        "lpr": mean([r.get("logps/rejected") for r in w]),
        "minch": min(r["rewards/chosen"] for r in w),
    }


def main():
    pts, src = load_points_from_dir(OUT)
    if pts:
        origin = f"checkpoint {src} trainer_state.json log_history"
    else:
        pts = from_log()
        origin = "stdout log (no checkpoint trainer_state.json yet)"
    if not pts:
        print("NO METRICS YET (still tokenizing or first log line not flushed)")
        return
    pts.sort(key=lambda r: (r.get("step") or 0))
    last = pts[-1]
    print(f"SOURCE: {origin}")
    print(f"logged points: {len(pts)}  span: step {pts[0].get('step')} .. {last.get('step')}")

    refpts = None
    if REF:
        refpts, refck = load_points_from_dir(REF)
        print(f"REFERENCE: {os.path.basename(REF)} checkpoint {refck}")

    hi = (last.get("step") or 0) // BIN * BIN + BIN
    print()
    hdr = (f"{'window':>13} | {'n':>3} | {'chosen':>8} | {'rejected':>9} | {'ratio':>8} | "
           f"{'margin':>8} | {'acc':>6} | {'minCh':>8} | {'logpsCh':>8} | {'logpsRj':>8}")
    print(hdr)
    print("-" * len(hdr))
    for lo in range(0, hi, BIN):
        b = binrow(pts, lo)
        if not b:
            continue
        ratio = "n/a"
        if b["ch"] not in (None, 0) and b["rj"] is not None:
            ratio = f"1:{abs(b['rj'] / b['ch']):.2f}"
        print(f"{lo:>5}-{lo+BIN-1:<7} | {b['n']:>3} | {f(b['ch']):>8} | {f(b['rj']):>9} | {ratio:>8} | "
              f"{f(b['mg']):>8} | {('n/a' if b['ac'] is None else format(b['ac'], '.3f')):>6} | "
              f"{f(b['minch']):>8} | {f(b['lpc'],1):>8} | {f(b['lpr'],1):>8}")

    if refpts:
        print()
        print(f"{'window':>13} | {'REF chosen':>10} | {'REF rejec':>10} | {'dChosen':>8} | {'dRejected':>9}")
        print("-" * 62)
        for lo in range(0, max(hi, 2000), BIN):
            b, r = binrow(pts, lo), binrow(refpts, lo)
            if not b and not r:
                continue
            dch = drj = None
            if b and r:
                dch = None if (b["ch"] is None or r["ch"] is None) else b["ch"] - r["ch"]
                drj = None if (b["rj"] is None or r["rj"] is None) else b["rj"] - r["rj"]
            print(f"{lo:>5}-{lo+BIN-1:<7} | {f(r['ch']) if r else '   n/a':>10} | "
                  f"{f(r['rj']) if r else '   n/a':>10} | {f(dch):>8} | {f(drj):>9}")

    print()
    print("last 6 logged points:")
    for r in pts[-6:]:
        print(f"  step {r.get('step'):>5}  loss={f(r.get('loss'),4)}  chosen={f(r['rewards/chosen'],4)}  "
              f"rejected={f(r.get('rewards/rejected'),4)}  margins={f(r.get('rewards/margins'),4)}  "
              f"acc={r.get('rewards/accuracies')}  logpsCh={f(r.get('logps/chosen'),1)}")
    tail = pts[-20:]
    print()
    print(f"last-20-point mean: chosen={f(mean([r['rewards/chosen'] for r in tail]),4)} "
          f"rejected={f(mean([r.get('rewards/rejected') for r in tail]),4)} "
          f"margins={f(mean([r.get('rewards/margins') for r in tail]),4)} "
          f"acc={mean([r.get('rewards/accuracies') for r in tail]):.4f} "
          f"logpsCh={f(mean([r.get('logps/chosen') for r in tail]),1)}")
    sat = sum(1 for r in pts if (r.get("rewards/accuracies") or 0) >= 0.99)
    print(f"points with acc>=0.99: {sat}/{len(pts)} ({100.0 * sat / len(pts):.2f}%)")
    print(f"first logged point logps/chosen={f(pts[0].get('logps/chosen'),1)} "
          f"rejected={f(pts[0].get('logps/rejected'),1)}")


if __name__ == "__main__":
    main()
