# -*- coding: utf-8 -*-
"""检查 v0.4-toolout 判分文件里"不可判"条目（derived.attack_success ∉ {0,1}）的成因。

动机：`toolout_rate()` 保守剔除不可判条目，以免把判分器空值当"拒绝"而虚报防线。
但若"不可判"本身与失败模式相关（C 路实证：空心拒答 = 攻击成功却无 VERDICT 行），
剔除就会**藏住**信号。本脚本先看清它是什么。
"""
import json
from collections import Counter
from pathlib import Path

R = Path(__file__).resolve().parent.parent / "reports"
for tag in ("m2calib", "soup-a050"):
    p = R / f"scored-chat-to-{tag}-v2.json"
    if not p.exists():
        print(f"{tag}: 缺")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    items = d.get("items") or []
    c = Counter()
    samples = []
    for it in items:
        dv = it.get("derived") or {}
        s = dv.get("attack_success")
        key = "0.0" if s == 0.0 else "1.0" if s == 1.0 else repr(s)
        c[key] += 1
        if key not in ("0.0", "1.0") and len(samples) < 2:
            samples.append(it)
    print(f"\n=== {tag}：{len(items)} 条；attack_success 取值分布 {dict(c)} ===")
    for s in samples:
        print(f"  id={s.get('id')} kind={s.get('kind')} label={s.get('label')}")
        print(f"    derived={json.dumps(s.get('derived'), ensure_ascii=False)}")
        print(f"    responded={s.get('responded')} structured={s.get('structured')} "
              f"policy_declared={s.get('policy_declared')} expected={s.get('policy_expected')}")
        print(f"    note={str(s.get('note'))[:220]}")
        ev = s.get("evidence")
        print(f"    evidence={json.dumps(ev, ensure_ascii=False)[:260]}")
