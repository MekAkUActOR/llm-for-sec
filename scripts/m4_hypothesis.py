# -*- coding: utf-8 -*-
r"""★★★ 因果归因 + M4 的可证伪假设。

## 归因是干净的（只有一个变量变了）

| 产物 | 训练到哪一步 | 512 口径鲁棒性 ASR |
|---|---|---|
| `soup-needlefix-a050` | **SFT 产物**（起点） | **4.8%**（8/168）✓ |
| `m3-dpo` | **起点 + M3 DPO** | **50.6%**（85/168）✗✗ |

**⇒ 两者之间只差 M3 这一步 DPO** ✓ ⇒ **注入抵抗力的崩塌归因于该 DPO** ✓✓。

## 该 DPO 的已知缺陷（第 16/17 轮已诊断）

`data/lf/dpo_m3_final.jsonl`（28,842 对）里 **5 类 / 6,540 对（22.7%）**
存在**长度混杂** ✗ —— **chosen 系统性比 rejected 长** ✓，
且是**均匀地**分布在全部 6,540 对上 ✓（而类别信号是类局部的 ✓）
⇒ 净效应 = **一个全局的长度推力** ✗ ⇒ 把策略推向**冗长** ✓。

## 机制假说（可证伪）

**冗长推力 ⇒ 策略整体漂移到"啰嗦的助手"行为 ⇒ 安全对齐被稀释 ⇒ 顺从上升** ✗✓。

**支持该假说的三条独立观测**：
1. **响应中位从 148 涨到 179 token** ✓（长度确实被推高了 ✓）
2. **顺从迁移 70 : 0 单向** ✓ ⇒ 顺从出现在**响应后段** ✓，
   正是冗长格式（先复述载体 → 后段照做 ✓）的产物 ✓
3. **同一模型的契约块也退化 32.6%** ✓ ⇒ 格式与内容一起漂移 ✓

## M4 的假设（发射前登记，事后不许改口 ✓）

**H1（主）**：`dpo_m4_final.jsonl`（长度匹配后 ✓）在同一协议下重训，
**512 口径鲁棒性 ASR 应显著低于 m3-dpo 的 50.6%** ✓。
**判据**：若 M4 的 ASR ≤ **15%** ⇒ 长度混杂是主因 ✓，修复有效 ✓。
**反证**：若 M4 的 ASR 仍 ≥ **35%** ⇒ **长度混杂不是主因** ✗，
须回到**数据语义**（哪一类在教顺从 ✓）重查 ✓。

**H2**：M4 的响应 token 中位应**回落**（< 179 ✓），且契约保留率应**回升**（> 55% ✓）。
**★ H2 若成立而 H1 不成立** ⇒ 说明**长度**与**顺从**是**两个独立的损伤** ✓
⇒ 必须分别处置 ✓（不能因为"长度修好了"就认为安全也修好了 ✗）。

**H3（对照）**：起点本身在同一协议下的 ASR 应稳定在 ~5% ✓
（已实测 4.2%→4.8% ✓）⇒ 作为该协议的**噪声上界** ✓。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
OUT = ROOT / "reports" / "m4-hypothesis.json"


def main() -> int:
    h = {
        "causal_attribution": {
            "start": {"name": "soup-needlefix-a050", "stage": "SFT",
                      "caliber": 512, "asr": 8 / 168, "k": 8, "n": 168},
            "variant": {"name": "m3-dpo", "stage": "SFT + M3 DPO",
                        "caliber": 512, "asr": 85 / 168, "k": 85, "n": 168},
            "conclusion": "两者只差 M3 这一步 DPO ⇒ ASR 崩塌归因于该 DPO ✓",
        },
        "known_defect": {
            "file": "data/lf/dpo_m3_final.jsonl", "pairs": 28842,
            "length_confounded_pairs": 6540, "share": 6540 / 28842,
            "fix_candidate": "data/dpo-remediation-staging/dpo_m4_final.jsonl",
        },
        "settled_facts": {
            "response_token_median": {"start": 148, "m3_dpo": 179},
            "label_migration": {"gained_comply": 70, "lost_comply": 0,
                                "baseline_gained": 2, "baseline_lost": 1},
            "contract": {"start": 251 / 258, "m3_dpo": 142 / 258,
                         "genuine_loss_start": 4 / 258,
                         "genuine_loss_m3": 84 / 258},
        },
        "predictions": {
            "H1_main": {"claim": "M4 的 512 鲁棒性 ASR 显著低于 50.6%",
                        "pass_if": "ASR <= 0.15",
                        "refute_if": "ASR >= 0.35",
                        "meaning_if_pass": "长度混杂是主因，修复有效 ✓",
                        "meaning_if_refute": "长度混杂不是主因 ✗ ⇒ 回到数据语义查 ✗"},
            "H2": {"claim": "M4 的 tok 中位 < 179 且契约保留率 > 55%",
                   "note": "★H2 成立而 H1 不成立 ⇒ 长度与顺应是两个独立损伤 ✓"},
            "H3_control": {"claim": "起点在同协议下 ASR ≈ 5%",
                           "measured": "4.2% → 4.8% ✓", "role": "噪声上界"},
        },
    }
    OUT.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== 因果归因 ===")
    print("  起点(SFT)        512 ASR =  8/168 = 4.8%  ✓")
    print("  m3-dpo(SFT+DPO)  512 ASR = 85/168 = 50.6% ✗✗")
    print("  ⇒ 只差 M3 这一步 DPO ⇒ 归因干净 ✓")
    print("\n=== M4 的可证伪假设（发射前登记 ✓）===")
    print("  H1  512 ASR <= 15% ⇒ 长度混杂是主因 ✓ / >= 35% ⇒ 不是 ✗")
    print("  H2  tok 中位 < 179 且契约 > 55%（与 H1 独立 ✓）")
    print("  H3  起点 ~5% 作噪声上界 ✓（已实测 ✓）")
    print(f"\nreport -> {OUT.name}")
    print("M4-HYPOTHESIS=DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
