# -*- coding: utf-8 -*-
"""查新格式 longctx 报告的实际键结构（旧格式是 needle.<lens>.<lang>.<depth>.success）。"""
import json
import sys
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec\reports")
name = sys.argv[1] if len(sys.argv) > 1 else "longctx-soup-a050.json"
d = json.loads((R / name).read_text(encoding="utf-8"))


def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, o


flat = list(walk(d))
print(f"{name}: 顶层键 = {list(d.keys())}")
print(f"总叶子 = {len(flat)}")
ks = [k for k, _ in flat if "needle" in k.lower()]
print(f"含 needle 的叶子 = {len(ks)}")
for k in ks[:16]:
    print("   ", k)

# 也打印第一层的子结构
for k, v in d.items():
    if isinstance(v, dict):
        print(f"  d['{k}'] 是 dict，子键 = {list(v.keys())[:10]}")
    elif isinstance(v, list):
        print(f"  d['{k}'] 是 list，长度 = {len(v)}"
              + (f"，首元素键 = {list(v[0].keys())[:10]}" if v and isinstance(v[0], dict) else ""))
    else:
        print(f"  d['{k}'] = {str(v)[:70]}")
