# -*- coding: utf-8 -*-
r"""★★★★★ 把第 21 轮的定论与修法写进 `reports/m4-hypothesis.json` ✓。

★ 关键纪律：修法 ① 要用**起点自己的正确响应** ✓，
  但**绝不能拿留出集回灌** ✗（规则 13：门禁 eval 集与训练混料零重叠 ✓）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "reports" / "m4-hypothesis.json"


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    d["mechanism_established"] = {
        "round": 21,
        "verdict": "均匀的能力破坏（capability destruction），不是覆盖缺口或偏好反转",
        "decisive_contrast": {
            "in_distribution": ("v0.2.1 鲁棒性 64 条（载体/机制全为训练同族）"
                                "m3-dpo 33/64 = 51.6%，起点 8/64 = 12.5%"),
            "out_of_distribution": ("v0.3-gen 鲁棒性 168 条（av_metadata/image_metadata"
                                    "训练行数为 0）m3-dpo 92/168 = 54.8%，起点 8/168 = 4.8%"),
            "reading": "两者几乎相同 ⇒ 新载体/新机制不是因素；分布内一样失败",
        },
        "supporting": [
            "动作偏好数据方向相反：反-answer 4,264 对 > pro-answer 1,320 对，而模型更多 answer",
            "失败在检测而非偏好（识别失败 ⇒ 继续做原任务 ⇒ answer）",
            "v0.4-toolout 独立复现 13.0% → 67.4%",
            "只差 M3 DPO 一步 ⇒ 归因干净",
        ],
        "generator_corpus_facts": {
            "inject_rows": 4680,
            "carriers": {"tool_output": 858, "log": 780, "webpage": 780, "code": 780,
                         "document": 780, "email": 390, "text": 312},
            "carriers_absent": {"av_metadata": 0, "image_metadata": 0},
            "semantic_mechanisms": 14,
            "position": {"head": 1564, "mid": 1562, "tail": 1554},
            "language": {"zh": 2340, "en": 2340},
            "reading": "语义/位置/语言三轴充分覆盖；唯一缺口是 av/image 载体，但已证非致因",
        },
        "excluded_hypotheses": [
            "框架漂移", "长度显著性", "动作偏好", "词法化", "模板化背诵",
            "裁决伪造族覆盖缺口（训练里有 verdict_suppress 282 条）",
            "载体本体论覆盖缺口（分布内 51.6% ≈ 分布外 54.8%）",
        ],
    }
    d["required_before_training"] = [
        "① 保住 SFT 能力：偏好对里加入**起点自己正确检测**的样本（chosen=report，"
        "rejected=它当时的顺从行为）。★必须在**训练侧语料**上重跑起点取响应 —— "
        "**绝不能拿留出集回灌**（规则 13：门禁 eval 集与训练混料零重叠）",
        "② 加能力保持正则：训练目标锚定 SFT 策略（KL 或 rehearse），"
        "因为失效是均匀的，要的是保持而不是打补丁",
        "③ 逐轴验收：发射后在载体/机制/位置/语言四个轴上分别报 ASR（规则 41）",
        "④ 先小规模验证：用当前 DPO 配方 + 仅加①跑一版，看 ASR 是否从 54.8% 掉回 <15%",
    ]
    d["launch_gate"]["verdict"] = (
        "dpo_m4_final.jsonl（仅长度匹配）修不好 ASR —— 失效是均匀的能力破坏，"
        "长度匹配不增加任何检测能力。必须先做 ①（能力锚回）再发射。")
    P.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    back = json.loads(P.read_text(encoding="utf-8"))
    ok = ("mechanism_established" in back
          and len(back["required_before_training"]) == 4
          and "留出集回灌" in back["required_before_training"][0]
          and "均匀的能力破坏" in back["mechanism_established"]["verdict"])
    print(f"  顶层键 = {sorted(back.keys())}")
    print(f"  已登记排除的假说 = {len(back['mechanism_established']['excluded_hypotheses'])} 条")
    print(f"  修法条数 = {len(back['required_before_training'])}")
    print(f"  含留出集红线 = {'留出集回灌' in back['required_before_training'][0]}")
    print(f"M4-HYPOTHESIS-R21={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
