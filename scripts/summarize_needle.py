# -*- coding: utf-8 -*-
"""汇总 longctx 报告的 needle 命中率（支持旧 3/格 与新 16/格 两代口径）。

用法：python scripts/summarize_needle.py [--dir reports] [--tags m25full,m2full,m2calib,m15]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def cell_counts(doc: dict) -> dict:
    """返回 {(lens,lang): (k, n)}；优先用 needle_counts，否则按率×试探数换算。"""
    trials = int(doc.get("needle_trials_per_cell") or 3)
    counts = doc.get("needle_counts") or {}
    out = {}
    for L, per in (doc.get("needle_success") or {}).items():
        if not isinstance(per, dict):
            continue
        for lang, rate in per.items():
            c = (counts.get(L) or {}).get(lang)
            if isinstance(c, dict) and c.get("n"):
                out[(L, lang)] = (int(c["k"]), int(c["n"]))
            else:
                out[(L, lang)] = (int(round(float(rate) * trials)), trials)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="reports")
    ap.add_argument("--tags", default="m25full,m2full,m2calib,m15")
    a = ap.parse_args()
    d = ROOT / a.dir
    print(f"{'tag':10} {'trials/cell':>11} {'needle k/n':>12} "
          f"{'rate':>7}  分格（lens/lang）")
    rows = {}
    for tag in [t.strip() for t in a.tags.split(",") if t.strip()]:
        p = d / f"longctx-{tag}.json"
        if not p.exists():
            print(f"{tag:10} {'-':>11} {'缺文件':>12}")
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        cc = cell_counts(doc)
        k = sum(v[0] for v in cc.values())
        n = sum(v[1] for v in cc.values())
        per_cell = int(doc.get("needle_trials_per_cell") or 3)
        rows[tag] = (k, n, per_cell, cc)
        detail = "  ".join(f"{L}/{lg}={v[0]}/{v[1]}"
                           for (L, lg), v in sorted(cc.items()))
        print(f"{tag:10} {per_cell:>11} {f'{k}/{n}':>12} "
              f"{k / n if n else 0:>7.3f}  {detail}")
    # 新口径下的两两对照（若都有）
    if "m25full" in rows and "m2full" in rows:
        sys.path.insert(0, str(ROOT))
        from secfm.eval.stats import fisher_p
        for base in ("m2full", "m2calib", "m15"):
            if base not in rows:
                continue
            k1, n1 = rows["m25full"][0], rows["m25full"][1]
            k0, n0 = rows[base][0], rows[base][1]
            p = fisher_p(k1, n1 - k1, k0, n0 - k0)
            print(f"  m25full {k1}/{n1} vs {base} {k0}/{n0}: "
                  f"Fisher p={p:.4f} {'可区分' if p < 0.05 else '★未达可区分'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
