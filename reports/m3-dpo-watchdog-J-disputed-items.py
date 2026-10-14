# -*- coding: utf-8 -*-
"""M3 DPO watchdog J: 跨全部档位逐字打印关键争议条目（决定 strict 口径结论的那几条）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
sys.path.insert(0, str(ROOT / "scripts"))
import score_heldout_v2 as S  # noqa: E402

TAGS = [p.name[len("resp-chat-to-"):-len(".jsonl")].strip()
        for p in sorted(R.glob("resp-chat-to-*.jsonl"))]

ids = sys.argv[1].split(",") if len(sys.argv) > 1 else ["to-a-06"]

items = {}
with (ROOT / "data" / "heldout" / "v0.4-toolout" / "tool_output.jsonl").open(
        encoding="utf-8") as f:
    for line in f:
        if line.strip():
            d = json.loads(line)
            items[d["id"]] = d

resp = {}
for tag in TAGS:
    resp[tag] = {}
    for line in (R / f"resp-chat-to-{tag}.jsonl").read_text(
            encoding="utf-8-sig").splitlines():
        if line.strip():
            o = json.loads(line)
            resp[tag][o["id"]] = o.get("text", "")

for iid in ids:
    print("=" * 100)
    print("ID", iid, "| kind", items[iid]["kind"], "| lang", items[iid]["language"])
    print("INTENT:", items[iid]["intent"][:260])
    print("QUERY (tail 400):", repr(items[iid]["query"][-400:]))
    for tag in TAGS:
        t = resp[tag].get(iid, "")
        sr = S.classify(t)
        st = S.classify(t, "strict")
        print(f"\n--- {tag} | selfreport={sr['label']} | strict={st['label']}")
        print(t.strip()[:560])
    print()
