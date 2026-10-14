# -*- coding: utf-8 -*-
"""载体普查：训练混料里到底出现过哪些**载体类型/族**（S0.6 前置，只读）。

## 为什么必须先做这个
`docs/06 §7` 把 `tool_output` 定为"永不入 SFT 的留出族"，但 `gen_t14_authinject.py`
恰恰生成 `carrier type="tool_output"` 的训练样本（2,500 行），于是 G1 的"未见载体"
断言失效（reports/review-2026-09-30.md §4.4）。要重建一个**真·未见载体**泛化集，
必须先有一份**可信的"已见载体"清单**——而不是凭设计文档推断。

本脚本扫训练用 jsonl + 暂存族，统计：
  * `carrier type="X"` 出现次数（载体类型的客观证据）
  * 行数、id 族前缀（t1..t14 / f* / E* 等）、语言、policy pack
输出 JSON + 一张表。用法：
  python scripts/carrier_census.py [--files ...] [--out reports/carrier-census.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "reports"
# 注意：数据以 JSON 行存储，引号被转义为 \"（2026-09-30 诊断确认）。
# 正则必须同时匹配 `carrier type="x"` 与 `carrier type=\"x\"`。
CARRIER_RE = re.compile(r'carrier\s+type=\\*"([A-Za-z_]+)\\*"')
ID_RE = re.compile(r"^([A-Za-z]+[-_]?\d*)")


def scan(path: Path) -> dict:
    rows = 0
    rows_with_carrier = 0
    carriers = collections.Counter()
    families = collections.Counter()
    langs = collections.Counter()
    packs = collections.Counter()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        rows += 1
        hits = CARRIER_RE.findall(line)
        if hits:
            rows_with_carrier += 1
        for h in hits:
            carriers[h] += 1
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = str(d.get("id", ""))
        if sid:
            families[ID_RE.match(sid).group(1) if ID_RE.match(sid) else sid[:6]] += 1
        lang = d.get("lang") or d.get("language")
        if lang:
            langs[lang] += 1
        pk = d.get("pack") or d.get("policy_pack")
        if pk:
            packs[pk] += 1
    return {"path": str(path.relative_to(ROOT)), "rows": rows,
            "rows_with_carrier": rows_with_carrier,
            "carriers": dict(carriers.most_common()),
            "families": dict(families.most_common(30)),
            "langs": dict(langs.most_common()), "packs": dict(packs.most_common())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=None,
                    help="默认：训练混料 + 暂存族")
    ap.add_argument("--out", default="reports/carrier-census.json")
    args = ap.parse_args()
    if args.files:
        files = [Path(f) for f in args.files]
    else:
        files = [ROOT / "data" / "lf" / "sft_m25.jsonl"]
        files += sorted((ROOT / "data" / "sft" / "m2.5-staging").glob("*.jsonl"))
    rep = {"files": []}
    for f in files:
        if not f.exists():
            print(f"[skip] {f} (missing)")
            continue
        try:
            rep["files"].append(scan(f))
        except Exception as exc:  # 只读普查不应中断整体
            print(f"[error] {f}: {exc}")
            rep["files"].append({"path": str(f), "error": str(exc)})
    # 汇总"已见载体"
    seen = collections.Counter()
    for blk in rep["files"]:
        for k, v in (blk.get("carriers") or {}).items():
            seen[k] += v
    rep["seen_carriers_total"] = dict(seen.most_common())
    rep["note"] = ("seen_carriers_total 是训练侧（含暂存）出现过的载体类型；"
                   "泛化留出集必须使用**不在此表**的载体类型。")
    print(f"{'file':56} {'rows':>8} {'w/carrier':>9}  carriers")
    for blk in rep["files"]:
        if blk.get("error"):
            print(f"{blk['path']:56} {'-':>8} {'-':>9}  ERROR {blk['error']}")
            continue
        print(f"{blk['path']:56} {blk['rows']:>8} "
              f"{blk.get('rows_with_carrier', 0):>9}  "
              f"{json.dumps(blk['carriers'], ensure_ascii=False)}")
    print()
    print("已见载体合计：", json.dumps(rep["seen_carriers_total"], ensure_ascii=False))
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"report -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
