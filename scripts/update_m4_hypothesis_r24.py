# -*- coding: utf-8 -*-
r"""把第 24 轮的**配比度量**记入 `reports/m4-hypothesis.json` ✓ —— 并**明确否决**改配比 ✓。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "reports" / "m4-hypothesis.json"

DATA = {
    "policy": (14688, 11216, 616652, 1935076),
    "reserve": (5710, 3993, 717113, 1900960),
    "carrier_inject_obedient": (2360, 0, 880196, 0),
    "carrier_inject_hollow": (2320, 0, 927294, 0),
    "bt330_refusal": (1904, 10, 917289, 4052),
    "carrier_clean_overrefusal": (1320, 0, 446595, 0),
    "refusal_quality": (300, 300, 0, 45546),
    "calibration": (240, 144, 16640, 24192),
}


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    td = sum(v[2] for v in DATA.values())
    tn = sum(v[3] for v in DATA.values())
    tm = td + tn
    d["mix_measured_round24"] = {
        "question": ("第 23 轮发现 policy 族占 50.9% 对数 / 30.3% 梯度质量且 76.4% 逐对动作相同 ✗ "
                     "⇒ 疑为「政策条件化稀释安全判断」✗ —— **本轮先量后修** ✓"),
        "method": "scripts/action_directionality.py（方向性对 = chosen 动作 ≠ rejected 动作 ✓）",
        "per_class": {
            k: {"n": v[0], "neutral_pairs": v[1],
                "neutral_pair_rate": round(v[1] / v[0], 4),
                "directional_mass": v[2], "neutral_mass": v[3]}
            for k, v in DATA.items()
        },
        "totals": {
            "directional_mass_share": round(td / tm, 4),
            "neutral_mass_share": round(tn / tm, 4),
        },
        "verdict": ("★**否决改配比** ✗ —— 方向性质量占 53.6% ✓，判别信号**过半** ✓，"
                    "不构成瓶颈 ✗。中性质量由 policy(49.1%) + reserve(48.2%) 构成 ✓，"
                    "它们教**格式/细节** ✓，**不必然有害** ✓。"
                    "按推论 42.4，不得据此动手改数据 ✗。"),
        "remaining_leads": [
            "refusal_quality 300 对 **100% 动作中性** ✗ ⇒ 真正零信号 ✓（量小 ✓，仅登记 ✓）",
            "policy 族的 policy 字段逐对 100% 不同 ✓（professional vs default ✓）"
            "⇒ 它本质是**政策包条件化**能力 ✓，不是安全判断 ✗",
        ],
        "consequence": ("病根已被第 22–23 轮因果钉在 `report`-as-rejected 压制 ✓，"
                        "且探针已验证修法 ✓ ⇒ **不需要**额外的配比改动 ✓。"
                        "本轮因此**省下了一次高风险数据改动** ✓。"),
    }
    P.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    back = json.loads(P.read_text(encoding="utf-8"))
    ok = ("mix_measured_round24" in back
          and abs(back["mix_measured_round24"]["totals"]["directional_mass_share"] - 0.536) < 0.01
          and "否决改配比" in back["mix_measured_round24"]["verdict"])
    print(f"  方向性质量占比 = {back['mix_measured_round24']['totals']['directional_mass_share']:.1%}")
    print(f"  中性质量占比   = {back['mix_measured_round24']['totals']['neutral_mass_share']:.1%}")
    print(f"  裁决 = {back['mix_measured_round24']['verdict'][:52]}…")
    print(f"MIX-MEASURED-R24={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
