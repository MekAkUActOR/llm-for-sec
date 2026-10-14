# -*- coding: utf-8 -*-
"""逐条对比 v0.4-toolout：soup-a050 相对 m2calib 的翻转条目是谁？

目的：判定 +0.087（2/46 → 6/46）是**基线缺陷**还是**数据效应**。
若翻转条目集中在 "M3 载体批里出现过的同族机理"，则属后者（应由 M3 的载体多样性批次处理），
而不构成"不得用 soup-a050 作起点"的理由。
另统计 "malformed VERDICT" 计数（格式退化的直接指标）。
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "reports"


def load(tag):
    p = R / f"scored-chat-to-{tag}-v2.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    return {it["id"]: it for it in (d.get("items") or [])}


b, v = load("m2calib"), load("soup-a050")
print(f"条目数 m2calib={len(b)} soup-a050={len(v)}；id 集合相同={set(b)==set(v)}")

flip_up = [i for i in b if i in v and _s(b[i]) == 0.0 and _s(v[i]) == 1.0] if False else None


def s_of(it):
    try:
        s = float((it.get("derived") or {}).get("attack_success"))
        return s if s in (0.0, 1.0) else None
    except (TypeError, ValueError):
        return None


def o_of(it):
    try:
        o = float((it.get("derived") or {}).get("over_refusal"))
        return o if o in (0.0, 1.0) else None
    except (TypeError, ValueError):
        return None


up = [i for i in b if s_of(b[i]) == 0.0 and s_of(v.get(i, {})) == 1.0]
down = [i for i in b if s_of(b[i]) == 1.0 and s_of(v.get(i, {})) == 0.0]
print(f"\n顺从 0→1（变差）{len(up)} 条：")
for i in up:
    print(f"  {i:12} kind={v[i].get('kind'):12} label={v[i].get('label')}")
    print(f"      m2calib: {json.dumps(b[i].get('evidence'), ensure_ascii=False)[:120]}")
    print(f"      a050   : {json.dumps(v[i].get('evidence'), ensure_ascii=False)[:120]}"
          f"  note={v[i].get('note')}")
print(f"\n顺从 1→0（变好）{len(down)} 条：{[ (i, v[i].get('label')) for i in down ]}")

mo = [i for i in b if o_of(b[i]) == 1.0]
mv = [i for i in v if o_of(v[i]) == 1.0]
print(f"\n误拒: m2calib {len(mo)}/{sum(1 for i in b if o_of(b[i]) is not None)} "
      f"→ soup-a050 {len(mv)}/{sum(1 for i in v if o_of(v[i]) is not None)}")
print(f"  新增误拒: {sorted(set(mv) - set(mo))}")

for tag, D in (("m2calib", b), ("soup-a050", v)):
    n = sum(1 for i in D if "malformed" in str(D[i].get("note") or "").lower())
    print(f"\n{tag}: note 含 malformed 的条目 = {n}")
    for i in D:
        if "malformed" in str(D[i].get("note") or "").lower():
            print(f"    {i}: {D[i].get('note')}")

# 机理族统计（label 即机理名）
print("\n全集 label（机理）分布：")
for tag, D in (("m2calib", b), ("soup-a050", v)):
    from collections import Counter
    c = Counter(D[i].get("label") for i in D)
    print(f"  {tag}: {dict(c)}")
