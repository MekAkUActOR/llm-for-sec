# -*- coding: utf-8 -*-
r"""★★★★★ 轴 1 构建器：把**纯文风对（F 类 ✗）降权**后的 DPO 数据集（**默认 dry-run ✓**）。

## 依据（第 30–31 轮 ✓，全部为实测 ✓）

`scripts/rebalance_design.py` 的三分（28,842 对 ✓）：
| 类 | 对数 | 占比 | 梯度质量占比 |
|---|---|---|---|
| **S 方向对** ✓（`action` 不同） | 13,179 | 45.7% | **53.6%** |
| **C 契约对** ✓（`action` 同，但 verdict/findings/confidence 有一项不同） | 1,422 | 4.9% | 7.0% |
| **F 风格对** ✗（三者全同 ⇒ 纯文风） | **14,241** | **49.4%** | **39.4%** |

**★ `policy` 类（占全量 51% ✓）里 F 占 74.3%** ✗ —— **最大的类几乎全是文风** ✗✓

## 机制（第 30 轮统一机制 ✓）
**>50% 梯度教文风** ✗ + **每个 margin 靠压低 rejected 拿到** ✗（`logps/rejected` → −18 ✗）
⇒ **结构化安全回复的**绝对似然崩塌**** ✗ ⇒ **丢掉 VERDICT 契约与 `report` 动作** ✗✓

## ★★★ 预注册预测（**在训练之前写下 ✓，不得事后改 ✓**）

**若「F 类降权到 1/N + epoch 0.1」同时施加 ✓，则**端点 ASR 应 < 15%** ✓**：
- **① F 的梯度质量占比从 39.4% 降到 ≈15% 以下** ✓（**可先由本脚本 dry-run 直接核验 ✓**）
- **② 端点 `rewards/chosen` 不应转负** ✓（第 29–31 轮实测其转负是病态的前兆 ✓）
- **③ 若只做降权而不削预算 ⇒ 预测 ASR 仍 > 40%** ✗（**预算轴独立必要 ✓**）

**★ 用法**：
```
python scripts/build_rebalanced_mix.py --dry-run        # 只报降权后的配比（默认 ✓）
python scripts/build_rebalanced_mix.py --factor 4 --out data/m4-run/dpo_m4_rebal.jsonl
```
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
SRC = R / "data" / "m4-run" / "dpo_m4_capfix.jsonl"
FIELD = re.compile(r'"([a-z_]+)"\s*:\s*("([^"]*)"|(-?[\d.]+)|(\[[^\]]*\]))')


def parse_verdict(t: str) -> dict:
    m = re.search(r"VERDICT\s*:\s*(\{.*\})", t or "", re.S)
    if not m:
        return {}
    s = m.group(1)
    k = s.rfind("}")
    s = s[:k + 1] if k >= 0 else s
    try:
        return json.loads(s)
    except Exception:
        out = {}
        for mm in FIELD.finditer(s):
            out[mm.group(1)] = (mm.group(3) if mm.group(3) is not None
                                else (mm.group(4) if mm.group(4) is not None
                                      else mm.group(5)))
        return out


def classify(row: dict) -> tuple[str, int]:
    ct = (row.get("chosen") or {}).get("value") or ""
    rt = (row.get("rejected") or {}).get("value") or ""
    cv, rv = parse_verdict(ct), parse_verdict(rt)
    ca, ra = cv.get("action"), rv.get("action")
    if not ca or ca != ra:
        return "S", len(rt)
    diffs = any(str(cv.get(x)) != str(rv.get(x))
                for x in ("verdict", "findings", "confidence"))
    return ("C" if diffs else "F"), len(rt)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--factor", type=int, default=4, help="F 类保留 1/factor（默认 4 ✓）")
    ap.add_argument("--out", default="")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--write", action="store_true", help="★显式写出（覆盖默认 dry-run ✓）")
    ap.add_argument("--seed", type=int, default=20261006)
    a = ap.parse_args()

    if not SRC.exists():
        print(f"  ★缺 {SRC}")
        return 2
    rnd = random.Random(a.seed)
    rows: list[dict] = []
    kept: list[dict] = []
    cnt, mass = Counter(), Counter()
    kcnt, kmass = Counter(), Counter()
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            k, L = classify(row)
            cnt[k] += 1
            mass[k] += L
            if k == "F":
                if rnd.randrange(a.factor) == 0:      # 保留 1/factor ✓
                    kept.append(row)
                    kcnt[k] += 1
                    kmass[k] += L
            else:
                kept.append(row)                       # S/C 全保留 ✓
                kcnt[k] += 1
                kmass[k] += L

    tot_m, ktot_m = sum(mass.values()) or 1, sum(kmass.values()) or 1
    print(f"=== ★F 类降权 1/{a.factor}（dry-run={not a.write} ✓）===")
    print(f"  {'类':<22} {'原对数':>8} {'原质量占比':>11} "
          f"{'新对数':>8} {'新质量占比':>11}")
    for k, name in (("S", "S 方向对 ✓"), ("C", "C 契约对 ✓"), ("F", "F 风格对 ✗")):
        print(f"  {name:<22} {cnt[k]:>8,} {mass[k]/tot_m:>11.1%} "
              f"{kcnt[k]:>8,} {kmass[k]/ktot_m:>11.1%}")
    print(f"  {'合计':<22} {sum(cnt.values()):>8,} {1.0:>11.1%} "
          f"{sum(kcnt.values()):>8,} {1.0:>11.1%}")

    print(f"\n★预注册预测核验（① ✓）：")
    f_after = kmass["F"] / ktot_m
    print(f"  · F 的质量占比 {mass['F']/tot_m:.1%} → **{f_after:.1%}**")
    print(f"  · 预测①（F 降到 ≤15%）⇒ {'**成立** ✓' if f_after <= 0.15 else '**不成立** ✗ ⇒ 需更大的 factor ✓'}")
    print(f"  · S+C 的质量占比 {1-mass['F']/tot_m:.1%} → **{1-f_after:.1%}** ✓")
    print(f"\n★预测②（端点 chosen 不转负）与③（只降权不削预算 ⇒ ASR 仍 >40%）"
          f"须训练后才能验 ✓")

    if not a.write:
        print("\n★dry-run ✓ —— **未写出任何数据** ✓（要写出请加 --write ✓）")
        print("REBALANCE-BUILD=DONE(dry-run)")
        return 0

    out = Path(a.out) if a.out else (R / "data" / "m4-run" / "dpo_m4_rebal.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    h = hashlib.sha256()
    with out.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    print(f"\n  写出 -> {out}")
    print(f"  行数 = {len(kept):,}，字节 = {out.stat().st_size:,}")
    print(f"  sha256 = **{h.hexdigest().upper()}**")
    print("REBALANCE-BUILD=DONE(written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
