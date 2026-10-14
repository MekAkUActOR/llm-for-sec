"""READ-ONLY: pair the probe (max_steps=300) and the full run at identical logged steps.

If seeds/data order match, the two trajectories should coincide exactly through step 300;
that decides whether the probe is a valid predictor of this run's early trajectory.
"""
import json
import os

ROOT = r"J:\Projects\llm_for_sec"
PROBE = os.path.join(ROOT, "checkpoints", "qwen3-06b-sec-m4-capfix-probe", "checkpoint-300", "trainer_state.json")
FULL = os.path.join(ROOT, "checkpoints", "qwen3-06b-sec-m4-capfix-full", "checkpoint-400", "trainer_state.json")


def load(p):
    with open(p, "r", encoding="utf-8") as fh:
        st = json.load(fh)
    out = {}
    for e in st.get("log_history", []):
        if "rewards/chosen" in e and "step" in e:
            out[int(e["step"])] = e
    return out


def main():
    a, b = load(PROBE), load(FULL)
    steps = sorted(set(a) & set(b))
    print(f"paired logged steps: {len(steps)}  (probe {min(steps)}..{max(steps)})")
    print(f"{'step':>5} | {'probeCh':>9} {'fullCh':>9} {'dCh':>8} | {'probeRj':>9} {'fullRj':>9} {'dRj':>8} | {'probeLoss':>9} {'fullLoss':>9}")
    print("-" * 96)
    maxd = 0.0
    for s in steps:
        pc, fc = a[s]["rewards/chosen"], b[s]["rewards/chosen"]
        pr, fr = a[s]["rewards/rejected"], b[s]["rewards/rejected"]
        pl, fl = a[s].get("loss", float("nan")), b[s].get("loss", float("nan"))
        maxd = max(maxd, abs(pc - fc), abs(pr - fr))
        if s % 25 == 0 or s <= 20:
            print(f"{s:>5} | {pc:>+9.4f} {fc:>+9.4f} {fc-pc:>+8.4f} | {pr:>+9.4f} {fr:>+9.4f} {fr-pr:>+8.4f} | {pl:>9.5f} {fl:>9.5f}")
    print("-" * 96)
    print(f"max |delta| across paired steps: {maxd:.6f}")


if __name__ == "__main__":
    main()
