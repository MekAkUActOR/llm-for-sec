# -*- coding: utf-8 -*-
"""汇总提示格式 A/B 的判分结果（对照标签分布）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "reports" / "ab-promptformat"
KEYS = ("asr", "labels", "n", "n_missing", "counts", "label_counts",
        "fmt_err", "refusal_rate", "summary", "metrics")


def main() -> int:
    files = sorted(D.glob("resp-*.scored.json"))
    if not files:
        print("无判分结果")
        return 1
    if len(sys.argv) > 1 and sys.argv[1] == "--dump":
        print(json.dumps(json.loads(files[0].read_text(encoding="utf-8")),
                         ensure_ascii=False, indent=2)[:4000])
        return 0
    print(f"{'模型/格式':30} {'asr':>7} {'n':>4}  labels")
    print("-" * 74)
    for f in files:
        j = json.loads(f.read_text(encoding="utf-8"))
        name = f.name.replace("resp-", "").replace(".scored.json", "")
        lab = j.get("label_distribution")
        asr = (j.get("metrics") or {}).get("asr", j.get("asr"))
        fmt = (j.get("metrics") or {}).get("format_error_rate")
        print(f"{name:30} {str(asr):>7} {str(j.get('n')):>4}  "
              f"fmt={fmt}  {json.dumps(lab, ensure_ascii=False) if lab else '(无)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
