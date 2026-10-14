# -*- coding: utf-8 -*-
r"""★★★★★ 训练注入的语言分布 —— 判定"语言泛化失败"的**因果**证据。

## 逻辑

- 测试侧：m3-dpo en **74.4%** ✗✗ / zh **27.9%** ✗（起点 3.7% / 5.8% ✓）
- **若训练的注入样本几乎全是中文** ✗ ⇒ **英文检测从未被教过** ✗✓
  ⇒ 英文崩塌是**训练分布缺口的直接后果** ✓ ⇒ 修法明确：**补英文注入正样本** ✓
- **若训练里中英相当** ✓ 而英文仍崩 ⇒ 另有机制，须继续查 ✗

**★ 判定方法**：按**中文字符占比**给每条注入载体定语言 ✓，
并**同时**看 chosen 的动作 ✓（确认这些对确实在教 report ✓）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
CARRIER = re.compile(r"<carrier\b[^>]*>(.*?)</carrier>", re.S)
CJK = re.compile(r"[\u4e00-\u9fff]")


def guess_lang(t: str) -> str:
    cjk = len(CJK.findall(t))
    letters = sum(1 for ch in t if ch.isascii() and ch.isalpha())
    if cjk == 0:
        return "en"
    if letters == 0:
        return "zh"
    return "zh" if cjk * 3 > letters else "mixed"


def side_text(side) -> str:
    if isinstance(side, dict):
        return str(side.get("value") or "")
    return str(side or "")


def main() -> int:
    ap = argparse.ArgumentParser(description="训练注入的语言分布")
    ap.add_argument("--data", default="data/lf/dpo_m3_final.jsonl")
    ap.add_argument("--classes", nargs="+",
                    default=["carrier_inject_obedient", "carrier_inject_hollow",
                             "carrier_clean_overrefusal", "bt330_refusal",
                             "policy", "reserve"])
    a = ap.parse_args()

    d = ROOT / a.data
    rows = [json.loads(l) for l in d.read_text(encoding="utf-8").splitlines() if l.strip()]
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(str(r.get("dpo_class")), []).append(r)

    print(f"=== 训练样本的语言分布（按载体正文的中文字符占比判定）===")
    print(f"  {'dpo_class':<30} {'n':>6} {'载体语言分布':<34} {'chosen 正文语言'}")
    for cls in a.classes:
        rs = by.get(cls) or []
        if not rs:
            continue
        cl = Counter()
        sl = Counter()
        for r in rs:
            hum = next((c.get("value") for c in (r.get("conversations") or [])
                        if c.get("from") == "human"), "")
            m = CARRIER.search(str(hum or ""))
            cl[guess_lang(m.group(1) if m else "")] += 1
            sl[guess_lang(side_text(r.get("chosen")))] += 1
        print(f"  {cls:<30} {len(rs):>6} {str(dict(cl)):<34} {dict(sl)}")

    print("\n★判读：")
    inj = [c for c in a.classes if "inject" in c]
    tot = Counter()
    for cls in inj:
        for r in (by.get(cls) or []):
            hum = next((c.get("value") for c in (r.get("conversations") or [])
                        if c.get("from") == "human"), "")
            m = CARRIER.search(str(hum or ""))
            tot[guess_lang(m.group(1) if m else "")] += 1
    n = sum(tot.values()) or 1
    print(f"  注入类合计 {n} 条，载体语言 = {dict(tot)}")
    zh = tot.get("zh", 0) / n
    en = tot.get("en", 0) / n
    print(f"  中文占比 {zh:.1%}   英文占比 {en:.1%}")
    if zh > 0.85:
        print("  ⇒ **训练注入几乎全为中文** ✗ ⇒ 英文检测从未被教过 ✓")
        print("    ⇒ **语言泛化失败成立** ✓✓ ⇒ 修法：**补英文注入正样本** ✓")
    elif en > 0.15:
        print("  ⇒ 训练英文注入占比不可忽略 ⇒ 单纯'没教过'解释不全 ✗，须继续查")
    print("\nTRAIN-INJECTION-LANGUAGE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
