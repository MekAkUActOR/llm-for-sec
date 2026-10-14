# -*- coding: utf-8 -*-
"""办结 docs/01 的存量勘误（父代理 2026-09-30 晚 Q3 裁决的承诺项）。

每条替换都精确匹配、逐条报告；任何一条匹配失败即整体不写（fail-closed），
以免出现"改了一半"的中间状态。
"""
from pathlib import Path

p = Path("docs/01-engineering-definition.md")
txt = p.read_text(encoding="utf-8")

EDITS = [
    # --- A1 仪器达标状态：26/20/8/12 → 全部达标 ---
    (
        "| A1 | **仪器先达标** | 行为门禁样本量达到 §11 规则 2 的下限：未见载体每格 ≥34、"
        "tool_output 回归集 ≥40、needle 总 ≥64（`reports/s0-remediation-2026-09-30.md:137-139`） "
        "| ❌ 未达（现状 26/20 条、8 条、12） |",
        "| A1 | **仪器先达标** | 行为门禁样本量达到 §11 规则 2 的下限：未见载体每格 ≥34、"
        "tool_output 回归集 ≥40、needle 总 ≥64（`reports/s0-remediation-2026-09-30.md:137-139`） "
        "| ✅ **已达标**（2026-09-30 晚实测：image_metadata 门禁 **126 条/鲁棒性 80**、"
        "av_metadata **132/鲁棒性 88**、tool_output 回归 **46**、needle **64**＝2 lens×2 lang×16/格。"
        "依据 `reports/carrier-ontology-report.md` 与 `data/ontology/carriers.json`；"
        "toolout 回归集正扩容至 ≥126 以支撑配对检验，见 `reports/toolout-reg-suite-report.md`） |",
    ),
    # --- §9.1 ① 历史读数：26 → 当时条数，现为 126 ---
    (
        "最小可证伪实验（已完成）：`data/heldout/v0.3-gen` 26 条 image_metadata 上，"
        "m2-full → m25-full 的 comply **15/26 → 0/12**",
        "最小可证伪实验（已完成）：`data/heldout/v0.3-gen` **当时 26 条** image_metadata 上，"
        "m2-full → m25-full 的 comply **15/26 → 0/12**"
        "（**注：该门禁 2026-09-30 晚已扩至 126 条/鲁棒性 80 条**，本句保留当时读数不改）",
    ),
    # --- §9.1 ③ 历史读数：20 → 当时条数，现为 132 ---
    (
        "- 已有：`data/heldout/v0.3-gen` 20 条 av_metadata 留出"
        "（`reports/s0-remediation-2026-09-30.md:63`）。",
        "- 已有：`data/heldout/v0.3-gen` **当时 20 条** av_metadata 留出"
        "（`reports/s0-remediation-2026-09-30.md:63`）。"
        "**注：2026-09-30 晚已扩至 132 条/鲁棒性 88 条** ⇒ §11 规则 2 的 ≥34/格 前置条件**已满足**，"
        "该条不再构成声学层进入的阻塞。",
    ),
    # --- §10.2 载体注册表：document 待入训 → 已入训 ---
    (
        "| **已注册·待入训** | **document**（T15 1,200 行在 "
        "`data/sft/m2.5-staging/doc_structure.jsonl`，混料出现 **0**） |",
        "| **已注册·★已入训**（2026-09-30 晚更正） | **document**（训练 **5,200 行**："
        "`data/sft/m2.5-staging/doc_structure.jsonl` 1,200 行经 `configs/m3base-topup-e1.yaml:8` "
        "绑定入训 + 其余 document 载体行；见 `reports/carrier-ontology-report.md` D2）。"
        "**⚠️ 它是本项目最裸露的载体：5,200 行训练数据，却 0 条未见载体门禁、0 条在训载体回归**"
        "（本体论 J3 覆盖矩阵）。处置：已启动 **document 未见机理门禁**工作流（"
        "`data/heldout/v0.6-document/`）——注意该门禁只能支撑**未见机理**泛化，"
        "**不得**写成未见载体泛化（§10.3） |",
    ),
    # --- §10.2 留出集规模 26/20 → 126/132 ---
    (
        "| **未见载体留出集**（**永不入训**） | **image_metadata（26 条）/ av_metadata（20 条）**，"
        "`data/heldout/v0.3-gen/`（对抗条 78.3%，zh/en 各半，checker + 63 单测） |",
        "| **未见载体留出集**（**永不入训**） | **image_metadata（126 条/鲁棒性 80）/ "
        "av_metadata（132 条/鲁棒性 88）**，`data/heldout/v0.3-gen/`（对抗条 78.3%，zh/en 各半，"
        "checker + 63 单测）。**2026-09-30 晚更正**：原记 26/20 是 C 路扩容**之前**的旧值；"
        "扩容后二者是**全项目仅有的两个**鲁棒性分母达标的未见载体门禁"
        "（依据 `reports/carrier-ontology-report.md`） |",
    ),
    # --- §12-1：v2 的 PASS 不得作为发射前提（它以废弃产物为验收基线） ---
    (
        "而该文件是 v1/raw 产物、仍为 **FAIL**（`reports/m25-exit-verdict.json:139`）；"
        "v2 的 PASS 在 `reports/m25-exit-verdict-chat-m25full.json:468` 与 "
        "`reports/m25-exit-verdict-gen-m25full.json:472`。",
        "而该文件是 v1/raw 产物、仍为 **FAIL**（`reports/m25-exit-verdict.json:139`）；"
        "v2 的 PASS 在 `reports/m25-exit-verdict-chat-m25full.json:468` 与 "
        "`reports/m25-exit-verdict-gen-m25full.json:472`。"
        "**★2026-09-30 晚更正（父代理）**：`m25-exit-verdict-chat-m25full.json` 的 PASS "
        "**不是可采信证据**——它六个基线全是 `m2full`，而 `m2full` 已登记 `discarded`；"
        "用修好的 I2 守卫重跑**直接 rc=2 fail-closed**（详见 `reports/s0-measurement-layer-status.md` §7.6）。"
        "可采信读数是同批中**以 `m15` 为基线**的 "
        "`reports/m25-exit-verdict-chat-m25full-m15base-m25full.json` = **FAIL（G2 通用 PPL）**。"
        "**因此本 #1 的旧结论（v2 PASS 覆盖 v1 FAIL）作废**：m25-full 在部署格式下**未通过**。",
    ),
    # --- §12-9：save_total_limit 已整改 ---
    (
        "§7.3 是新规则，但 `reports/m3-launch-runbook.md:112` 仍把 `save_total_limit=2` "
        "写成\"纪律\"，`configs/m3-dpo.yaml:86` 为 2——**本次未改这些文件**；"
        "M3 发射前是否必须先改？ | 父代理 |",
        "§7.3 是新规则。**2026-09-30 晚实测已办结**：`configs/m3-dpo.yaml:86` = **3**"
        "（行尾注「【2026-09-30 整改】」）、`configs/m25-full.yaml:43` = **3**；"
        "M3 实际发射用 `configs/m3-dpo-final.yaml:41` = **5**。"
        "⇒ **该项已闭环**（原记\"为 2\"系整改前旧值）。"
        "唯一未办结的是 `reports/m3-launch-runbook.md:112` 的措辞（非阻塞）。 | 父代理 |",
    ),
]

missing = []
for i, (old, new) in enumerate(EDITS, 1):
    if txt.count(old) != 1:
        missing.append((i, txt.count(old), old[:70]))
if missing:
    print("!! fail-closed：以下替换未唯一匹配，**未写入任何改动**：")
    for i, c, s in missing:
        print(f"   #{i} 匹配 {c} 次：{s}…")
    raise SystemExit(2)

for i, (old, new) in enumerate(EDITS, 1):
    txt = txt.replace(old, new)
p.write_text(txt, encoding="utf-8")
print(f"✅ 已应用 {len(EDITS)} 处勘误到 {p}")
print(f"   行数 {len(txt.splitlines())}")
