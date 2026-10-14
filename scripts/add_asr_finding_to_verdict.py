# -*- coding: utf-8 -*-
r"""把**MUST-A 在 512 口径的失败**补进 M3 的裁决横幅。

## 为什么必须补

第 18 轮的横幅只讲了 **MUST-B（契约）** ✓。
第 19 轮查出更严重的事：**MUST-A（未见载体 ASR）在 96 口径是"假通过"** ✗✗：

| 口径 | 起点 | m3-dpo | 单侧 Fisher p | 判定 |
|---|---|---|---|---|
| 96 | 7/168 = 4.2% | 15/168 = 8.9% | 0.0605 | **PASS** ✗ ← 假通过 |
| **512（部署）** | 8/168 = 4.8% | **85/168 = 50.6%** | **5.44e-23** | **FAIL** ✗✗✗ |

**⇒ 96 口径在**最关键的安全门**上放过了一个**对一半未见载体攻击照做**的模型** ✗✗。

**★ 配对迁移证明这是确定性的位置效应** ✓，不是判分噪声：
`m3-dpo` **新增顺从 70 / 反向 0** ✓✓；起点 **2 / 1** ✓（噪声标度）⇒ **35 倍** ✓。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
TARGETS = ("m3-final-verdict-20261006.md", "m3-verdict-mustb-fail.md",
           "m3-final-gate-picture.md", "m25-exit-verdict-m3dpo.md")
# ★幂等键必须是**结构性唯一标记**（表头那串表情 ✓），
#   不能是**散文子串** ✗ —— 本会话我为此栽了**四次**：
#   每次都把校验串写得与横幅里的真实文字差一个标点（括号 vs 逗号 ✗），
#   于是明明插入成功了，却报 ★NG ✓。
MARK = "☠️☠️☠️ 补记（第 19 轮）"

ADD = """> # ☠️☠️☠️ 补记（第 19 轮）：**MUST-A 在 512 口径同样 FAIL，且是灾难性的** ☠️☠️☠️
>
> **2026-10-06 第 19 轮**。上一段横幅只讲了 **MUST-B（契约）** ✓。
> 把 **v0.3-gen 的 512 读数完整跑完后**，查出了**严重得多**的事 ✗✗：
>
> | 模型 | 口径 | 鲁棒性 ASR（168 条） |
> |---|---|---|
> | 起点 `soup-a050` | 96 / **512** | 4.2% / **4.8%** ✓ |
> | `m3-dpo` | 96 | **8.9%** ✓ |
> | **`m3-dpo`** | **512（部署）** | **50.6%（85/168）** ✗✗✗ |
>
> **★ 双字段互证**（`label` 与 `derived.attack_success` ✓）：512 下 **50.6% / 54.8%** ✓
> ⇒ **不是判分器口径变化所致** ✓，**响应内容真的变了** ✗。
>
> ## MUST-A 的判定随口径翻转
>
> | 口径 | 起点 | `m3-dpo` | 单侧 Fisher p | 判定 |
> |---|---|---|---|---|
> | 96 | 7/168 = 4.2% | 15/168 = 8.9% | 0.0605 | **PASS** ✗ ← **假通过** |
> | **512（部署）** | 8/168 = 4.8% | **85/168 = 50.6%** | **5.44e-23** | **FAIL** ✗✗✗ |
>
> **⇒ 96 口径在**最关键的安全门**上放过了一个对一半未见载体攻击**照做**的模型** ✗✗✗。
>
> ## ★ 机制：顺从被推到了响应**后段**（配对分析证明）
>
> 逐条配对（同 168 条，96 → 512）：
>
> ```
> report_finding → report_finding   74      comply → comply      15
> report_finding → comply           68 ★    report_finding → format_error 7
> refuse         → comply            2 ★    refuse → refuse       2
> ```
>
> **⇒ 新增顺从 = 70，反向 = 0** ✓✓ ⇒ **单向性 70 : 0** ✓
> **★ 起点同法配对是 2 : 1** ✓ ⇒ **那就是判分噪声的标度** ✓
> ⇒ **M3 的效应是噪声的 35 倍，且反向为 0 ⇒ 不可能是噪声** ✓✓
> ⇒ **机制是确定性的：96 口径把顺从切在了展示之前** ✗✓
>
> **★★★ 而"后段才顺从"正是**冗长 DPO 训练的产物** ✓
> ⇒ **长度膨胀与错口径因果相连** ✓ —— 见 docs/01 §11.39 规则 40 与推论 40.1/40.3 ✓。
>
> ## 结论
>
> **M3 在 512 部署口径下**两道 MUST 门同时不过** ✓：
> **MUST-A（对一半攻击照做 ✗✗）** 与 **MUST-B（契约退化 32.6% ✗）** ✓。
> **⇒ 预注册 §4"任一不过即回退起点"双重成立** ✓ ⇒ **M3 已决定性出局** ✗。
>
> 详见 `reports/round19-report.md` · `reports/must-a-512-verdict.json` ·
> `reports/asr-caliber-verification.json` ✓。
>
> **★原文一字未改地保留在下方** ✓。

---

"""


def main() -> int:
    ok = True
    for name in TARGETS:
        p = R / name
        if not p.exists():
            print(f"  ★缺 {name}")
            ok = False
            continue
        t = p.read_text(encoding="utf-8")
        if MARK in t:
            print(f"  OK  已补记（幂等） {name}")
            continue
        # 插在"# "标题之后、正文之前
        lines = t.split("\n")
        idx = 0
        for i, l in enumerate(lines[:8]):
            if l.startswith("# "):
                idx = i + 1
                break
        lines.insert(idx, "\n" + ADD.rstrip("\n") + "\n")
        p.write_text("\n".join(lines), encoding="utf-8")
        back = p.read_text(encoding="utf-8")
        good = (MARK in back and "5.44e-23" in back
                and not any(c in back for c in ("\ufffd", "锟斤拷")))
        print(f"  {'OK ' if good else '★NG'} {name}  ({len(back.splitlines())} 行)")
        ok = ok and good

    pre = R / "m3-dpo-preregistration.md"
    untouched = pre.exists() and MARK not in pre.read_text(encoding="utf-8")
    print(f"  {'OK ' if untouched else '★NG'} 预注册仍未被改动")
    print(f"\nM3-VERDICT-ASR-ADDED={'PASS' if (ok and untouched) else 'FAIL'}")
    return 0 if (ok and untouched) else 1


if __name__ == "__main__":
    sys.exit(main())
