# -*- coding: utf-8 -*-
r"""给**基于 96 口径**的 M3 裁决文档加"裁定挂起"横幅（**只加不删** ✓）。

## 为什么必须做

第 18 轮受控实验（`scripts/caliber_curve_controlled.py`）证明：
起点 `soup-needlefix-a050` 在 v0.3-gen 上的契约保留率
**512 口径 97.3%** ✓ vs **96 口径 46.9%** ✗ —— 且 **96 处的切片与真实 96 实跑逐位相同** ✓
⇒ **96 口径测的是截断，不是契约遵守** ✗。

而 M3 的 MUST-B 裁定（**70/168 → 20/168 FAIL** ✗）正是在 96 口径下读的 ✗
⇒ 该结论**不可采信** ✓，必须重算 ✓。

## 纪律（规则 2 + 推论 39.1）

**只加横幅，绝不删改原文** ✓ —— 原始裁决与其口径必须**同时可见** ✓，
否则就变成了"用新结论覆盖历史读数" ✗。
**预注册文档不在此列** ✓（预注册不可变 ✗）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"

#: 需要加横幅的**裁决类**文档（预注册不在内 ✗）
TARGETS = (
    "m3-final-verdict-20261006.md",
    "m3-verdict-mustb-fail.md",
    "m3-final-gate-picture.md",
    "m25-exit-verdict-m3dpo.md",
)
MARK = "裁定挂起"

BANNER = """> # ⏳⏳⏳ 裁定挂起：本文的裁决读数取自 **96 口径**，已证明该口径无效 ⏳⏳⏳
>
> **2026-10-06 第 18 轮**：独立复算 + **受控实验**（`scripts/caliber_curve_controlled.py`）
> 证明 —— 起点 `checkpoints/soup-needlefix-a050` 在 `v0.3-gen`（258 条）上的
> **契约保留率**：
>
> | 口径 | 含字面 `VERDICT` | 保留率 | 响应 token 中位 |
> |---|---|---|---|
> | **512（部署口径）** | 251/258 | **97.3%** ✓ | **148** |
> | **96（`baseline_eval.py` 的 CLI 默认值）** | 121/258 | **46.9%** ✗ | — |
>
> **★受控实验**（同一份 512 产物按 `new_token_ids[:N]` 切分，只改预算）在 **96 处给出
> 46.9%**，与真实 96 实跑**逐位相同** ⇒ **96 口径测的是截断，不是契约遵守** ✗✗。
>
> 预注册的 MUST-B 门限是 **63/168 = 37.5%** ✓ ——
> **在 96 口径下基线自己只有 41.7%（余量 4.2pp）** ✗
> ⇒ 该仪器上"起点 → M3 是否劣化"的比较**没有分辨力** ✗ ⇒ **本文结论不可采信** ✗。
>
> **⇒ M3 的正式状态：由「FAIL（已裁定）」改为「裁定挂起，待 512 口径重算」⏳。**
> **⇒ 不因挂起而进入交付谱系**（重算给出结论前保守处置不变 ✓）。
>
> 详见 `reports/caliber-defect-m3-adjudication.md` · 规则 39（docs/01 §11.38）。
>
> **★原始裁决原文一字未改地保留在下方** ✓ —— 口径与结论必须同时可见 ✓。

---

"""


def main() -> int:
    ok_all = True
    for name in TARGETS:
        p = R / name
        if not p.exists():
            print(f"  ★缺 {name}")
            ok_all = False
            continue
        t = p.read_text(encoding="utf-8")
        if MARK in t:
            print(f"  OK  已挂起（幂等） {name}")
            continue
        p.write_text(BANNER + t, encoding="utf-8")
        back = p.read_text(encoding="utf-8")
        good = MARK in back and not any(c in back for c in ("\ufffd", "锟斤拷"))
        print(f"  {'OK ' if good else '★NG'} 已加横幅 {name}  "
              f"({len(t.splitlines())} → {len(back.splitlines())} 行)")
        ok_all = ok_all and good

    # 反向检查：预注册**必须没有**被改动
    pre = R / "m3-dpo-preregistration.md"
    if pre.exists():
        pt = pre.read_text(encoding="utf-8")
        untouched = MARK not in pt
        print(f"  {'OK ' if untouched else '★NG'} 预注册未被改动 {pre.name}")
        ok_all = ok_all and untouched

    print(f"\nM3-VERDICT-SUSPENDED={'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
