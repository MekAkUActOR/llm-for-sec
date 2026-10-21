# -*- coding: utf-8 -*-
"""runpoint 变体生成（⑪ suppression A/B：two-band vs strong-too）。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from m6_acceptance import now  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--suppression", required=True, choices=["two-band", "strong-too"])
    args = ap.parse_args()

    d = json.loads(Path(args.base).read_text(encoding="utf-8"))
    d["runpoint_id"] = f"{d['runpoint_id']}-{args.suppression}"
    d["created"] = now()
    d["ood"] = dict(d.get("ood") or {})
    d["ood"]["suppression"] = args.suppression
    d["notes"] = (d.get("notes") or "") + f"；suppression 变体（⑪ A/B）：{args.suppression}"
    Path(args.out).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"变体 runpoint -> {args.out}（suppression={args.suppression}）")


if __name__ == "__main__":
    main()
