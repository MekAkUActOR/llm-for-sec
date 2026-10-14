# -*- coding: utf-8 -*-
"""算 m3-dpo 的 G2（PPL 双轨）读数：增量 ≤+10%（vs 上一同类产物）且绝对 ≤+18% en / +25% zh。"""
import json
from collections import OrderedDict
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")


def load(tag, ver="v0.4"):
    for nm in (f"ppl-{tag}-{ver}.json", f"ppl-{tag}.json"):
        p = R / nm
        if p.exists():
            return nm, json.loads(p.read_text(encoding="utf-8"))
    return None, None


tags = ["m15", "m2calib", "soup-a050", "m25full", "m2full", "m3-dpo"]
data = OrderedDict()
for t in tags:
    nm, d = load(t)
    if d:
        data[t] = (nm, d)

print("=== 各臂 PPL（v0.4）===")
for t, (nm, d) in data.items():
    print(f"  {t:<12} ({nm})")
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (int, float)):
                print(f"      {k} = {v}")
            elif isinstance(v, dict):
                print(f"      {k} = {json.dumps(v, ensure_ascii=False)[:180]}")

print("\n=== G2 双轨判定（m3-dpo 对 soup-a050）===")
b = data.get("soup-a050")
v = data.get("m3-dpo")
if b and v:
    bd, vd = b[1], v[1]
    # 找 general_en / general_zh 段
    def seg(doc, key):
        for cand in (key, f"general_{key}"):
            if cand in doc and isinstance(doc[cand], (int, float)):
                return doc[cand]
            if cand in doc and isinstance(doc[cand], dict):
                for kk in ("ppl", "value", "mean"):
                    if kk in doc[cand]:
                        return doc[cand][kk]
        return None

    for lang, abs_cap in (("en", 0.18), ("zh", 0.25)):
        bs, vs = seg(bd, lang), seg(vd, lang)
        if bs is None or vs is None:
            print(f"  general_{lang}: 取不到（键结构需查）")
            continue
        inc = (vs - bs) / bs * 100
        print(f"  general_{lang}: 起点 {bs:.3f} → m3 {vs:.3f}  "
              f"增量 {inc:+.2f}%（阈值 ≤+10%）⇒ {'PASS' if inc <= 10 else '★FAIL'}")
else:
    print("  缺少某一臂的 PPL 产物")

print("\nG2-PPL=DONE")
