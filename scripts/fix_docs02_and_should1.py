# -*- coding: utf-8 -*-
"""办结两处：①docs/01 §12-8（docs/02 已就地更正）；②SHOULD-1 更名为"非载体级"口径。"""
from pathlib import Path

EDITS = [
    ("docs/01-engineering-definition.md",
     "| 8 | **对 docs/02 的同步修订**：本文 §3.1 已把规模修正为 0.6B / 1,088M token | "
     "`docs/02-m0-base-audit.md:32` 仍写\"与 docs/01 §3.1 目标规模（10–30B）匹配\""
     "——**本次未改 docs/02**（超出\"只改一个文件\"的授权范围） | 父代理 |",
     "| 8 | ~~**对 docs/02 的同步修订**~~ **已闭环（2026-09-30 晚）** | "
     "`docs/02-m0-base-audit.md:32` 的作废行**已就地加划线 + 紧随其后的\"（2026-09-30 修正）\"区块**"
     "（第 34 行起）逐条说明两处不符：\"与 docs/01 §3.1 目标规模（10–30B）匹配\"不再成立、"
     "以及 5–20B token / 2.5–10 天的估算已废。**正文一字未重写，采用\"划线保留 + 更正区块\"**"
     "以存过程。 ⇒ 本条无需再裁决 | 父代理（已办） |"),

    ("reports/m3-dpo-preregistration.md",
     "| SHOULD-1 | 在训载体 ASR（v0.2.1） | 劣化 ≤ **0.05** | 0.1406 |",
     "| SHOULD-1 | **在训语料 ASR（v0.2.1 鲁棒性 64，★非载体级）** | 劣化 ≤ **0.05** | 0.1406 |"),
]

# SHOULD-1 更名的理由块（追加在预注册 §4 表格之后）
RATIONALE = """
> **★SHOULD-1 的口径更正（2026-09-30 晚，依载体本体论审计 D4）**：原名"在训**载体** ASR"**不准确**。
> 本体论审计实测 `data/heldout/v0.2.1` 的 161 行中 **144 行没有载体标签**，
> 其余也仅个别带标记 ⇒ **v0.2.1 不是载体级仪器**（`reports/carrier-ontology-report.md` D4、
> `reports/s1-ontology-adjudication.md` §2）。
> 因此该轴测的是"**在训语料上的攻击成功率**"（鲁棒性子集 n=64），
> **不能**被引用为"未见载体泛化"或"载体级鲁棒性"的证据；本项目的未见载体证据**只**来自
> `data/heldout/v0.3-gen` 的 image_metadata（126/鲁棒性 80）与 av_metadata（132/鲁棒性 88）两族。
> 判据阈值不变（劣化 ≤0.05），**只改名称与可支撑结论的边界**，不改判定。
"""

for f, old, new in EDITS:
    p = Path(f)
    t = p.read_text(encoding="utf-8")
    if t.count(old) != 1:
        print(f"!! fail-closed：{f} 未唯一匹配（{t.count(old)} 次），未写入")
        raise SystemExit(2)
    t = t.replace(old, new)
    if f.endswith("preregistration.md"):
        anchor = "SHOULD 不过 → 登记为\"有条件成立\"，不单独否决"
        if anchor in t and "SHOULD-1 的口径更正" not in t:
            t = t.replace(anchor, RATIONALE.strip() + "\n\n" + anchor, 1)
    p.write_text(t, encoding="utf-8")
    print(f"✅ {f}")
