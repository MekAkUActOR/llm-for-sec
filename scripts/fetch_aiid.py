"""C2 AI-safety 知识层：AIID（AI Incident Database）→ 训练语料。

数据通路（2026-09-26 破局记录）：api.incidentdatabase.ai 连接被断
（本日网络），但主站 Gatsby 静态层全通 → 从 research 页 HTML 挖出
**Cloudflare R2 周导出桶**（pub-72b2b2fc36ec423189843747af98f80e.r2.dev）
的全库 Excel 导出（无需 API/MongoDB）——excel-export-pipeline README
记载该导出即"whole database as a single offline spreadsheet"。

内容：AIID 全库 **1,689 起已策展 AI 事件**（编辑撰写 title/description，
MIT 风险分类 89% 填充）。红线分类：**事件报告 = OK**（父代理分类）。

范围决策：
- Incidents 表（编辑策展内容）→ 逐事件一 doc；
- **Reports 表（7,791 条外部新闻片段）排除**——第三方版权内容混入
  （新闻原文摘录），许可不可传递，知识密度也低于策展描述（记档）；
- Entities 表（7,341 实体名）为辅助维表，随事件字段内嵌，不单独立 doc。

许可记录（如实）：**数据许可未公示**——terms-of-use 页无数据许可条款、
站点 footer 无标注、工作簿内无许可注记；父代理口径 CC-BY-4.0 **未能
在线核实**；仓库代码 LICENSE.txt = Apache-2.0（Responsible AI
Collaborative）。D3 评审项：事件描述为事实性报道+编辑表述，权属 AIID/
RAIC，开放权重前需重估（同 gtfobins/lolbas 行）。

输入：raw/aiid/AIID_Excel_Export-20260921.xlsx（2.5MB，下载已记档）
输出：c2_aisafety_aiid.jsonl（1,689 docs）
用法：python scripts/fetch_aiid.py [--count]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW_XLSX = ROOT / "data" / "corpora" / "raw" / "aiid" / \
    "AIID_Excel_Export-20260921.xlsx"
OUT = ROOT / "data" / "corpora" / "clean" / "c2_aisafety_aiid.jsonl"
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"

_WS = re.compile(r"\s+")
_BRACKET = re.compile(r'^\[.*\]$')

# 字段 → 文中标签（填充率 ≥0.1 才收；见 fetch 期列分析）
MIT_FIELDS = [           # 89% 填充：MIT 风险分类骨干
    ("Risk Domain", "Risk domain"),
    ("Risk Subdomain", "Risk subdomain"),
    ("Intent", "Intent"),
]
CSET_FIELDS = [          # 12% 填充：CSET 政策分析层，有值即带
    ("Harm Domain", "Harm domain"),
    ("AI Harm Level", "AI harm level"),
    ("Sector of Deployment", "Sector of deployment"),
    ("AI Task", "AI task"),
    ("Autonomy Level", "Autonomy level"),
    ("Tangible Harm", "Tangible harm"),
]


def _clean(v) -> str | None:
    """单元格 → 干净字符串；空/NaN/纯占位 → None。"""
    if v is None:
        return None
    if isinstance(v, float) and v != v:          # NaN
        return None
    s = _WS.sub(" ", str(v)).strip()
    if not s or s in ("-", "nan", "None"):
        return None
    if _BRACKET.match(s):                        # '["a", "b"]' → 'a, b'
        inner = s[1:-1].strip()
        parts = [p.strip().strip('"').strip("'")
                 for p in inner.split(",") if p.strip().strip('"').strip("'")]
        s = ", ".join(parts) if parts else None
    return s


def convert_incident(row: dict) -> str:
    """一行事件（列名→值 dict）→ 一 doc 文本。纯函数。"""
    aid = _clean(row.get("Incident ID")) or "?"
    date = _clean(row.get("date")) or "unknown date"
    title = _clean(row.get("title")) or "Untitled incident"
    desc = _clean(row.get("description")) or ""
    head = (f"AI Incident Database (AIID) incident {aid}, date {date}: "
            f"{title}.")
    parts = [head]
    if desc:
        parts.append(desc)
    actor_bits = []
    for col, label in (("deployer", "Deployer"), ("developer", "Developer"),
                       ("harmed", "Harmed parties")):
        v = _clean(row.get(col))
        if v:
            actor_bits.append(f"{label}: {v}")
    if actor_bits:
        parts.append("; ".join(actor_bits) + ".")
    sysv = _clean(row.get("Implicated Systems"))
    if sysv:
        parts.append(f"Implicated systems: {sysv}.")
    cls_bits = []
    for col, label in MIT_FIELDS + CSET_FIELDS:
        v = _clean(row.get(col))
        if v:
            cls_bits.append(f"{label}: {v}")
    if cls_bits:
        parts.append("; ".join(cls_bits) + ".")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description="AIID xlsx → C2 知识层")
    ap.add_argument("--count", action="store_true")
    args = ap.parse_args()

    import pandas as pd
    xl = pd.ExcelFile(RAW_XLSX)
    df = xl.parse("Incidents", skiprows=1, header=1)
    docs = [convert_incident(r) for r in df.to_dict("records")]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")

    tokens = 0
    if args.count:
        sys.path.insert(0, str(ROOT / "scripts"))
        from fetch_zhwiki import count_tokens
        tokens = count_tokens(OUT)
    print(f"[aiid] {len(docs)} docs, {tokens:,} tokens -> {OUT.name}",
          flush=True)

    # manifest 登记（id=aiid；数据许可如实记录 + D3）
    rows = []
    if MANIFEST.exists():
        rows = [json.loads(l) for l in
                MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("id") != "aiid"]
    rows.append({
        "id": "aiid", "name": "aiid",
        "url": "https://incidentdatabase.ai/ (R2 export "
               "pub-72b2b2fc36ec423189843747af98f80e.r2.dev/"
               "AIID_Excel_Export-20260921.xlsx)",
        "license": "未公示（数据）; Apache-2.0 (repo code)",
        "tier": "public", "domain": "ai_safety", "lang": "en",
        "est_tokens": tokens, "docs": len(docs), "status": "ingested",
        "ingested_at": time.strftime("%Y-%m-%d"),
        "files": [str(OUT.relative_to(ROOT))],
        "notes": "AI Incident Database 全库 1,689 起策展 AI 事件（编辑撰写"
                 "标题/描述 + MIT 风险分类 89% 填充 + CSET 政策层有值即带）。"
                 "数据许可：站点 terms-of-use 无数据许可条款、footer 与工作簿"
                 "均无标注——父代理口径 CC-BY-4.0 未能在线核实，如实记录"
                 "（代码仓库 LICENSE.txt = Apache-2.0, Responsible AI "
                 "Collaborative）。D3 评审项：事件描述=事实报道+编辑表述，"
                 "开放权重前需重估（同 gtfobins/lolbas 行）。Reports 表"
                 "（7,791 条外部新闻片段）按版权红线排除——第三方新闻原文"
                 "摘录，许可不可传递。通路：api 被断 → Gatsby 静态层挖出 R2 "
                 "周导出桶（excel-export-pipeline README 记载该导出=全库"
                 "单文件）。事件报告=OK（父代理红线分类）",
    })
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")
    print("manifest updated", flush=True)


if __name__ == "__main__":
    main()
