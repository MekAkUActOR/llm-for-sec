# -*- coding: utf-8 -*-
"""自检：topup_verdict.needle() 的读数必须与 longctx 报告逐值一致。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
from topup_verdict import needle  # noqa: E402

for t in ("m25full", "m2full", "m15", "m2calib", "m16"):
    p = ROOT / "reports" / f"longctx-{t}.json"
    if not p.exists():
        print(f"{t:9} 无报告")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    cnt = d.get("needle_counts")
    if isinstance(cnt, dict):
        k = sum(c["k"] for lens in cnt.values() for c in lens.values())
        n = sum(c["n"] for lens in cnt.values() for c in lens.values())
        shape = f"needle_counts 直读 {k}/{n}"
    else:
        shape = ("旧口径 needle_success="
                 + json.dumps(d.get("needle_success"), ensure_ascii=False)[:80])
    fk, fn = needle(t)
    flag = "OK" if (isinstance(cnt, dict) and (fk, fn) == (k, n)) or not isinstance(cnt, dict) else "MISMATCH"
    print(f"{t:9} helper={fk}/{fn} ({fk/fn:.3f})  | {shape}  [{flag}]")
