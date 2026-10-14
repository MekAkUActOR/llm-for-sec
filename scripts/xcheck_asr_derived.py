# -*- coding: utf-8 -*-
r"""★用**独立字段** `derived.attack_success` 交叉核验 ASR（不依赖 `label` ✗）。

`label` 是判分器的**分类结论** ✓；`derived.attack_success` 是**派生量** ✓。
两者若一致 ⇒ 读数扎实 ✓；若不一致 ⇒ 先查清楚再下结论 ✗。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CANDS = [
    ("起点", "96", "reports/scored-chat-gen-soup-a050-v2.json"),
    ("起点", "512", "reports/scored-chat-gen-soup-a050-v2-mnt512.json"),
    ("M3", "96", "reports/scored-chat-gen-m3-dpo-v2.json"),
    ("M3", "512", "reports/scored-chat-gen-m3-dpo-v2-mnt512.json"),
]


def main() -> int:
    print("=== 鲁棒性集：label=comply 与 derived.attack_success 双路核验 ===")
    print(f"  {'模型':<6} {'口径':>5} {'n':>5} {'label comply':>13} {'ASR_label':>10} "
          f"{'ASR_derived':>12} {'一致?':>6}")
    rows = []
    for name, cal, rel in CANDS:
        p = ROOT / rel
        if not p.exists():
            print(f"  ★缺 {rel}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        sub = [x for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"]
        n = len(sub)
        kc = sum(1 for x in sub if str(x.get("label")) == "comply")
        vals = [x["derived"]["attack_success"] for x in sub
                if isinstance(x.get("derived"), dict)
                and isinstance(x["derived"].get("attack_success"), (int, float))]
        m = statistics.fmean(vals) if vals else float("nan")
        same = "✓" if (vals and abs(m - kc / n) < 0.06) else "✗"
        print(f"  {name:<6} {cal:>5} {n:>5} {kc:>13} {kc/n:>10.1%} {m:>12.1%} {same:>6}")
        rows.append({"model": name, "caliber": cal, "n": n, "comply": kc,
                     "asr_label": kc / n, "asr_derived": m})

    print("\n★读法：两路若一致 ⇒ ASR 读数**与判分器分类口径无关** ✓ ⇒ 结论扎实 ✓")
    print("  ★若起点跨口径稳定、而 M3 跨口径暴增 ⇒")
    print("    该暴增**不是判分器口径变化造成的** ✓，而是**响应内容真的变了** ✗")
    out = ROOT / "reports" / "asr-caliber-verification.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n一 -> {out.name}")
    print("ASR-XCHECK=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
