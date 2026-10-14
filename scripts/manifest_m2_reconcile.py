#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M2 期 manifest 行对账（16 行 status='procured' 的记账体检）。

背景：这 16 行是 2026-09-25 抓取的 M2 SFT/DPO 来源，manifest 记为
status='procured'、est_tokens=0、无 ingested_at；但原始目录在盘、且部分源
**确实进了训练集**（cvalues/pku-saferlhf → data/lf/dpo_m3.jsonl；双误拒件
与 wildguard/wildjailbreak 见 d3-ledger-memo §3 分级清单）。
d3-ledger-memo §5 早已登记此缺口："M2 SFT 原料层 tokens 为粗估，T2/T3 占比
待 SFT mix 定稿后复核"——mix 现已在 2026-09-30 定稿（sft_m25 137,670 行）。

本脚本只**测量与并列证据**，不改 manifest（行改写属记账口径决策）。
输出：reports/manifest-m2-reconciliation.md
用法：python scripts/manifest_m2_reconcile.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"
OUT = ROOT / "reports" / "manifest-m2-reconciliation.md"

# docs/research/m2-sft-sources.md 的逐源量级/角色摘录（行号为准，人工核对）
DOC = {
    "safety-prompts": ("§2.2 L81", "100K 对 ≈30MB zh ≈12–18M zh tokens（zh 最大单源）"),
    "xstest": ("§2.8 L108", "250 prompts ≈0.3M tokens（误拒测量；输入侧种子+eval）"),
    "or-bench": ("§2.9 L109", "or-bench-80k + hard-1k(1,320) + toxic（误拒测量）"),
    "tc260": ("§2.10 L117", "2,903 行 ≈0.7–1M zh tokens（ref-only，不入权重）"),
    "cvalues": ("§2.11 L122", "14.5 万对比对（prompt+双响应+人标，Apache-2.0）"),
    "pku-saferlhf": ("L45", "330K 偏好对（CC-BY-NC-4.0，T2）"),
    "beavertails": ("L46", "330K QA + 361K 危害标注（CC-BY-NC-4.0，T2）"),
    "wildguardmix": ("L47", "92K prompt-response 审核对（AI2 OUFRA+门控，T3）"),
    "wildjailbreak": ("L48", "426K 对抗对话（ODC-By+门控，T3）"),
    "hh-rlhf-harmlessness": ("L15", "42.5K harmlessness 对（MIT）"),
    "safemtdata": ("L15", "600 条（MIT）"),
    "trustllm-safety": ("L6", "TrustLLM 基准（已克隆 raw/m2-research）"),
    "advbench": ("§采购表", "攻击提示基准"),
    "harmbench": ("§采购表", "攻击/防御基准"),
    "strongreject": ("L6", "攻击强度基准（raw/m2-research）"),
    "maliciousinstruct": ("§采购表", "恶意指令基准"),
}

# 实际入训证据（人工登记的确定性事实；来源见括号）
USAGE = {
    "cvalues": "✅ 入 DPO 对（dpo_m3 类 policy/无差别攻击侧 cv 系；m1 assembler SUBCAPS cv 4,800 行）",
    "pku-saferlhf": "✅ 入 DPO 对（pku 系；m1 SUBCAPS pku 3,600 行）",
    "safety-prompts": "✅ 入 SFT（docs/06 m1 配方 T5-attack/T12 政策问答 zh 侧）",
    "tc260": "⛔ ref-only（永不入权重；仅评估/分类参照）",
    "xstest": "◐ eval 侧复用（误拒测量）；训练侧未登记",
    "or-bench": "◐ eval 侧复用（误拒测量）；训练侧未登记",
    "wildguardmix": "✅ 登记入 m1（T1/T5 输入侧清洗源）",
    "wildjailbreak": "✅ 登记入 m1（对抗转化源）",
    "beavertails": "◐ 用户拍板纳入 M2 第二批；是否入 m1 未在源文档逐条登记",
    "hh-rlhf-harmlessness": "◐ 同上（MIT 主力候选）",
    "safemtdata": "◐ 同上",
    "trustllm-safety": "◐ 同上",
    "advbench": "◐ 同上",
    "harmbench": "◐ 同上",
    "strongreject": "◐ 同上",
    "maliciousinstruct": "◐ 同上",
}


def dir_size(p: Path) -> tuple[int, int]:
    """(bytes, files) 递归统计。"""
    b = n = 0
    for f in p.rglob("*"):
        if f.is_file():
            b += f.stat().st_size
            n += 1
    return b, n


def main() -> int:
    rows = [json.loads(l) for l in MANIFEST.open(encoding="utf-8") if l.strip()]
    targets = [r for r in rows if r.get("status") != "ingested"]
    L = ["# M2 期 manifest 行对账（16 行 status='procured'）", "",
         "生成：`scripts/manifest_m2_reconcile.py`（只测量，不改 manifest）", "",
         "| id | 声明 tier | 盘上原始体量 | 文件数 | 首见 mtime | 文档量级 | 实际入训证据 |",
         "|---|---|---|---|---|---|---|"]
    tot = 0
    for r in sorted(targets, key=lambda x: x["id"]):
        files = r.get("files") or []
        b = n = 0
        mtime = "—"
        for raw in files:
            p = ROOT / raw
            if p.is_dir():
                db, dn = dir_size(p)
                b += db
                n += dn
                mt = max((f.stat().st_mtime for f in p.rglob("*")
                          if f.is_file()), default=p.stat().st_mtime)
                import datetime
                mtime = datetime.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M")
            elif p.is_file():
                b += p.stat().st_size
                n += 1
        tot += b
        doc = DOC.get(r["id"], ("—", "—"))
        L.append(f"| `{r['id']}` | {r.get('tier')} | {b/1e6:.2f} MB | {n} | "
                 f"{mtime} | {doc[0]} {doc[1]} | {USAGE.get(r['id'], '?')} |")
    L += ["", f"**合计原始体量：{tot/1e6:.1f} MB**（manifest 现记 est_tokens=0）", "",
          "## 三个待决问题（记账口径）", "",
          "1. **status**：这些源既已抓取且部分已入训——是否统一改 `ingested`"
          "（另设 `role` 字段区分 train/eval/reference）？tc260 已 ref-only，"
          "改动仅涉其余 15 行。",
          "2. **ingested_at**：按盘上 mtime（2026-09-25 09:49–10:29）填，"
          "还是按实际入训日（m1 组装 2026-09-26 / DPO 对 2026-09-26）填？",
          "3. **est_tokens**：填**原料层**体量（会与 SFT 产物谱系行重复计入总账，"
          "需在卡上标注「SFT 原料层」分区）还是填**实际入训用量**"
          "（更贴 M5 权重成分口径，但需逐行溯源；当前可用上界=原料层）？", "",
          "证据文件：`reports/manifest-audit.json`、本表；"
          "工具：`scripts/audit_manifest.py`（可复跑）。"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\n报告 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
