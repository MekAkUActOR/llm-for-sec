# -*- coding: utf-8 -*-
"""★查明 MUST-A 的 n=168（历史裁定）与 n=64（现行 axes_rate）分别对应什么。

方法：读同一份 scored-chat-gen-*.json，逐个统计可得出 64 与 168 的筛选条件。
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

R = ROOT / "reports"


def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, o


for tag in ("soup-a050", "m25full", "m2full", "m3-dpo"):
    p = R / f"scored-chat-gen-{tag}-v2.json"
    if not p.exists():
        print(f"{tag}: 缺")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    items = d.get("items", [])
    print(f"\n--- {tag}：scored 文件 {len(items)} 个 item ---")
    print(f"    顶层键 = {list(d.keys())[:10]}")
    kinds = Counter(it.get("kind") for it in items)
    print(f"    kind 分布 = {dict(kinds)}")
    nresp = sum(1 for it in items if it.get("responded"))
    print(f"    responded=True = {nresp}")
    rob = [it for it in items if it.get("kind") == "robustness"]
    print(f"    kind=='robustness' = {len(rob)}")
    rob_r = [it for it in rob if it.get("responded")]
    print(f"    robustness 且 responded = {len(rob_r)}")
    has_as = [it for it in rob_r if "attack_success" in it]
    print(f"    ★其中含 attack_success 键 = {len(has_as)}")
    # attack_success 的取值分布
    vals = Counter(str(it.get("attack_success")) for it in has_as)
    print(f"    attack_success 取值 = {dict(vals)}")
    # 是否有嵌套结构
    if rob_r:
        print(f"    首个 robustness item 的键 = {sorted(rob_r[0].keys())}")

print("\n=== 系统日期 ===")
import datetime  # noqa: E402
print(f"  {datetime.datetime.now()}")
print("\nMUSTA-N-RESOLVE=DONE")
