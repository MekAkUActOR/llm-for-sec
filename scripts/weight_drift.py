# -*- coding: utf-8 -*-
r"""★★★★★ 量「权重漂移」：探针是不是**几乎没离开起点**？ ✓（纯 CPU ✓）

## 为什么这是决定性的

第 25–26 轮：**三次运行的奖励曲线逐点重合** ✗ ⇒ 曲线测不住行为漂移 ✗✓。
**而行为侧：起点 ASR 4.8% ✓ → 探针 0.6% ✓ → M3 50.6%** ✗。

**★ 若探针的权重**几乎没动**（相对起点 ✓）⇒ 它的 0.6% 就是「**没怎么训**」的产物 ✓✓
**⇒ H-B 成立** ✗（问题在训练预算，不在数据内容 ✓）
**★ 反之若探针权重已大幅漂移 ⇒ H-B 不成立** ✗ ⇒ 数据修法确实起了作用 ✓✓

**★ 度量**：逐张量的**相对 L2**（||Δ|| / ||起点|| ✓）与**余弦相似度** ✓，
**并报**全局的相对 L2**（按参数数加权 ✓，避免被单个大张量主导 ✗）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
CK = R / "checkpoints"
TARGETS = [
    ("探针（有效 ~150 步 ✓）", CK / "qwen3-06b-sec-m4-capfix-probe"),
    ("M3 @1500（毒 ✗）", CK / "qwen3-06b-sec-m3-dpo" / "checkpoint-1500"),
    ("M3 @1803（毒 ✗）", CK / "qwen3-06b-sec-m3-dpo" / "checkpoint-1803"),
    ("全长 @300 ✓", CK / "qwen3-06b-sec-m4-capfix-full" / "checkpoint-300"),
    ("全长 @400 ✓", CK / "qwen3-06b-sec-m4-capfix-full" / "checkpoint-400"),
    ("全长 @500 ✓", CK / "qwen3-06b-sec-m4-capfix-full" / "checkpoint-500"),
    ("全长 @600 ✓", CK / "qwen3-06b-sec-m4-capfix-full" / "checkpoint-600"),
    ("全长 @700 ✓", CK / "qwen3-06b-sec-m4-capfix-full" / "checkpoint-700"),
]
STARTS = [("起点 soup-a050", CK / "soup-needlefix-a050")]


def load_state(p: Path):
    import torch
    from safetensors.torch import load_file
    f = p / "model.safetensors"
    if not f.exists():
        cands = sorted(p.glob("*.safetensors"))
        if not cands:
            return None
        f = cands[0]
    return load_file(str(f), device="cpu")


def main() -> int:
    try:
        import torch  # noqa: F401
        from safetensors.torch import load_file  # noqa: F401
    except Exception as e:
        print(f"  ★缺依赖：{e}")
        return 2

    bname, bpath = STARTS[0]
    print(f"=== 基准 = {bname} ===")
    base = load_state(bpath)
    if base is None:
        print(f"  ★读不到 {bpath}")
        return 2
    bn = sum(v.numel() for v in base.values())
    print(f"  张量数 = {len(base)}，参数数 = {bn:,}")

    print(f"\n=== ★相对漂移（vs 起点 ✓）===")
    print(f"  {'目标':<26} {'相对L2(全局)':>13} {'余弦相似':>10} {'改过的张量':>11}")
    out = {}
    for name, p in TARGETS:
        if not p.exists():
            print(f"  {name:<26} ★缺目录")
            continue
        st = load_state(p)
        if st is None:
            print(f"  {name:<26} ★读不到权重")
            continue
        num = den = dot = nb = 0.0
        changed = 0
        tot = 0
        for k, v0 in base.items():
            if k not in st:
                continue
            v1 = st[k]
            if v1.shape != v0.shape:
                continue
            d = (v1.float() - v0.float())
            num += float((d * d).sum())
            den += float((v0.float() * v0.float()).sum())
            dot += float((v1.float() * v0.float()).sum())
            nb += float((v1.float() * v1.float()).sum())
            tot += 1
            # ★"改过的张量"：该张量自身的相对 L2 > 1e-4 ✓
            n0 = float((v0.float() * v0.float()).sum())
            if n0 > 0 and (float((d * d).sum()) / n0) ** 0.5 > 1e-4:
                changed += 1
        rel = (num / den) ** 0.5 if den else float("nan")
        cos = dot / ((den ** 0.5) * (nb ** 0.5)) if den and nb else float("nan")
        print(f"  {name:<26} {rel:>13.5f} {cos:>10.6f} "
              f"{changed:>5}/{tot:<5}")
        out[name] = {"rel_l2": rel, "cosine": cos,
                     "changed_tensors": changed, "tensors": tot}

    print(f"\n★判读：")
    probe = next((v for k, v in out.items() if k.startswith("探针")), None)
    if probe:
        print(f"  · 探针相对漂移 = **{probe['rel_l2']:.5f}**，余弦 = {probe['cosine']:.6f}")
        if probe["rel_l2"] < 0.01:
            print("  ⇒ **探针几乎没离开起点** ✓ ⇒ 它的 ASR 0.6% 是「**没怎么训**」的产物 ✓✓")
            print("  ⇒ **H-B 成立** ✗ ⇒ 病根在**训练预算**，不在数据内容 ✓")
        else:
            print("  ⇒ 探针已实质漂移 ⇒ H-B **不成立** ✗ ⇒ 数据修法可能确有作用 ✓✓")
    print("\nWEIGHT-DRIFT=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
