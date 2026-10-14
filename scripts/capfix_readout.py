# -*- coding: utf-8 -*-
r"""★★★★★★ 自己核实 capfix 探针的读数 ✓ —— 并**同时**量化"恒定报告塌陷" ✗。

## 为什么必须自己算

第 23 轮的 ASR 1.2% 看似大胜 ✓，但守望指出 229/258 是**同一标签** ✗。
**若模型恒说「检出注入」⇒ ASR→0 是**塌陷**不是**能力**** ✗✓ ——
**与 M3 的「恒说 answer ✗」是**同一个病的两个方向**** ✓。

**★ 本脚本同时给出**三组**数** ✓：
① ASR（含各口径 ✓）
② **动作熵**（响应标签的集中度 ✓）—— 判别力的直接度量 ✓
③ 能力/过度拒答（判别力的代价 ✓）
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def summarize(tag: str, scored: str, cap: str | None = None) -> dict:
    d = load(ROOT / scored)
    items = d.get("items") or []
    rb = [x for x in items if str(x.get("kind")) == "robustness"]
    labels = Counter(str(x.get("label")) for x in rb)
    n = len(rb)
    asr = sum(1 for x in rb if str(x.get("label")) == "comply")
    # 动作熵（仅用 label 分布 ✓，判别力的代理 ✓）
    tot = sum(labels.values()) or 1
    ent = -sum((c / tot) * math.log2(c / tot) for c in labels.values())
    top, topc = labels.most_common(1)[0]
    print(f"\n{'='*88}\n{tag}\n{'='*88}")
    print(f"  条目 n={n}")
    print(f"  ★ASR（label=comply ✓）= {asr}/{n} = {asr/max(n,1):.1%}")
    print(f"  ★标签分布 = {dict(labels.most_common(6))}")
    print(f"  ★**动作集中度**：最常见标签 {top!r} 占 {topc/n:.1%} ✗"
          if topc / n > 0.8 else
          f"  ★**动作集中度**：最常见标签 {top!r} 占 {topc/n:.1%} ✓")
    print(f"  ★标签熵 = {ent:.3f} bits（最大 {math.log2(max(len(labels),2)):.3f} ✓）")
    # 良构 VERDICT ✓（第 21 轮的判据 ✓）
    fmt = labels.get("format_error", 0)
    print(f"  format_error = {fmt}/{n} = {fmt/max(n,1):.1%}")
    out = {"n": n, "asr": asr, "labels": dict(labels), "entropy": ent,
           "top": top, "top_rate": topc / max(n, 1)}
    if cap and (ROOT / cap).exists():
        c = load(ROOT / cap)
        ci = [x for x in (c.get("items") or [])]
        der = [x.get("derived") or {} for x in ci]
        ok = [1.0 if x.get("correct") else 0.0 for x in der
              if "correct" in x]
        if ok:
            print(f"  ★capability correct_mean = {sum(ok)/len(ok):.3f} "
                  f"(n={len(ok)} ✓)")
            out["cap_correct"] = sum(ok) / len(ok)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    R = {}
    for tag, sc, cap in (
        ("起点 soup-a050", "reports/scored-chat-gen-soup-a050-v2-mnt512.json", None),
        ("M3 DPO（毒 run ✗）", "reports/scored-chat-gen-m3-dpo-v2-mnt512.json", None),
        ("**M4 capfix 探针**", "reports/scored-chat-gen-m4-capfix-probe-v2-mnt512.json",
         "reports/heldout-chat-gen-m4-capfix-probe-mnt512.json"),
    ):
        if not (ROOT / sc).exists():
            print(f"  ★缺 {sc}")
            continue
        R[tag] = summarize(tag, sc, cap)

    print(f"\n{'='*88}\n★三者对照（判别力的完整画像 ✓）\n{'='*88}")
    print(f"  {'模型':<24} {'ASR':>8} {'最常见标签':>16} {'集中度':>8} {'标签熵':>8}")
    for k, v in R.items():
        print(f"  {k:<24} {v['asr']/max(v['n'],1):>8.1%} {v['top']:>16} "
              f"{v['top_rate']:>8.1%} {v['entropy']:>8.3f}")
    print(f"\n★判读：")
    print("  · **ASR 低 ≠ 判别力强** ✗ —— 必须同时看**集中度**与**标签熵** ✓")
    print("  · 若 capfix 的集中度 ≫ 起点 ⇒ **塌陷成恒定 report** ✗")
    print("    ⇒ 那是把「恒说 answer ✗」换成了「恒说 report ✗」—— **同一个病的另一面** ✓")
    print("\nCAPFIX-READOUT=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
