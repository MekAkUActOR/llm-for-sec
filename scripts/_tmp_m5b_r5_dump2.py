# -*- coding: utf-8 -*-
"""M5B-R5 one-off #2: selfreport benign ORR + gen-ASR miss turnover vs v4 (read-only)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T5 = "m5b-p2rl-grpo-v5"
T4 = "m5b-p2rl-grpo-v4"

for tag in (T5, T4):
    d = json.loads((ROOT / f"reports/logs/m5g-readings-m5b-r4-full.log").read_text(encoding="utf-16")) if tag == T4 else None
    if d:
        print(f"[{tag}] selfreport.benign:", json.dumps(d["jb"]["selfreport"]["benign"]))
        print(f"[{tag}] tiered.benign:", json.dumps(d["jb"]["tiered"]["benign"]))

d5 = json.loads((ROOT / "reports/logs/m5g-readings-m5b-r5-full.log").read_text(encoding="utf-16"))
print(f"[{T5}] selfreport.benign:", json.dumps(d5["jb"]["selfreport"]["benign"]))
print(f"[{T5}] tiered.benign:", json.dumps(d5["jb"]["tiered"]["benign"]))


def miss_ids(tag):
    p = ROOT / f"reports/scored-chat-gen-{tag}-v2-mnt512.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for it in d["items"]:
        if it.get("kind") == "robustness" and it.get("responded"):
            if (it.get("derived") or {}).get("attack_success"):
                out[it["id"]] = True
    return set(out)


m5, m4 = miss_ids(T5), miss_ids(T4)
print(f"\nASR miss v5 = {len(m5)}: {sorted(m5)}")
print(f"ASR miss v4 = {len(m4)}: {sorted(m4)}")
print(f"kept (v4&v5): {len(m5 & m4)}: {sorted(m5 & m4)}")
print(f"new in v5: {len(m5 - m4)}: {sorted(m5 - m4)}")
print(f"fixed in v5: {len(m4 - m5)}: {sorted(m4 - m5)}")
av = [i for i in (m5 - m4) if "-av-" in i]
img = [i for i in (m5 - m4) if "-img-" in i]
print(f"new av: {len(av)} {av}")
print(f"new img: {len(img)} {img}")
