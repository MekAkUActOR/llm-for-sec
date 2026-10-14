# -*- coding: utf-8 -*-
"""核实 objective ① 的"needle **每格 ≥16**"是否达成——**实测**，不读脚本注释。

口径（实测所得，`reports/longctx-*.json` 的 `needle` 字段结构）：
    needle[length][lang][f"{depth}#{variant}"] = {code, success, insert_pos, prompt_len, generated}
  ⇒ **格 = (length × lang)**；每格 trials = depths × variants。
  objective ① 要求"每格 ≥16"，即 **每个 (length, lang) 格 ≥16 次试次**。
"""
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

rows = []
for f in sorted(glob.glob(str(ROOT / "reports" / "longctx-*.json"))):
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    nd = d.get("needle")
    if not isinstance(nd, dict):
        continue
    per_cell = {}
    tot = suc = 0
    for length, langs in nd.items():
        if not isinstance(langs, dict):
            continue
        for lang, trials in langs.items():
            if not isinstance(trials, dict):
                continue
            per_cell[(length, lang)] = len(trials)
            for t in trials.values():
                tot += 1
                if isinstance(t, dict) and t.get("success"):
                    suc += 1
    if per_cell:
        rows.append((Path(f).name, per_cell, tot, suc))

print(f"{'报告':<38} {'格数':>4} {'最小格':>7} {'最大格':>7} {'总试次':>7} "
      f"{'成功':>5} {'needle':>8} {'每格≥16':>8}")
print("-" * 96)
for name, per_cell, tot, suc in rows:
    mn, mx = min(per_cell.values()), max(per_cell.values())
    rate = suc / tot if tot else 0
    ok = "✓" if mn >= 16 else "✗"
    print(f"{name:<38} {len(per_cell):>4} {mn:>7} {mx:>7} {tot:>7} {suc:>5} "
          f"{rate:>8.3f} {ok:>8}")

print("\n逐格明细（最新 3 份报告）：")
for name, per_cell, tot, suc in rows[-3:]:
    print(f"  {name}: " + "  ".join(f"{k[0]}/{k[1]}={v}" for k, v in sorted(per_cell.items())))
