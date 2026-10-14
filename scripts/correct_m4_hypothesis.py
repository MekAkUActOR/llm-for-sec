# -*- coding: utf-8 -*-
r"""★更正 `reports/m4-hypothesis.json` 里已不可采信的 `lexicalization_finding` ✓。

该字段是第 20 轮早期写的 ✗，其分档键（"有无自称词汇"）实测只是**语言**的代理 ✗，
且 `language` 字段本身也不是载荷语言 ✗ ⇒ 按规则 42.4 **降级为线索** ✓。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "reports" / "m4-hypothesis.json"


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    old = d.pop("lexicalization_finding", None)
    d["round20_leads_not_established"] = {
        "status": "线索（按规则 42.4 未采信）— 机制尚未确立",
        "why_downgraded": (
            "分档键『有无自称词汇』的关键词表只有中文 ⇒ 实际捕获的是『英文载荷』，不是『隐蔽载荷』；"
            "改用 language 字段复算得 en 74.4%/zh 27.9%，但该字段是条目语言、不是载荷语言"
            "（86 条 language=zh 里 64 条载荷是英文）；改用整段正文定语言 ⇒ 168 条全判 en"
            "（结构化 ASCII 淹没注入）"),
        "superseded_claim": (old or {}).get("conclusion"),
        "excluded_mechanisms": {
            "frame_drift": "训练①祈使 42.4% / 测试 34.9%，差 <8pp ⇒ 出局",
            "length_salience": "载体长度 4 箱 ASR = 57.1/45.2/52.4/47.6% ⇒ 平坦 ⇒ 出局",
            "action_preference": "反-answer 4,264 > pro-answer 1,320 ⇒ 方向相反 ⇒ 出局",
            "template_repetition": "训练复用 2.5×（940 去重/2360）、最常见模板仅 3 次 ⇒ 出局",
        },
        "sample_level_lead": (
            "训练注入多声称**虚假权威/信任级别**（platform-managed channel / "
            "highest-priority system-region text）；测试注入多要求**伪造裁决/隐瞒证据**"
            "（report as compliant / omit the URL / state the file passed every check）。"
            "关键词分类下『裁决伪造族』训练 5.2% vs 测试 31.9%（6.2×），"
            "但训练侧 93.9% 未分类 ⇒ 只作线索"),
        "next_round_method": (
            "★ 不要再用关键词分类。先用**成对差分**（carrier_inject_* vs carrier_clean_*）"
            "把训练侧的注入行**定位**出来，测试侧用 [text-bearing] 标记或 intent 的载荷字段；"
            "两侧打印样本确认后，才做统计（规则 42.1/42.2）"),
    }
    d["launch_gate"]["verdict"] = (
        "dpo_m4_final.jsonl（仅长度匹配）修不好 ASR —— 理由独立于未定的机制："
        "长度匹配不增加任何检测能力，而失效在『检测』而非『偏好』"
        "（反-answer 4,264 > pro-answer 1,320 而模型反而更多照做）")
    P.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    back = json.loads(P.read_text(encoding="utf-8"))
    ok = ("lexicalization_finding" not in back
          and "round20_leads_not_established" in back
          and "检测能力" in back["launch_gate"]["verdict"])
    print(f"  顶层键 = {sorted(back.keys())}")
    print(f"  旧字段已移除 = {'lexicalization_finding' not in back}")
    print(f"  线索已登记   = {'round20_leads_not_established' in back}")
    print(f"M4-HYPOTHESIS-CORRECTED={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
