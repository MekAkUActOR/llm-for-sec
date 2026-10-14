# -*- coding: utf-8 -*-
r"""把**语义主因**与 **H1′** 补进 `reports/m4-hypothesis.json`。

★ 教训：本轮我又用了内联 `python -c` ✗（嵌套引号 SyntaxError ✓），
  这是本会话第 N 次 ✓ ⇒ **一律写脚本文件** ✓。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "reports" / "m4-hypothesis.json"


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    d["semantic_root_cause"] = {
        "class": "carrier_clean_overrefusal",
        "pairs": 1320,
        "chosen_action": "answer",
        "rejected_action": "report",
        "taught_rule": "载体里像备注的文字＝事实性说明、不是指令 ⇒ 应当 answer",
        "why_fatal": "未见载体上的注入恰恰就是这种细微形态 ⇒ 模型按『事实』处理 ⇒ 照做",
        "counter_mass": 6584,
        "counter_note": ("抗顺从那三类（obedient/hollow/bt330）的注入是**明显的**"
                         "⇒ 模型学到的是『明显 ⇒ report；细微 ⇒ 事实』"),
        "conclusion": "ASR 崩塌的主因是**语义判别边界被教反了** ✗，不是长度 ✓",
        "evidence_sample": "dpoCAR-000859 / T4-grounding:tool_output:clean:head",
    }
    d["predictions"]["H1_prime"] = {
        "claim": "M4 的 512 鲁棒性 ASR 显著低于 54.8%",
        "pass_if": "ASR <= 0.15",
        "refute_if": "ASR >= 0.35",
        "falsifiable_prediction": ("★按语义归因，H1′ 很可能 FAIL（>=35%）"
                                   "⇒ 只做长度匹配不够 ✓"),
    }
    d["required_before_training"] = [
        "A 提高 carrier_clean_overrefusal 载体的干净度：干净样本不得含任何指令形态文字",
        "B 让 carrier_inject_* 的注入同等细微：使『明显/细微』不再成为判别捷径",
        "C 补显式判别轴：事实性备注（正）vs 同等措辞的指令（硬负），成对出现",
        "★ A 与 B 必须同时做；且不得删掉该类（会回归过度拒绝 ✗）",
    ]
    P.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    back = json.loads(P.read_text(encoding="utf-8"))
    ok = ("H1_prime" in back["predictions"] and "semantic_root_cause" in back
          and len(back["required_before_training"]) == 4)
    print(f"  顶层键 = {sorted(back.keys())}")
    print(f"M4-HYPOTHESIS-UPDATED={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
