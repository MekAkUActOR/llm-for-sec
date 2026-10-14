# -*- coding: utf-8 -*-
"""看几个 jsonl/json 的条目 id 前缀，确认"哪份响应对应哪份判分产物"。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ids_jsonl(p, limit=6):
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            for k in ("id", "item_id", "qid"):
                if k in d:
                    out.append(str(d[k]))
                    break
            if len(out) >= limit:
                break
    return out


def ids_json(p, limit=6):
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    return [str(r.get("id")) for r in d.get("items", [])[:limit]]


for arg in sys.argv[1:]:
    p = Path(arg)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        print(f"{p.name}: 缺失")
        continue
    try:
        got = ids_jsonl(p) if p.suffix == ".jsonl" else ids_json(p)
        print(f"{p.name:46} 前几个 id = {got}")
    except Exception as e:
        print(f"{p.name:46} 读取失败 {e}")
