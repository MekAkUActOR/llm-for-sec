# -*- coding: utf-8 -*-
"""_tmp_m5a_r9_sha_check.py - M5A-R9 frozen-instrument sha re-verification (one-shot probe).

r9 gates chain pre-launch gate (run_m5a_r9_gates.ps1 Step 0):
  four frozen instruments byte-identical to r6/r7/r8 (zero scorer/data drift);
  this round training config configs/m5a-dpo-r9.yaml = r8 copy + 6 functional-line diff
  (lora_rank 16->64 / lora_alpha 32->128 / max_steps 300->1200 / dataset_dir m5a-r9-run /
   dataset r9 names / output_dir r9; see configs/m5a-dpo-r9.yaml header).
  New sha registered below. fail-closed: any mismatch -> rc=1.
Whole-file rewrite (errata discipline: no string surgery).
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")

CHECKS = [
    # (relpath, sha256 first 16 hex, last 8 hex)
    ("scripts/probe_jailbreak.py", "6cd4390f7848719b", "20a6881b"),
    ("scripts/score_heldout_v2.py", "83d50c8bfb8a500e", "52bcb1da"),
    ("data/heldout/v0.7-jailbreak/jailbreak.jsonl", "cbad0fed25d3490b", "20f816cb"),
    ("data/heldout/v0.6-dilution/risk_payloads.jsonl", "c6eabceecdffa05f", "fd5ef09f"),
    # r9 training config (r8 copy + 6-line diff, registered in configs/m5a-dpo-r9.yaml header)
    ("configs/m5a-dpo-r9.yaml", "289e6b1a14a625ac", "34cf502d"),
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ok = True
    for rel, pre, suf in CHECKS:
        p = ROOT / rel
        if not p.is_file():
            print(f"[MISS] {rel}: file not found")
            ok = False
            continue
        full = sha256_file(p)
        match = full.startswith(pre) and full.endswith(suf)
        print(f"[{'OK' if match else 'BAD'}] {rel}: {full[:16]}...{full[-8:]}")
        if not match:
            ok = False
    print("INSTRUMENT-SHA=" + ("PASS" if ok else "FAIL")
          + " (jb scorer / heldout scorer / jb suite / dilution pool / r9 config)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
