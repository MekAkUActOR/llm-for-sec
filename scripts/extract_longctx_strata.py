# -*- coding: utf-8 -*-
"""抽取各臂 longctx 报告的 needle 命中率与分层形态（严格按 needle.<lens>.<lang>.<depth>.<variant>.success）。

用途：m3-dpo 的 **chat** 读数 11/64（en16384=68.8%，其余三层 0）需要对照。
      chat 无历史口径 ⇒ 先在 **raw** 口径内看各臂形态，判断"分层极不均匀"是不是本仪器固有的。
"""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"

# needle.<lens>.<lang>.<depth>.<variant?>.<field>
KEY = re.compile(r"^needle\.(\d+)\.(\w+)\.([\d.]+)(?:\.(\d+))?\.success$")


def walk(o, path=""):
    """把嵌套 dict/list 摊平成 (点分路径, 值)。★报告是**嵌套** JSON，
    故必须摊平后再匹配 `needle.<lens>.<lang>.<depth>[.<variant>].success`。"""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, o


def load(f: Path):
    d = json.loads(f.read_text(encoding="utf-8"))
    out = {}
    for k, v in walk(d):
        m = KEY.match(k)
        if m:
            lens, lang, depth, var = m.group(1), m.group(2), float(m.group(3)), m.group(4)
            out[(int(lens), lang, depth, var)] = bool(v)
    return out


rows = []
for f in sorted(R.glob("longctx-*.json")):
    try:
        d = load(f)
    except Exception as e:  # noqa: BLE001
        print(f"  {f.name:<38} 读取失败 {type(e).__name__}")
        continue
    if not d:
        continue
    tag = f.stem.replace("longctx-", "")
    by = defaultdict(lambda: [0, 0])
    for (lens, lang, depth, var), ok in d.items():
        by[(lang, lens)][0] += 1
        if ok:
            by[(lang, lens)][1] += 1
    n = len(d)
    hit = sum(1 for v in d.values() if v)
    rows.append((tag, hit, n, by))

print(f"{'臂':<26} {'总命中':>10}   {'en16k':>8} {'en32k':>8} {'zh16k':>8} {'zh32k':>8}")
print("-" * 76)
for tag, hit, n, by in rows:
    def cell(lang, lens):
        k = (lang, lens)
        if k not in by:
            return "  -"
        tot, h = by[k][1], by[k][0]
        return f"{tot}/{h}"
    rate = f"{hit}/{n}={hit/n*100:.1f}%" if n else "-"
    print(f"{tag:<26} {rate:>10}   {cell('en',16384):>8} {cell('en',32768):>8} "
          f"{cell('zh',16384):>8} {cell('zh',32768):>8}")

print("\n注：old 格式报告（base/c1-full/m16/stage1-202m）只有 3 深度、无 variant ⇒ 分母 12，")
print("    与本轮 64 次（8 深度 × 2 variant × 2 lens × 2 lang）**不同口径**，不可直接混比。")
print("\nLONGCTX-STRATA=DONE")
