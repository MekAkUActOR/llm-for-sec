# -*- coding: utf-8 -*-
r"""★★★★★★ 训练注入的**载体类型**分布 —— 判定"载体本体论覆盖缺口"。

## 假说（由生成器标签直接读出 ✓）

- **训练** `src_task = T1-injection:{载体}:{语义机制}:{位置}` ✓
  我在样本里看到的是 `email` ✓ / `log` ✓ / `code` ✓
- **测试** `机制:[AV-MP4-SubtitleTrack]` / `[IMG-XMP-SinkUrl]` ✓ = **字节存储位置** ✗
  载体是 `av_metadata`（MP4/MKV ✗）与 `image_metadata`（EXIF/XMP/PNG ✗）

**⇒ 若训练**从未**用过 av/image 载体 ⇒ 模型没见过这些存储位置的注入** ✗✓
**★ 这与载体本体论检查里的 `image_metadata 0 / av_metadata 0` 一致** ✓✓
（第 18 轮登记过这两个载体**训练行数为 0** ✗）。

**★ 修法将极其明确**：**补 av_metadata / image_metadata 载体的注入训练对** ✓
—— 而不是我前三轮猜的"隐蔽度" ✗ / "语言" ✗ / "裁决族" ✗ / "模板多样性" ✗（全部已被排除 ✓）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TRAIN = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"
HD = ROOT / "data" / "heldout" / "v0.3-gen"


def parse_src(st: str) -> tuple[str, str, str]:
    """★修正：`T1-injection:c:mech:pos` 是 **4** 段 ✗（我上一版写 5 ⇒ 静默全 `?` ✗）。"""
    p = str(st).split(":")
    if len(p) >= 4 and p[0] == "T1-injection":
        return p[1], p[2], p[3]
    return "?", "?", "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inject-classes", nargs="+",
                    default=["carrier_inject_obedient", "carrier_inject_hollow"])
    a = ap.parse_args()

    rows = [json.loads(l) for l in TRAIN.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    inj = [r for r in rows if str(r.get("dpo_class")) in a.inject_classes]

    print(f"=== 训练注入 {len(inj)} 条：载体 × 语义机制 × 位置（生成器标签 ✓）===")
    car = Counter()
    mech = Counter()
    pos = Counter()
    bad = 0
    for r in inj:
        c, m, p = parse_src(r.get("src_task"))
        if c == "?":
            bad += 1
        car[c] += 1
        mech[m] += 1
        pos[p] += 1
    print(f"  ★解析失败 = {bad}/{len(inj)}（必须为 0 ✗）")
    print(f"  载体   = {dict(car.most_common())}")
    print(f"  机制（{len(mech)} 种）= {dict(mech.most_common(14))}")
    print(f"  位置   = {dict(pos)}")

    print("\n=== ★全部 dpo_class 用到的载体（不只注入类 ✓）===")
    allcar = Counter()
    for r in rows:
        c, _, _ = parse_src(r.get("src_task"))
        allcar[c] += 1
    for k, v in allcar.most_common():
        print(f"  {k:<26} {v:>6}")
    print(f"  ★含 '?' 的情况 = {allcar.get('?', 0)}（非 T1-injection 的任务 ✓）")

    print("\n=== ★训练 vs 测试的**载体存在性**对照 ===")
    tst_car = Counter()
    for f in sorted(HD.glob("*.jsonl")):
        n = 0
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if str(r.get("kind")) == "robustness":
                n += 1
        tst_car[f.stem] = n
    print(f"  {'载体':<26} {'训练行数':>9} {'测试条数':>9}   判定")
    for k in sorted(set(list(tst_car) + [c for c in allcar if c != "?"])):
        tr = allcar.get(k, 0)
        te = tst_car.get(k, 0)
        if te and tr == 0:
            v = "★测试有、训练**完全没有** ✗✗"
        elif te and tr:
            v = "两侧都有 ✓"
        else:
            v = "仅训练有"
        print(f"  {k:<26} {tr:>9} {te:>9}   {v}")

    print("\n★判读：若 av_metadata / image_metadata 的训练行数为 **0** ✗")
    print("  ⇒ **载体本体论覆盖缺口成立** ✓✓")
    print("  ⇒ 模型从未见过 MP4/MKV/EXIF/XMP/PNG 存储位置的注入 ✗")
    print("  ⇒ 修法：**补这两类载体的注入训练对** ✓（不是隐藏度/语言/裁决族 ✗）")
    print("\nCARRIER-COVERAGE=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
