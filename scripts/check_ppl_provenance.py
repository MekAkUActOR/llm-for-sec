# -*- coding: utf-8 -*-
"""核对各 ppl-<tag>-v0.4.json 的测量口径是否可比（max_len / stride / 域 token 数 / 耗时）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in sorted((ROOT / "reports").glob("ppl-*-v0.4.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    doms = d.get("domains") or {}
    tok_total = sum((v or {}).get("tokens", 0) for v in doms.values())
    print(f"{p.name:26} max_len={d.get('max_len')} stride={d.get('stride')} "
          f"elapsed_s={d.get('elapsed_s')} domains={len(doms)} tokens={tok_total:,} "
          f"gen_en={((doms.get('general_en') or {}).get('ppl'))}")
    if len(sys.argv) > 1 and sys.argv[1] == "-v":
        for k, v in sorted(doms.items()):
            print(f"    {k:22} ppl={(v or {}).get('ppl')} tokens={(v or {}).get('tokens')}")
