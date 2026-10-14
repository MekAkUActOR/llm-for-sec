# -*- coding: utf-8 -*-
r"""★★★★★★ 用**生成器自己的结构化字段**定位注入族（不再自造代理 ✗）。

## 为什么这条路对

第 20 轮我用四个**自造代理**（引号 ✗ / `language` 字段 ✗ / 整段正文 ✗ / 关键词 ✗）全部失效 ✓。
**我一直在猜哪些字是注入** ✗ —— 而训练行自带 `src_task` / `lang` / `pack` ✓
（`dpoCAR-000859` 的 `src_task = T4-grounding:tool_output:clean:head` ✓），
**测试行自带 `intent`（含 `机制:[…]` 与 `载荷:…` ✓）与 `expected`** ✓。

**⇒ 先把这些字段的取值分布打出来** ✓ —— 这是**生成器的标签**，
不是我发明的度量 ✓。**只有在这一层找不到区分时，才回去做文本抽取** ✓。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/lf/dpo_m3_final.jsonl")
    a = ap.parse_args()

    rows = [json.loads(l) for l in (ROOT / a.data).read_text(
        encoding="utf-8").splitlines() if l.strip()]
    print(f"=== {a.data}  n={len(rows)} ===")
    print(f"  顶层键 = {sorted(rows[0].keys())}")

    print("\n=== ① dpo_class × lang 交叉 ===")
    tab: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        tab[str(r.get("dpo_class"))][str(r.get("lang"))] += 1
    print(f"  {'dpo_class':<30} {'lang 分布'}")
    for cls in sorted(tab, key=lambda c: -sum(tab[c].values())):
        print(f"  {cls:<30} {dict(tab[cls])}")

    print("\n=== ② dpo_class × pack 交叉（只看前 6 类）===")
    tab2: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        tab2[str(r.get("dpo_class"))][str(r.get("pack"))] += 1
    for cls in sorted(tab2, key=lambda c: -sum(tab2[c].values()))[:6]:
        print(f"  {cls:<30} {dict(tab2[cls])}")

    print("\n=== ③ carrier_* 三类的 src_task 取值（★生成器标签 ✓）===")
    for cls in ("carrier_inject_obedient", "carrier_inject_hollow",
                "carrier_clean_overrefusal"):
        st = Counter(str(r.get("src_task")) for r in rows
                     if str(r.get("dpo_class")) == cls)
        print(f"\n  --- {cls}（{sum(st.values())} 条，{len(st)} 种 src_task）---")
        for k, v in st.most_common(14):
            print(f"    {v:>5}  {k}")

    print("\n=== ④ 三类的 src_task 集合差（定位『注入族』标签 ✓）===")
    sets = {}
    for cls in ("carrier_inject_obedient", "carrier_inject_hollow",
                "carrier_clean_overrefusal"):
        sets[cls] = {str(r.get("src_task")) for r in rows
                     if str(r.get("dpo_class")) == cls}
    inj = sets["carrier_inject_obedient"] | sets["carrier_inject_hollow"]
    cln = sets["carrier_clean_overrefusal"]
    print(f"  仅注入类有 = {sorted(inj - cln)}")
    print(f"  仅干净类有 = {sorted(cln - inj)}")
    print(f"  两者共有   = {sorted(inj & cln)}")

    print("\n=== ⑤ 一个 inject_obedient 与一个 clean 的完整对照 ===")
    for cls in ("carrier_inject_obedient", "carrier_clean_overrefusal"):
        r = next((x for x in rows if str(x.get("dpo_class")) == cls), None)
        if not r:
            continue
        h = next((str(c.get("value") or "") for c in (r.get("conversations") or [])
                  if c.get("from") == "human"), "")
        print(f"\n--- {cls}  id={r.get('id')}  lang={r.get('lang')}  "
              f"src_task={r.get('src_task')} ---")
        print(h[:1300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
