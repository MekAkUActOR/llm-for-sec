# -*- coding: utf-8 -*-
"""从既有 longctx-*.json 报告里抽取 needle 命中率的分层形态。

目的：m3-dpo 的 chat 口径读数是 11/64（en16384=68.8%，其余三层全 0）。
      但 chat 口径**从未跑过**，没有历史对照 ⇒ 需先看 **raw 口径**下各臂的形态：
      - 若**所有臂**都是"en16384 高、其余低" ⇒ 这是仪器固有形态，m3-dpo 的 17.2% 需与
        同口径 baseline 比才有效（即必须等 soup-a050-chat）。
      - 若**只有 m3-dpo 类**呈现该形态 ⇒ 崩塌结论更强。
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"


def walk(o, path=""):
    """把嵌套 dict/list 摊平成 (路径, 值)。"""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, o


def needle_summary(d):
    """尽力从报告中找出 needle 命中统计。返回 (hits, total) 或 None。"""
    flat = dict(walk(d))
    # 常见键名
    for k, v in flat.items():
        if isinstance(v, (int, float)) and "needle" in k.lower() and (
                "rate" in k.lower() or "acc" in k.lower() or "hit" in k.lower()):
            tot = None
            for k2, v2 in flat.items():
                if "needle" in k2.lower() and ("n" == k2.lower().split(".")[-1]
                                               or "total" in k2.lower()):
                    tot = v2
                    break
            return (v, tot, k)
    return None


print("=== reports/longctx-*.json 的 needle 读数（raw 口径，除注明外）===\n")
for f in sorted(R.glob("longctx-*.json")):
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  {f.name:<40} 读取失败 {type(e).__name__}")
        continue
    flat = dict(walk(d))
    # 找 needle 相关键（列出全部，便于人读）
    keys = [k for k in flat if "needle" in k.lower()]
    if not keys:
        # 也许叫 retrieval / probe
        keys = [k for k in flat if "retriev" in k.lower() or "probe" in k.lower()]
    print(f"--- {f.name} ---")
    if not keys:
        print(f"    顶层键 = {list(d)[:8]}")
        continue
    # 汇总每组
    for k in sorted(keys):
        if isinstance(flat[k], (int, float, str)):
            print(f"    {k} = {flat[k]}")
    print()

print("LONGCTX-SHAPE=DONE")
