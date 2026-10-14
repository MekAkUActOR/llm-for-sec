# -*- coding: utf-8 -*-
"""核对 toolout 读数的新旧命名是否为同一仪器结构。

新命名：scored-chat-to-{tag}-v2.json      （eval_needlefix.ps1 现行写出）
旧命名：scored-chat-{tag}-tooloutput-v2.json（m25full/m2full 等既有产物）

若结构一致 ⇒ m25full/m2full 的裁定"缺 toolout"阻断项系**命名不匹配**，而非数据缺失。
"""
import json
from collections import Counter
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")
PAIRS = [
    ("scored-chat-to-m3-dpo-v2.json", "新命名（m3-dpo）"),
    ("scored-chat-m25full-tooloutput-v2.json", "旧命名（m25full）"),
    ("scored-chat-m2full-tooloutput-v2.json", "旧命名（m2full）"),
    ("scored-chat-m25full-v2.json", "参考：v0.2.1（m25full）"),
]


def hsh(o):
    if isinstance(o, dict):
        return {k: hsh(v) for k, v in sorted(o.items())}
    if isinstance(o, list):
        return f"list[{len(o)}]" + (f" of {hsh(o[0])}" if o else "")
    return type(o).__name__


for name, desc in PAIRS:
    p = R / name
    if not p.exists():
        print(f"\n✗ 缺 {name}（{desc}）")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    print(f"\n--- {name}  [{desc}]  {p.stat().st_size:,} B ---")
    print(f"    顶层键 = {list(d.keys())}")
    items = d.get("items", [])
    if items:
        print(f"    items = {len(items)}；kind 分布 = {dict(Counter(i.get('kind') for i in items))}")
        print(f"    item 键 = {sorted(items[0].keys())}")
    for k in ("metrics", "notes", "n", "n_responded", "n_missing"):
        if k in d:
            v = d[k]
            print(f"    {k} = {json.dumps(v, ensure_ascii=False)[:220]}")

print("\nTOOLOUT-NAMING-CHECK=DONE")
