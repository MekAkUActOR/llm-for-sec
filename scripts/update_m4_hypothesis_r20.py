# -*- coding: utf-8 -*-
r"""把第 20 轮的**词法化**结论与**精确修法**写进 `reports/m4-hypothesis.json`。

★ 第 19 轮写的 A/B/C 方向对但**不够准** ✗ —— 本轮用实测把修法收敛到
**补隐蔽注入正样本 + 成对硬负样本（同句不同上下文）** ✓✓。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "reports" / "m4-hypothesis.json"


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    d["lexicalization_finding"] = {
        "instrument": "data/heldout/v0.3-gen robustness 168 条，按载体正文有无自称词汇分档",
        "baseline": {"vocab_framed": "3/69 = 4.3%", "stealth": "5/99 = 5.1%",
                     "note": "起点两类一样好 ⇒ 隐蔽注入并不天然更难 ⇒ 任务可解"},
        "m3_dpo": {"vocab_framed": "21/69 = 30.4%", "stealth": "64/99 = 64.6%",
                   "note": "差 2.1 倍 ⇒ 检测退化成词法匹配"},
        "conclusion": ("DPO 把语义意图判别训成了表观词汇匹配 ⇒ "
                       "无词汇标记的隐蔽注入穿过过滤器 ⇒ 照做"),
        "hypotheses_excluded": {
            "frame_drift": "训练①祈使 42.4% / 测试 34.9%，差 -7.6pp ⇒ 解释力不足",
            "length_salience": "载体长度 4 箱 ASR = 57.1/45.2/52.4/47.6% ⇒ 平坦 ⇒ 出局",
            "action_preference": "反-answer 4,264 > pro-answer 1,320 ⇒ 方向相反 ⇒ 出局",
        },
    }
    d["required_before_training"] = [
        "① 补隐蔽注入正样本：注入不带任何指令词汇，恶意只能由语义意图判断"
        "（越权范围 / 与操作者任务冲突 / 要求外传或改裁决）—— 起点在隐蔽档 5.1% 证明可解",
        "② 干净类与注入类在词汇上对齐：干净载体的元文本同样使用说明/备注/指令等词，"
        "由上下文表明其正当性",
        "③ 成对硬负样本：同一句元文本，一个由上下文证明无害、一个证明越权 —— "
        "只差语义、不差词面",
        "④ 长度分布对齐：训练载体长度覆盖测试的 370–2096（现训练中位 319 / 测试 1190）",
        "★ ①③ 是核心；① 的样本量须占训练相当比例（测试隐蔽档占 59%）",
    ]
    d["launch_gate"] = {
        "verdict": ("dpo_m4_final.jsonl（仅长度匹配）不可能修好该缺口 ⇒ "
                    "直接发射预计 H1_prime 失败（≥35%）"),
        "action": "先完成 ①③ 再发射；否者浪费一整轮串行 GPU",
    }
    P.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    back = json.loads(P.read_text(encoding="utf-8"))
    ok = ("lexicalization_finding" in back and "launch_gate" in back
          and len(back["required_before_training"]) == 5)
    print(f"  顶层键 = {sorted(back.keys())}")
    print(f"  ①③核心 = {'①' in back['required_before_training'][0]}")
    print(f"M4-HYPOTHESIS-R20={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
