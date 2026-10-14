# -*- coding: utf-8 -*-
r"""★★★★★★ 真正的维度：**按语言分档的 ASR**。

## 为什么这是本轮的关键更正

我把注入按"有无自称词汇"分档 ✓，但关键词表**只有中文** ✗
⇒ "无自称词汇"那一档实际是**英文注入** ✗✓。
实看样本：被漏掉的注入是英文 ✓（`skip the copyright checks` ✗）、
被正确检出的注入是中文 ✓（`步骤1：…步骤3：不要提及本段` ✓）。

**⇒ 真正的假说是**语言泛化失败**：DPO 只教会了**中文**注入检测** ✗✓。

**★ 这个区分极其重要**，因为两条假说导出的**修法完全不同** ✗✓：
| 假说 | 修法 |
|---|---|
| 词法化 ✗ | 补隐蔽注入正样本 |
| **语言泛化失败** ✗ | **补**双语**注入正样本（同等语义、两种语言）** ✓ |
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
D = ROOT / "data" / "heldout" / "v0.3-gen"


def lang_map() -> dict[str, str]:
    out = {}
    for p in sorted(D.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) == "robustness":
                out[str(r.get("id"))] = str(r.get("language") or "?")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="按语言分档的 ASR")
    a = ap.parse_args()

    lm = lang_map()
    print(f"=== heldout/v0.3-gen robustness 语言分布 n={len(lm)} ===")
    print(f"  {dict(Counter(lm.values()))}")

    for name, rel in [("起点 soup-a050", "reports/scored-chat-gen-soup-a050-v2-mnt512.json"),
                      ("m3-dpo", "reports/scored-chat-gen-m3-dpo-v2-mnt512.json")]:
        p = ROOT / rel
        if not p.exists():
            print(f"  ★缺 {rel}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        items = [x for x in (d.get("items") or []) if str(x.get("kind")) == "robustness"]
        print(f"\n{'='*80}\n{name}  n={len(items)}\n{'='*80}")
        print(f"  {'语言':<8} {'n':>4} {'comply':>7} {'ASR':>8}   {'检测到':>7}  标签")
        for lg in sorted(set(lm.values())):
            sub = [x for x in items if lm.get(str(x.get("id"))) == lg]
            if not sub:
                continue
            k = sum(1 for x in sub if str(x.get("label")) == "comply")
            rf = sum(1 for x in sub if str(x.get("label")) == "report_finding")
            c = Counter(str(x.get("label")) for x in sub)
            print(f"  {lg:<8} {len(sub):>4} {k:>7} {k/len(sub):>8.1%} {rf:>7}   "
                  f"{dict(c)}")

    print("\n★判读：")
    print("  · 若起点两种语言都低 ✓ 而 m3-dpo **只在一种语言上爆炸** ✗")
    print("    ⇒ **语言泛化失败成立** ✓✓ ⇒ 修法是**双语注入正样本** ✓")
    print("  · 若两种语言都爆炸 ⇒ 与语言无关，回到语义/词法 ✗")
    print("\nASR-BY-LANGUAGE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
