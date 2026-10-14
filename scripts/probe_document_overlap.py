# -*- coding: utf-8 -*-
"""独立判定 raw_hits_long_content_share=17558 是真污染还是陈旧口径产物。

假设：rev=6 把"长内容共享"拆成 skeleton / prose 两桶（见 build_document_gate.py L1653），
      而盘上的 rev=5 产物只有一个未拆分的 raw_hits_long_content_share。
      若 17558 绝大部分属 skeleton（文档骨架样板，非内容），则"未见内容"的 claim 不受损。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "data/heldout/v0.6-document/_work/overlap-full.json"
d = json.loads(p.read_text(encoding="utf-8"))


def walk(o, path="", out=None):
    """收集所有以 raw_hits 或 prose 开头的键及其"大小"。"""
    if out is None:
        out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            np = f"{path}.{k}" if path else k
            if isinstance(v, (int, float, str, type(None))):
                if any(t in k for t in ("hits", "share", "overlap", "rev", "prose",
                                        "residue", "content", "short_fragment")):
                    out[np] = v if not isinstance(v, str) or len(v) < 60 else f"<str {len(v)}>"
            else:
                walk(v, np, out)
    elif isinstance(o, list):
        out[f"{path}[]"] = f"list len={len(o)}"
        if o and isinstance(o[0], dict):
            walk(o[0], f"{path}[0]", out)
    return out


print(f"顶层键 = {list(d.keys())}")
flat = walk(d)
for k in sorted(flat):
    print(f"  {k} = {flat[k]}")
