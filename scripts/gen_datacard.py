"""MODEL_DATA_CARD.md 生成器：manifest.jsonl → 语料总账数据卡（M5 发布件）。

设计依据：docs/research/cc-by-sa-precedent.md §3（先例最佳实践——RedPajama
式逐子集许可指针 + 我们更强的逐字许可引用）+ §4 前置动作③；
分级依据：docs/research/d3-ledger-memo.md §3（T1/T2/T3/ref-only）。

特性：
- **逐源**：名称 / URL / 许可逐字（manifest license 字段原样，管道符转义）
  / docs / tokens / 占比 / D3 分级；
- **头部汇总**：总 tokens、按许可家族分布、按 tier 分布；
- **语料态绑定**：数据卡记录生成时间 + manifest 文件 sha256——manifest
  变更后数据卡即过期（重跑再生，防漂移；对应探针 v0.3 的 sha256 锁惯例）；
- **下游用户提示**：Dolma 式"源级许可传递"提示（给用户的告知，非我方义务）；
- **SFT 谱系与评估注意事项**：manifest 之外的 SFT 产物（sec_sft_m25）与探针
  污染评估口径在生成器内静态登记（可复现——直改 MODEL_DATA_CARD.md 会被覆盖）。

TIER_MAP 手工镜像 d3-ledger-memo §3（来源→分级），runtime 断言全 manifest
行都有分级（manifest 新增源而未评 tier → 报 unclassified 警告并计入
"未分级"，防止台账静默漂移）。

用法：python scripts/gen_datacard.py   （幂等，输出覆盖 MODEL_DATA_CARD.md）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"
OUT = ROOT / "MODEL_DATA_CARD.md"

# ------------------------------------------------------------- D3 分级 --
# 镜像 docs/research/d3-ledger-memo.md §3（2026-09-25 整合版）。
# T1 可直接发布 / T2 需剥离重训 / T3 需法务确认 / ref-only 不入训参照物。
TIER_MAP: dict[str, str] = {
    # T1 可直接发布（署名/NOTICE 义务即可）—— d3-ledger-memo §3 T1 清单
    "arxiv-cscr-full": "T1", "arxiv-aisafety": "T1", "arxiv-privacy": "T1",
    "arxiv-cscr": "T1",
    "nist": "T1", "nist-privacy": "T1", "kev": "T1",
    "redhat-csaf": "T1", "gdpr-full": "T1", "or-bench": "T1", "xstest": "T1",
    "ghsl-advisories": "T1", "advbench": "T1", "harmbench": "T1",
    "strongreject": "T1", "safemtdata": "T1", "trustllm-safety": "T1",
    "hh-rlhf-harmlessness": "T1", "p0-0days": "T1", "atlas": "T1",
    "safety-prompts": "T1", "cvalues": "T1",
    "cwe": "T1", "capec": "T1", "mitre-attack": "T1", "cve": "T1",
    "cn-laws": "T1", "cn-laws-full": "T1", "cn-regs": "T1", "gdpr": "T1",
    "debian-dsa": "T1",
    # T6 采购（2026-09-28；d3-ledger-memo §5 缺口条 + §6"许可记账以 canonical
    # 上游为准"）——两源按 canonical 许可落 T1，行级衍生落 T3（评审前重估）：
    "t6_devign": "T1",        # MIT（epicosy/devign 镜像 LICENSE 逐字）
    "t6_cvefixes": "T1",      # CC-BY-4.0（canonical Zenodo；hf 镜像 apache-2.0 不可信）
    "t6_devign_lines": "T3",  # 上游 MIT，DetectVul 行级衍生卡未标 license
    # T2 需剥离重训（禁止性条款：NC / all-rights-reserved / 未授权）
    "msrc-cvrf": "T2", "sans-isc": "T2", "cisco-psirt": "T2",
    "oracle-cpu": "T2",
    "pku-saferlhf": "T2", "beavertails": "T2",  # M2 第二批（NC，用户拍板纳入）
    # T3 需法务确认（copyleft / ShareAlike / 未公示 / 混合引用）
    "enwiki-gen": "T3", "zhwiki-gen": "T3", "zhwiki-sec": "T3",
    "owasp-cs": "T3", "owasp-rtg": "T3", "owasp-top10": "T3",
    "maliciousinstruct": "T3",
    "gtfobins": "T3", "lolbas": "T3", "aiid": "T3",
    "credential-formats": "T3",
    # AI2 门控三件（OUFRA/ODC-By + 门控；d3-ledger-memo §3 T3 清单——
    # wildguardmix/wildjailbreak 已落地 2026-09-26，WildTeaming deferred）
    "wildguardmix": "T3", "wildjailbreak": "T3",
    # ref-only：不入权重的参照物（父会话裁决）
    "tc260": "ref-only",
}
TIER_DESC = {
    "T1": "可直接发布（署名/NOTICE 义务即可）",
    "T2": "需剥离重训（NC / all-rights-reserved / 未授权——开放权重前删除重训）",
    "T3": "需法务确认（copyleft / ShareAlike / 未公示——学界惯例可训，开放权重有争议）",
    "ref-only": "不入训练的参照物（仅评估/分类参照，永不入权重）",
    "unclassified": "未分级（TIER_MAP 未覆盖——评审补录）",
}
TIER_ORDER = ["T2", "T3", "ref-only", "T1", "unclassified"]  # 风险在前

# ------------------------------------------------- SFT 谱系与评估口径 --
# manifest 只覆盖预训练语料；SFT 产物（data/lf/sft_*.jsonl）不入 manifest，
# 故在生成器内静态登记（可复现；对应 m25-backfill-plan §10 与
# docs/research/probe-contamination-audit.md「下一次再生加注」的结论）。
SFT_LINEAGE = [
    {
        "name": "sec_sft_m25",
        "file": "data/lf/sft_m25.jsonl",
        "rows": 137670,
        "zh": "44.0%（内容级；上限 45%）",
        "lineage": "base → c1-full → m16-32k → m15 → m25-full",
        "note": "M2.5 回填终混（17,210 步 ≈ 10.3h，configs/m25-full.yaml）；"
                "464 行公共文本双侧复用裁定命中"
                "（reports/m25-staging-check.json adjudicated_count）",
    },
]

EVAL_CAVEATS = [
    "**探针 PPL 绝对幅度受污染影响，只做相对比较**：v0.3 的 privacy 探针取自 "
    "GDPR 序言，与 c0_gdpr 训练语料 64.9% 篇级重叠；general_en 探针与 enwiki "
    "训练采样存在 ~26% 篇级重叠——跨模型绝对读数不可直接比较，同模型前后"
    "（base → c1-full → m15/m16 → SFT/DPO 各检查点）相对变化有效；"
    "ais / content / general_zh / malware 四域完全干净，sec 与 aisafety 有"
    "少量（7 + 1 单元）已裁定的公共公告/arXiv 双侧复用残留——对**所有**阶段"
    "等权，横向比较仍有效、绝对幅度只作附注。",
    "**探针 v0.4 已落地（2026-09-30）**：privacy 换源到英国 ICO 指导页"
    "（非 GDPR 原文）、general_en 改用 C1 同池哈希**补集**（26% 未训标题）重建；"
    "两域成品 vs sft_m25 全量 137,670 行、vs sec_c1_full 抽样 60,000 行均 **0 命中**；"
    "其余六域字节复制以保纵向可比（证据链 data/probes/v0.4/README.md、"
    "reports/probes-v04-build.json、reports/probes-v04-vs-sft.json）。"
    "**门禁仍用 v0.3 口径**（与 base/c1-full/m15/m2* 历史读数连续），v0.4 只提供"
    "去污染后的**绝对幅度**附注——两域 v0.3↔v0.4 数值不可直接比较。"
    "VERDICT 词表 retrieved / not-in-doc 扩项属评分器级改动，顺延到 M2.5 读数之后。",
    "**m25 训练行的公共条文复用**：sec_sft_m25 含 464 行 GDPR 条文/序言、"
    "CISA KEV 公开描述文本（与 privacy / sec 探针语料双侧复用，已由 "
    "scripts/check_m25_staging.py 的 ADJUDICATED 表裁定为良性）——继续推高 "
    "privacy / sec 探针的绝对幅度，故上述「仅相对比较」口径对 m25 及后续"
    "检查点同样成立。",
    "详见 docs/research/probe-contamination-audit.md 与 "
    "docs/research/m25-backfill-plan.md §10。",
]

# --------------------------------------------------------- 许可家族分类 --
def lic_family(license: str) -> str:
    """license 字段 → 家族标签（汇总表用，宽松匹配）。"""
    s = license.lower()
    if "未公示" in s:
        return "未公示"
    if "cc0" in s:
        return "CC0 1.0"
    if "public domain" in s or "17 u.s.c" in s:
        return "Public domain（美国政府作品）"
    if "cc by-sa" in s or "cc-by-sa" in s or "attribution-sharealike" in s:
        return "CC BY-SA（ShareAlike）"
    if "cc by-nc" in s or "cc-by-nc" in s or "noncommercial" in s \
            or "non-commercial" in s:
        return "CC BY-NC（非商用）"
    if "cc-by-4.0" in s or "cc by 4.0" in s or "cc-by 4.0" in s:
        return "CC-BY-4.0（署名）"
    if "cc by" in s or "cc-by" in s:
        return "CC-BY（署名）"
    if "gpl-3" in s or "gpl 3" in s:
        return "GPL-3.0（copyleft）"
    if "gpl-2" in s or "gpl 2" in s or "mit-expat" in s:
        return "MIT / GPL-2+ 双许可"
    if "apache-2" in s or "apache 2" in s:
        return "Apache-2.0"
    if "mit" == s.strip()[:3].lower() or "mit " in s[:12] or s.startswith("mit ("):
        return "MIT"
    if "all rights" in s:
        return "All rights reserved"
    if "未公示" in s:
        return "未公示"
    if "arxiv" in s:
        return "arXiv（CC0 元数据/ToU）"
    if "mitre terms" in s:
        return "MITRE 条款（署名）"
    if "cve" in s:
        return "CVE Program（公开条款）"
    if "官方" in s or "statutory" in s or "eur-lex" in s or "法律" in s:
        return "法定文本（无版权/官方公开）"
    return "其他（详见逐源行）"


def md_escape(s: str) -> str:
    """markdown 表格单元格安全化（管道符转义，其余原样保留逐字性）。"""
    return s.replace("|", "\\|").replace("\n", " ")


# ------------------------------------------------------------- 生成器 --
def gen_card(rows: list[dict], manifest_sha: str, gen_time: str) -> str:
    """manifest 行 → MODEL_DATA_CARD markdown（纯函数）。"""
    total_tok = sum(r.get("est_tokens") or 0 for r in rows)
    total_docs = sum(r.get("docs") or 0 for r in rows)
    tiers = {r["id"]: TIER_MAP.get(r["id"], "unclassified") for r in rows}

    # 分级分布 / 许可家族分布
    by_tier: dict[str, int] = {}
    by_family: dict[str, int] = {}
    for r in rows:
        t = tiers[r["id"]]
        by_tier[t] = by_tier.get(t, 0) + (r.get("est_tokens") or 0)
        fam = lic_family(r.get("license", "?"))
        by_family[fam] = by_family.get(fam, 0) + (r.get("est_tokens") or 0)

    L: list[str] = []
    L.append("# Model Data Card（模型训练数据总账）\n")
    L.append("> **语料态绑定**：本卡由 `manifest.jsonl` 机器生成（"
             "`scripts/gen_datacard.py`）——manifest 变更后本卡即过期，须重跑再生。"
             "结构对齐 docs/research/cc-by-sa-precedent.md §3 先例实践"
             "（RedPajama 式逐子集许可指针 + 逐字许可引用）。\n")
    L.append(f"- 生成时间：{gen_time}")
    L.append(f"- manifest 快照 sha256（前 16 位）：`{manifest_sha}`")
    L.append(f"- 源数：{len(rows)} · 总 docs：{total_docs:,} · "
             f"总 tokens：{total_tok:,}\n")
    L.append("## 下游用户提示（Dolma 式源级许可传递）\n")
    L.append("使用本模型时，您同时受训练数据原始来源的许可条款约束"
             "（各源逐字许可见下表）。本卡按 CC 官方 AI 训练指南的署名"
             "建议（attribution = 数据集链接式指引）逐源披露。\n")

    # 汇总表
    L.append("## 汇总\n")
    L.append("### 按 D3 分级（docs/research/d3-ledger-memo.md §3）\n")
    L.append("| 分级 | tokens | 占比 | 含义 |")
    L.append("|---|---:|---:|---|")
    for t in TIER_ORDER:
        if t in by_tier and by_tier[t] > 0:
            share = f"{by_tier[t] / total_tok * 100:.1f}%" if total_tok else "—"
            L.append(f"| {t} | {by_tier[t]:,} | {share} | {TIER_DESC[t]} |")
    L.append("")
    L.append("### 按许可家族\n")
    L.append("| 许可家族 | tokens | 占比 |")
    L.append("|---|---:|---:|")
    for fam, tok in sorted(by_family.items(), key=lambda x: -x[1]):
        share = f"{tok / total_tok * 100:.1f}%" if total_tok else "—"
        L.append(f"| {fam} | {tok:,} | {share} |")
    L.append("")

    # 逐源清单（按 tier 分组，组内 tokens 降序）
    L.append("## 逐源清单\n")
    for t in TIER_ORDER:
        group = [r for r in rows if tiers[r["id"]] == t]
        if not group:
            continue
        group.sort(key=lambda r: -(r.get("est_tokens") or 0))
        L.append(f"### {t} — {TIER_DESC[t]}（{len(group)} 源）\n")
        L.append("| 源 | URL | 许可（逐字） | docs | tokens | 占比 |")
        L.append("|---|---|---|---:|---:|---:|")
        for r in group:
            tok = r.get("est_tokens") or 0
            share = f"{tok / total_tok * 100:.2f}%" if total_tok else "—"
            L.append(
                f"| {md_escape(r.get('id', '?'))} | "
                f"{md_escape(r.get('url', '')[:120])} | "
                f"{md_escape(r.get('license', '?'))} | "
                f"{r.get('docs', 0):,} | {tok:,} | {share} |")
        L.append("")

    # SFT 谱系与评估注意事项（manifest 之外的静态登记，见 SFT_LINEAGE 注释）
    L.append("## SFT 谱系与已注册数据集\n")
    L.append("| 数据集 | 文件 | 行数 | 内容级 zh | 谱系 | 备注 |")
    L.append("|---|---|---:|---:|---|---|")
    for e in SFT_LINEAGE:
        L.append(f"| {md_escape(e['name'])} | {md_escape(e['file'])} | "
                 f"{e['rows']:,} | {md_escape(e['zh'])} | "
                 f"{md_escape(e['lineage'])} | {md_escape(e['note'])} |")
    L.append("")
    L.append("## 评估注意事项\n")
    for c in EVAL_CAVEATS:
        L.append(f"- {c}")
    L.append("")

    L.append("---\n")
    L.append("*本卡为工程侧披露文件，不构成法律意见；D3 分级的法律问题"
             "（权重演绎性/训练复制许可）待法务确认——见 "
             "docs/research/d3-ledger-memo.md §4 前置动作清单。*\n")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="manifest → MODEL_DATA_CARD.md")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    raw = MANIFEST.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()[:16]
    rows = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]

    unclassified = [r["id"] for r in rows
                    if r["id"] not in TIER_MAP and (r.get("est_tokens") or 0) > 0]
    if unclassified:
        print(f"[WARN] 未分级源（d3-ledger-memo §3 未覆盖，评审补录）："
              f"{unclassified}", flush=True)

    card = gen_card(rows, sha, time.strftime("%Y-%m-%d %H:%M"))
    out = Path(args.out)
    out.write_text(card, encoding="utf-8", newline="\n")
    total = sum(r.get("est_tokens") or 0 for r in rows)
    print(f"数据卡 → {out}（{len(rows)} 源 / {total:,} tokens / "
          f"manifest@{sha}）", flush=True)


if __name__ == "__main__":
    main()
