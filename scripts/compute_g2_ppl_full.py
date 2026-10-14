# -*- coding: utf-8 -*-
"""G2 双轨（PPL）正确计算：按 domains 结构逐域对比 m3-dpo 对 soup-a050。"""
import json
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")


def load(tag):
    p = R / f"ppl-{tag}-v0.4.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


base = load("soup-a050")
var = load("m3-dpo")
if not base or not var:
    raise SystemExit("缺 PPL 产物")

bd = base["domains"]
vd = var["domains"]
print("=== 各域 PPL（v0.4）===")
print(f"{'域':<26} {'soup-a050':>10} {'m3-dpo':>10} {'增量%':>9}  {'绝对%(vs 族入口)':>16}")
for k in sorted(set(bd) | set(vd)):
    b = bd.get(k, {}).get("ppl")
    v = vd.get(k, {}).get("ppl")
    if b is None or v is None:
        print(f"{k:<26} {b if b else '-':>10} {v if v else '-':>10}")
        continue
    inc = (v - b) / b * 100
    flag = "★FAIL" if inc > 10 else "ok"
    print(f"{k:<26} {b:>10.3f} {v:>10.3f} {inc:>+8.2f}%  {flag}")

print("\n=== G2 判定（增量 ≤+10%）===")
worst = 0.0
for k in sorted(set(bd) & set(vd)):
    b = bd[k].get("ppl")
    v = vd[k].get("ppl")
    if b and v:
        inc = (v - b) / b * 100
        worst = max(worst, inc)
print(f"  最差域增量 = {worst:+.2f}%  ⇒ {'PASS' if worst <= 10 else '★FAIL'}")
print("\n注：G2 亦要求绝对上限（en ≤+18% / zh ≤+25%，相对'族入口'基线）；")
print("    族入口值需从 m15 的对应域取，见下。")
m15 = load("m15")
if m15:
    md = m15["domains"]
    for k in sorted(set(md) & set(vd)):
        e, v = md[k].get("ppl"), vd[k].get("ppl")
        if e and v:
            print(f"  {k:<26} 族入口 {e:.3f} → m3 {v:.3f} = {(v-e)/e*100:+.2f}%")
print("\nG2-PPL-FULL=DONE")
