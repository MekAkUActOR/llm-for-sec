"""C2 AI-safety 知识库层：NIST / OWASP / MITRE ATLAS → 训练语料。

四个描述级知识源（红线分类：政策/框架/技术参考的描述=OK）：

1. **NIST**（美国政府作品，17 U.S.C. §105 → 公有领域）：
   - AI 600-1（Generative AI Profile，2023-07）
   - AI RMF 1.0（NIST.AI.100-1，2023-01）
   - SP 800-226（AI 系统风险管控，2025-04 初版）
   PDF → pypdf 提取，一文一 doc。
2. **OWASP GenAI Red Teaming Guide** v1.0（2025-01-23，77 页）：
   许可 CC BY-SA 4.0（OWASP GenAI Security Project 口径——项目与 Top 10
   同源同许可；PDF 内无逐字许可页，如实记录。D3 评审项：SA=ShareAlike）。
3. **OWASP Top 10 for LLM Applications 2026**（2026-08-04 发布）：
   仓库 GenAI-Security-Project/GenAI-LLM-Top10 的 2026/final/ 13 个
   markdown（Appendix B 为纯图占位，跳过 → 12 docs）。许可逐字：
   仓库徽标 "License: CC BY-SA 4.0"（creativecommons.org/licenses/by-sa/4.0）。
4. **MITRE ATLAS**（dist/ATLAS.yaml 2026.09 版）：
   16 tactics + 170 techniques + 35 mitigations + 57 case studies
   → 每条目一 doc。许可：仓库 LICENSE = Apache-2.0（MITRE,
   Copyright 2021-2026）。

本地依赖：raw/nist/*.pdf、raw/nist/owasp-genai-red-teaming-guide.pdf、
raw/owasp-llm-top10-2026/*.md、raw/atlas/dist/ATLAS.yaml
（下载由 README/报告记录，本脚本只做转换，幂等）。

输出：c2_aisafety_{nist,owasp_rtg,owasp_top10,atlas}.jsonl
用法：python scripts/fetch_aisafety_knowledge.py [--count]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import warnings
from pathlib import Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "corpora" / "raw"
CLEAN = ROOT / "data" / "corpora" / "clean"
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"

_WS = re.compile(r"[ \t]+")
_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTMLIMG = re.compile(r"<img[^>]*/?>")


def pdf_to_text(path: Path) -> str:
    """PDF → 文本（pypdf；逐页提取，页间双换行，行内空白规范化）。"""
    from pypdf import PdfReader
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = PdfReader(str(path))
        pages = [p.extract_text() or "" for p in r.pages]
    out = []
    for t in pages:
        lines = [_WS.sub(" ", ln).strip() for ln in t.splitlines()]
        out.append("\n".join(ln for ln in lines if ln))
    return "\n\n".join(out).strip()


def md_to_text(text: str) -> str:
    """Markdown → 文本（去图/链接保文字，行内空白规范化，保段落空行）。"""
    t = _HTMLIMG.sub("", text)
    t = _IMG.sub("", t)
    t = _LINK.sub(r"\1", t)
    lines = [_WS.sub(" ", ln).strip() for ln in t.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)   # 3+ 连续空行折叠
    return out.strip()


# ---- NIST ----
NIST_DOCS = [
    ("NIST.AI.600-1.pdf",
     "NIST AI 600-1: Generative AI Profile (NIST AI Risk Management "
     "Framework, July 2023)"),
    ("NIST.AI.100-1.pdf",
     "NIST AI Risk Management Framework (AI RMF 1.0), January 2023"),
    ("NIST.SP.800-226.pdf",
     "NIST Special Publication 800-226: Artificial Intelligence Risk "
     "Management Framework: Generative AI Profile"),
]


def convert_nist() -> list[str]:
    docs = []
    for fname, title in NIST_DOCS:
        p = RAW / "nist" / fname
        if not p.exists():
            print(f"    [warn] 缺 {fname}，跳过", flush=True)
            continue
        body = pdf_to_text(p)
        docs.append(f"{title}.\n\n{body}")
    return docs


# ---- OWASP RTG ----
def convert_rtg() -> list[str]:
    p = RAW / "nist" / "owasp-genai-red-teaming-guide.pdf"
    if not p.exists():
        return []
    body = pdf_to_text(p)
    return ["OWASP GenAI Red Teaming Guide, Version 1.0 (January 23, 2025): "
            "A Practical Approach to Evaluating AI Vulnerabilities.\n\n"
            + body]


# ---- OWASP Top 10 2026 ----
def convert_top10() -> list[str]:
    base = RAW / "owasp-llm-top10-2026"
    docs = []
    for p in sorted(base.glob("*.md")):
        if p.name.startswith("Appendix_B"):
            continue        # 纯图占位（424B），无文本
        body = md_to_text(p.read_text(encoding="utf-8"))
        if body:
            docs.append(f"OWASP Top 10 for LLM Applications 2026 — "
                        f"{p.stem.replace('_', ' ')}.\n\n{body}")
    return docs


# ---- MITRE ATLAS ----
def convert_atlas() -> list[str]:
    p = RAW / "atlas" / "dist" / "ATLAS.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    m = d["matrices"][0]
    tactic_names = {t["id"]: t["name"] for t in m["tactics"]}
    tech_names = {t["id"]: t["name"] for t in m["techniques"]}
    docs = []

    for t in m["tactics"]:
        docs.append(f"MITRE ATLAS tactic {t['id']} ({t['name']}). "
                    f"{_WS.sub(' ', t.get('description', '')).strip()}")
    for t in m["techniques"]:
        tacs = ", ".join(
            f"{tactic_names.get(tid, tid)} ({tid})"
            for tid in (t.get("tactics") or []))
        head = f"MITRE ATLAS technique {t['id']} ({t['name']})"
        if tacs:
            head += f", tactics: {tacs}"
        desc = _WS.sub(" ", t.get("description", "")).strip()
        docs.append(f"{head}. {desc}")
    for mit in m["mitigations"]:
        techs = ", ".join(x["id"] for x in (mit.get("techniques") or []))
        head = f"MITRE ATLAS mitigation {mit['id']} ({mit['name']})"
        if techs:
            head += f" (mitigates {techs})"
        desc = _WS.sub(" ", mit.get("description", "")).strip()
        docs.append(f"{head}. {desc}")
    for cs in d["case-studies"]:
        head = (f"MITRE ATLAS case study {cs['id']} ({cs['name']}), "
                f"incident date {cs.get('incident-date', 'unknown')}.")
        parts = [head]
        summ = _WS.sub(" ", cs.get("summary", "")).strip()
        if summ:
            parts.append(f"Summary: {summ}")
        for proc in cs.get("procedure") or []:
            tid = proc.get("technique", "")
            tname = tech_names.get(tid, "")
            pd_ = _WS.sub(" ", proc.get("description", "")).strip()
            parts.append(f"Procedure (technique {tid}"
                         f"{' ' + tname if tname else ''}): {pd_}")
        if cs.get("target"):
            parts.append(f"Target: {_WS.sub(' ', str(cs['target'])).strip()}")
        if cs.get("actor"):
            parts.append(f"Actor: {_WS.sub(' ', str(cs['actor'])).strip()}")
        docs.append("\n".join(parts))
    return docs


def write_jsonl(path: Path, docs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")


def upsert_manifest(sid: str, url: str, files: list[str], docs: int,
                    tokens: int, license_: str, domain: str, lang: str,
                    note: str) -> None:
    rows = []
    if MANIFEST.exists():
        rows = [json.loads(l) for l in
                MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("id") != sid]
    rows.append({
        "id": sid, "name": sid, "url": url, "license": license_,
        "tier": "public", "domain": domain, "lang": lang,
        "est_tokens": tokens, "docs": docs, "status": "ingested",
        "ingested_at": time.strftime("%Y-%m-%d"), "files": files,
        "notes": note,
    })
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")


def main():
    ap = argparse.ArgumentParser(description="NIST/OWASP/ATLAS → C2 知识层")
    ap.add_argument("--count", action="store_true")
    args = ap.parse_args()

    sources = [
        ("nist", "c2_aisafety_nist.jsonl", convert_nist,
         "https://nvlpubs.nist.gov/nistpubs/ (AI 600-1 / AI RMF 100-1 / "
         "SP 800-226)",
         "Public domain (US government work, 17 U.S.C. §105)",
         "NIST AI 风险治理三文档（GenAI Profile / AI RMF 1.0 / SP 800-226）。"
         "许可：美国政府作品=公有领域（17 U.S.C. §105，无版权）。"
         "PDF→pypdf 提取，一文一 doc"),
        ("owasp-rtg", "c2_aisafety_owasp_rtg.jsonl", convert_rtg,
         "https://genai.owasp.org/ (GenAI Red Teaming Guide v1.0)",
         "CC BY-SA 4.0 (OWASP GenAI Security Project)",
         "OWASP GenAI Red Teaming Guide v1.0（2025-01-23，77 页）。许可："
         "CC BY-SA 4.0（项目口径，与 Top 10 同项目；PDF 内无逐字许可页，"
         "如实记录；SA=ShareAlike → D3 评审项：模型发布时需署名+相同方式"
         "共享评估）。红队方法论=描述级知识，非攻击载荷"),
        ("owasp-top10", "c2_aisafety_owasp_top10.jsonl", convert_top10,
         "https://github.com/GenAI-Security-Project/GenAI-LLM-Top10 "
         "(2026/final)",
         "CC BY-SA 4.0",
         "OWASP Top 10 for LLM Applications 2026（2026-08-04 发布）。许可"
         "逐字：仓库徽标 \"License: CC BY-SA 4.0\""
         "(creativecommons.org/licenses/by-sa/4.0)；D3 评审项同 rtg 行。"
         "12 docs（LLM01-10 + 附录 A + references；附录 B 纯图跳过）。"
         "风险类别描述/缓解建议=描述级知识"),
        ("atlas", "c2_aisafety_atlas.jsonl", convert_atlas,
         "https://github.com/mitre-atlas/atlas-data (dist/ATLAS.yaml, "
         "release 2026.09)",
         "Apache-2.0",
         "MITRE ATLAS（Adversarial Threat Landscape for AI Systems）"
         "2026.09 版：16 tactics / 170 techniques / 35 mitigations / "
         "57 case studies。许可：仓库 LICENSE = Apache-2.0（MITRE，"
         "Copyright 2021-2026；与父代理原口径 CC-BY-4.0 不符，已上报）。"
         "攻击技术分类与案例研究=描述级知识"),
    ]
    for sid, out_name, fn, url, license_, note in sources:
        docs = fn()
        out = CLEAN / out_name
        write_jsonl(out, docs)
        tokens = 0
        if args.count:
            sys.path.insert(0, str(ROOT / "scripts"))
            from fetch_zhwiki import count_tokens
            tokens = count_tokens(out)
        print(f"[{sid}] {len(docs)} docs, {tokens:,} tokens -> {out.name}",
              flush=True)
        upsert_manifest(sid, url, [str(out.relative_to(ROOT))],
                        len(docs), tokens, license_,
                        "ai_safety", "en", note)
    print("manifest updated", flush=True)


if __name__ == "__main__":
    main()
