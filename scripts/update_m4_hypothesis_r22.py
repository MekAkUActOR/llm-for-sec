# -*- coding: utf-8 -*-
r"""★★★★★★★ 把第 22 轮的**因果定论与已完成的修法**写进 `reports/m4-hypothesis.json` ✓。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "reports" / "m4-hypothesis.json"


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    d["mechanism_established"] = {
        "round": 22,
        "verdict": ("`report`（注入抵抗的正确动作）被 DPO 的 rejected 侧全局压制 —— "
                    "算术上定量吻合"),
        "evidence": {
            "logps_chosen_delta": "+22.01",
            "logps_rejected_delta": "-151.93",
            "rewards_chosen_delta": "+0.29",
            "rewards_rejected_delta": "-12.46",
            "rejected_share_of_margin": "97.7%",
            "effective_gradient_ratio": "约 43:1（压低 : 抬高）",
            "report_as_chosen": 4680,
            "report_as_rejected": 1320,
            "report_as_rejected_where": "全部在 carrier_clean_overrefusal",
            "effective_strength": "压低 56760 vs 抬高 4680 ⇒ 12 倍压制",
            "curve": ("rewards/accuracies 0.325→0.9375（max 1.0）；"
                      "margins 0.036→12.81（×359）；loss 0.679→0.112"),
        },
        "reading": ("取胜的不是对数而是梯度方向：4,680 条教抵抗的对敌不过 1,320 条把 report "
                    "放在 rejected 侧的对，因为 DPO 的梯度几乎只在压低 rejected"),
    }
    d["excluded_hypotheses_final"] = [
        "框架漂移", "长度显著性", "动作偏好（数据量）", "词法化", "模板化背诵",
        "裁决伪造族覆盖缺口（训练有 verdict_suppress 282 条）",
        "载体本体论覆盖缺口（分布内 51.6% ≈ 分布外 54.8%）",
        "数据配比稀释（真抵抗对 32.6%、有效信号 45.7%）",
        "偏好环（环存在但按违例代价仍应偏好 report）",
        "良性负例不可判别（解剖：干净支标注行 0/354 面向 AI ⇒ 可分）",
        "同句反标（仅 483/6000 = 8.1%，不足）",
        "单条样本误判（83/85 是良构 VERDICT + action=answer）",
    ]
    d["fix_implemented"] = {
        "artifact": "data/dpo-remediation-staging/dpo_m4_capfix.jsonl",
        "bytes": 59793275,
        "rows": 28842,
        "supersedes": "dpo_m4_lenmatch.jsonl.superseded（长度匹配版，已退役改名）",
        "change": ("carrier_clean_overrefusal 的 1,320 条 rejected 侧整体重写为「过度谨慎」："
                   "action report→refuse、verdict contains-injection→hold、"
                   "去掉「检出注入/上报」措辞"),
        "length_ratio": 0.97,
        "verification": ("scripts/verify_capfix.py 7 项全绿 CAPFIX-VERIFY=PASS；"
                         "关键：report 作 rejected = 0、非干净支改动 0 行、"
                         "report 作 chosen 仍 4680"),
        "why_rename": ("本体论作用域 data/dpo-remediation-staging/*.jsonl 会双计两个版本"
                       "（实测 computed 恰为 ontology 的 2×），故退役件改名避开 glob"),
    }
    d["required_before_training"] = [
        "① 已做：capfix 让 report 永不作 rejected（天平从 1320 压制:4680 提升 转为纯 4680 提升）",
        "② 小规模验证：先用 capfix 跑一版，确认未见载体 ASR 从 54.8% 回落；"
        "并做 dpo_m4_lenmatch（仅长度）vs dpo_m4_capfix（长度+capfix）两版对照",
        "③ 逐轴验收：载体/机制/位置/语言四轴分别报 ASR（规则 41）",
        "④ 残留（未处理，须随产物交付）：policy 14,688 对（50.9%）动作轴零信号；"
        "refusal_quality 300 对零信号；同句反标 483 条（推论 41.5）",
    ]
    d["launch_gate"]["verdict"] = (
        "dpo_m4_capfix 已就绪但**未经训练验证** —— 必须先小规模跑确认 ASR 回落才可发射全量。"
        "仅长度匹配的版本已证明不够（长度匹配不增加检测能力，而失效在 report 被压制）。")
    P.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    back = json.loads(P.read_text(encoding="utf-8"))
    ok = ("mechanism_established" in back and back["mechanism_established"]["round"] == 22
          and back["fix_implemented"]["rows"] == 28842
          and "report 永不作 rejected" in back["required_before_training"][0])
    print(f"  顶层键 = {sorted(back.keys())}")
    print(f"  机制 = {back['mechanism_established']['verdict'][:56]}…")
    print(f"  排除假说 = {len(back['excluded_hypotheses_final'])} 条")
    print(f"  修法产物 = {back['fix_implemented']['artifact']}")
    print(f"M4-HYPOTHESIS-R22={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
