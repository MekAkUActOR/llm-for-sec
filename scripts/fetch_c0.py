"""C0 冒烟雾料管线：P0 清洁来源 -> 清洗文本 JSONL + manifest 登记（docs/04 §3）。

来源与许可（docs/04 §1 P0 表）：
  mitre-attack  ATT&CK enterprise STIX          raw.githubusercontent.com
  cwe           CWE 字典 XML                    cwe.mitre.org
  capec         CAPEC 攻击模式 XML              capec.mitre.org
  kev           CISA KEV JSON                   cisa.gov
  cve           CVEProject/cvelistV5 (zip 流式) github codeload
  owasp-cs      OWASP CheatSheetSeries (zip)    github codeload
  gdpr          GDPR 英文全文（EUR-Lex）
  cn-laws       PIPL/网络安全法/数据安全法 中文全文（gov.cn）
  arxiv-cscr    arXiv cs.CR 近期摘要（API 分页）

产物：
  data/corpora/raw/<id>/...                原始文件
  data/corpora/clean/c0_<id>.jsonl         清洗后 {"text": ...} 每行一篇
  data/corpora/clean/c0_all.jsonl          合并（LLaMA-Factory 输入）
  data/corpora/manifest.jsonl              upsert 入库登记
用法：
  python scripts/fetch_c0.py [--sources all|a,b,...] [--skip-fetch] [--no-tokens]
"""

from __future__ import annotations

import argparse
import hashlib
import html as _html
import json
import re
import ssl
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw"
CLEAN = ROOT / "data" / "corpora" / "clean"
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"
SNAPSHOT = (ROOT / ".cache" / "huggingface" / "hub" /
            "models--Qwen--Qwen3-0.6B-Base" / "snapshots" /
            "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")

UA = "llm-for-sec-c0/0.1 (security corpus research pipeline)"


def _norm(s):
    return " ".join(str(s or "").split())


# ---------------------------------------------------------------- 下载工具 --
def http_get(url, dest: Path, timeout=90):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            if total % (100 << 20) < (1 << 20):
                print(f"    ... {total >> 20} MB", flush=True)
    print(f"  downloaded {dest.name} ({total >> 20} MB)", flush=True)
    return dest


def http_text(url, timeout=60, insecure=False):
    """insecure=True 仅用于已知被本地网络 TLS 拦截的官方法律文本抓取，
    且调用方必须做关键词完整性校验（见 s_cn_laws）。"""
    ctx = ssl._create_unverified_context() if insecure else None
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- 转换器 --
def convert_cve_item(d):
    """cvelistV5 单条 CVE JSON -> 文本（REJECTED/无英文描述跳过）。"""
    meta = d.get("cveMetadata") or {}
    cve_id = meta.get("cveId", "")
    if not cve_id or meta.get("state") == "REJECTED":
        return None
    cna = (d.get("containers") or {}).get("cna") or {}
    descs = cna.get("descriptions") or []
    desc = next((x.get("value") for x in descs if x.get("lang") == "en"), None)
    if not desc:
        return None
    title = cna.get("title") or ""
    parts = [f"{cve_id}: {title}. {_norm(desc)}" if title else f"{cve_id}: {_norm(desc)}"]
    affected = []
    for a in (cna.get("affected") or [])[:8]:
        v, p = a.get("vendor") or "", a.get("product") or ""
        if v or p:
            affected.append(f"{v}/{p}".strip("/"))
    if affected:
        parts.append("Affected products: " + ", ".join(dict.fromkeys(affected)))
    refs = [r.get("url") for r in (cna.get("references") or [])[:5] if r.get("url")]
    if refs:
        parts.append("References: " + ", ".join(refs))
    return " ".join(parts)


def convert_kev(doc):
    out = []
    for v in doc.get("vulnerabilities", []):
        cid = v.get("cveID", "")
        if not cid:
            continue
        name = v.get("vulnerabilityName", "")
        prod = f"{v.get('vendorProject', '')} {v.get('product', '')}".strip()
        added = v.get("dateAdded", "")
        ransom = v.get("knownRansomwareCampaignUse", "")
        sdesc = v.get("shortDescription", "")
        line = (f"{cid} (CISA KEV, known exploited, added {added}): "
                f"{name}. Product: {prod}. {_norm(sdesc)}")
        if ransom and ransom.lower() not in ("unknown", "nan"):
            line += f" Known ransomware campaign use: {ransom}."
        out.append(line)
    return out


def convert_attack(doc):
    out = []
    for obj in doc.get("objects", []):
        t = obj.get("type")
        refs = obj.get("external_references") or []
        ext_id = next((r.get("external_id", "") for r in refs
                       if r.get("source_name") == "mitre-attack"), "")
        desc = obj.get("description") or ""
        if not desc:
            continue
        if t == "attack-pattern":
            phases = ", ".join(p.get("phase_name", "") for p in
                               obj.get("kill_chain_phases", [])
                               if p.get("phase_name"))
            head = f"ATT&CK technique {ext_id} ({obj.get('name', '')})"
            if phases:
                head += f", kill chain phase: {phases}"
            out.append(f"{head}: {_norm(desc)}")
        elif t == "course-of-action":
            out.append(f"ATT&CK mitigation {ext_id} ({obj.get('name', '')}): "
                       f"{_norm(desc)}")
    return out


def _local(root):
    return root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""


def convert_cwe(xml_text):
    root = ET.fromstring(xml_text)
    ns = _local(root)
    out = []
    for w in root.iter(ns + "Weakness"):
        wid, name, status = w.get("ID", ""), w.get("Name", ""), w.get("Status", "")
        d = w.find(ns + "Description")
        desc = _norm("".join(d.itertext())) if d is not None else ""
        if not desc:
            continue
        ext = w.find(ns + "Extended_Description")
        parts = [f"CWE-{wid} {name} ({status}): {desc}"]
        if ext is not None and _norm("".join(ext.itertext())):
            parts.append(_norm("".join(ext.itertext())))
        cons = []
        for c in w.iter(ns + "Consequence"):
            scopes = [s.text for s in c.iter(ns + "Scope") if s.text]
            if scopes:
                cons.append("/".join(scopes))
        if cons:
            parts.append("Common consequences: " + ", ".join(cons[:5]))
        mits = []
        for m in w.iter(ns + "Mitigation"):
            dm = m.find(ns + "Description")
            if dm is not None:
                ph = m.find(ns + "Phase")
                mits.append((f"{ph.text}: " if ph is not None and ph.text else "")
                            + _norm("".join(dm.itertext())))
        if mits:
            parts.append("Mitigations: " + "; ".join(mits[:4]))
        out.append(" ".join(parts))
    return out


def convert_capec(xml_text):
    root = ET.fromstring(xml_text)
    ns = _local(root)
    out = []
    for p in root.iter():
        if not p.tag.endswith("Attack_Pattern"):
            continue
        pid, name = p.get("ID", ""), p.get("Name", "")
        d = None
        for child in p:
            if child.tag.endswith("Description"):
                d = child
                break
        desc = _norm("".join(d.itertext())) if d is not None else ""
        if not desc:
            continue
        parts = [f"CAPEC-{pid} {name}: {desc}"]
        sols = [_norm("".join(s.itertext())) for s in p.iter() if s.tag.endswith("Solution")]
        sols = [s for s in sols if s]
        if sols:
            parts.append("Solutions: " + "; ".join(sols[:3]))
        out.append(" ".join(parts))
    return out


def convert_arxiv(atom_text):
    ns = "{http://www.w3.org/2005/Atom}"
    root = ET.fromstring(atom_text)
    out = []
    for e in root.iter(ns + "entry"):
        t = e.find(ns + "title")
        s = e.find(ns + "summary")
        if t is None or s is None:
            continue
        title, summ = _norm(t.text), _norm(s.text)
        if title and summ:
            out.append(f"arXiv security research paper: {title}. {summ}")
    return out


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def html_to_text(html_text):
    html_text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
    html_text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", html_text)
    text = _html.unescape(_TAG_RE.sub(" ", html_text))
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


# ---------------------------------------------------------------- 各源定义 --
SOURCES = {}


def source(sid, url=None, license="", domain="security", lang="en", note=""):
    def deco(fn):
        SOURCES[sid] = {"fn": fn, "url": url, "license": license,
                        "domain": domain, "lang": lang, "note": note}
        return fn
    return deco


@source("mitre-attack",
        url="https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json",
        license="MITRE terms (attribution required)", domain="security")
def s_attack(skip_fetch):
    p = RAW / "mitre-attack" / "enterprise-attack.json"
    if not skip_fetch:
        http_get(SOURCES["mitre-attack"]["url"], p)
    return convert_attack(json.loads(p.read_text(encoding="utf-8")))


@source("cwe", url="https://cwe.mitre.org/data/xml/cwec_latest.xml.zip",
        license="MITRE terms (attribution required)", domain="security")
def s_cwe(skip_fetch):
    p = RAW / "cwe" / "cwec_latest.xml.zip"
    if not skip_fetch:
        http_get(SOURCES["cwe"]["url"], p)
    with zipfile.ZipFile(p) as z:
        name = next(n for n in z.namelist() if n.endswith(".xml"))
        return convert_cwe(z.read(name).decode("utf-8", "replace"))


@source("capec", url="https://capec.mitre.org/data/xml/capec_latest.xml",
        license="MITRE terms (attribution required)", domain="security")
def s_capec(skip_fetch):
    p = RAW / "capec" / "capec_latest.xml"
    if not skip_fetch:
        http_get(SOURCES["capec"]["url"], p)
    return convert_capec(p.read_text(encoding="utf-8", errors="replace"))


@source("kev",
        url="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        license="public-domain (US government)", domain="security")
def s_kev(skip_fetch):
    p = RAW / "kev" / "known_exploited_vulnerabilities.json"
    if not skip_fetch:
        http_get(SOURCES["kev"]["url"], p)
    return convert_kev(json.loads(p.read_text(encoding="utf-8")))


@source("cve", url="https://github.com/CVEProject/cvelistV5/archive/refs/heads/main.zip",
        license="CVE Program terms (public)", domain="security")
def s_cve(skip_fetch):
    p = RAW / "cve" / "cvelistV5-main.zip"
    if not skip_fetch:
        http_get(SOURCES["cve"]["url"], p)
    out = []
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist()
                 if n.startswith("cvelistV5-main/cves/")
                 and n.endswith(".json") and "CVE-" in n]
        print(f"  cve: {len(names)} entries in zip", flush=True)
        for i, n in enumerate(names):
            try:
                t = convert_cve_item(json.loads(z.read(n).decode("utf-8", "replace")))
            except Exception:
                t = None
            if t:
                out.append(t)
            if (i + 1) % 50000 == 0:
                print(f"    ... {i + 1}/{len(names)}", flush=True)
    return out


@source("owasp-cs", url="https://github.com/OWASP/CheatSheetSeries/archive/refs/heads/master.zip",
        license="CC-BY-SA", domain="security")
def s_owasp(skip_fetch):
    p = RAW / "owasp-cs" / "cheatsheets-master.zip"
    if not skip_fetch:
        http_get(SOURCES["owasp-cs"]["url"], p)
    out = []
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            parts = n.split("/")
            # 仓库目录为小写 cheatsheets/（历史版本曾为 CheatSheets/），排除 draft
            if (len(parts) >= 3 and parts[0] == "CheatSheetSeries-master"
                    and parts[1].lower() == "cheatsheets"
                    and not parts[1].endswith("_draft") and n.endswith(".md")):
                out.append(z.read(n).decode("utf-8", "replace"))
    return out


@source("gdpr", url="https://gdpr-info.eu/",
        license="EU 官方法律文本（镜像 gdpr-info.eu 逐条页）",
        domain="privacy", lang="en")
def s_gdpr(skip_fetch):
    d = RAW / "gdpr"
    d.mkdir(parents=True, exist_ok=True)
    if not skip_fetch or not (d / "art-1.html").exists():
        for i in range(1, 100):
            try:
                (d / f"art-{i}.html").write_text(
                    http_text(f"https://gdpr-info.eu/art-{i}-gdpr/"),
                    encoding="utf-8")
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                print(f"  gdpr art-{i} FAILED: {e}", flush=True)
    texts = []
    for i in range(1, 100):
        p = d / f"art-{i}.html"
        if not p.exists():
            continue
        t = html_to_text(p.read_text(encoding="utf-8"))
        end = t.find("Suitable Recitals")
        if end == -1:
            end = t.find("Table of contents")
        if end == -1:
            continue
        # h1 行 "Art. N GDPR <标题>"：取 Suitable Recitals 之前最后一次出现
        start = t[:end].rfind(f"Art. {i} GDPR")
        if start >= 0 and end > start:
            texts.append(t[start:end].strip())
    return ["\n\n".join(texts)] if len(texts) >= 90 else []


_CN_LAWS = {
    "PIPL-个人信息保护法": ("https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm",
                            ["个人信息保护法", "第一条"], 3000),
    "CybersecurityLaw-网络安全法": ("https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm",
                                    ["网络安全法", "第一条"], 3000),
    "DataSecurityLaw-数据安全法": ("http://www.npc.gov.cn/c2/c30834/202106/t20210610_311888.html",
                                  ["数据安全法", "第一条"], 3000),
}

# C1 扩展：法规/规章层（CAC / gov.cn 现行页面，2026-09-24 核验）
_CN_REGS = {
    "CybersecurityReview-网络安全审查办法": (
        "https://www.cac.gov.cn/2022-01/04/c_1642894602182845.htm",
        ["网络安全审查办法", "第一条"], 3000),
    "DataExport-数据出境安全评估办法": (
        "https://www.cac.gov.cn/2022-07/07/c_1658811536396503.htm",
        ["数据出境安全评估办法", "第一条"], 3000),
    "GenAI-生成式人工智能服务管理暂行办法": (
        "https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm",
        ["生成式人工智能", "第一条"], 3000),
    "NetDataReg-网络数据安全管理条例": (
        "https://www.gov.cn/gongbao/2024/issue_11646/202410/content_6980863.html",
        ["网络数据安全管理条例", "第一条"], 3000),
    "CIIReg-关键信息基础设施安全保护条例": (
        "https://www.gov.cn/zhengce/content/2021-08/17/content_5631671.htm",
        ["关键信息基础设施", "第一条"], 3000),
    "PIIExportContract-个人信息出境标准合同办法": (
        "https://www.gov.cn/gongbao/content/2023/content_5752224.htm",
        ["个人信息出境标准合同", "第一条"], 1500),  # 13 条短规章（合同模板附件为 PDF，不在正文页）
    "AutoData-汽车数据安全管理若干规定": (
        "https://www.gov.cn/zhengce/2021-08/20/content_5728943.htm",
        ["汽车数据", "第一条"], 3000),
}


def _fetch_law_pages(entries, raw_subdir, tag, skip_fetch):
    """逐条抓取官方法规页：TLS 拦截降级 + 标题/第一条关键词完整性校验。"""
    out = []
    d = RAW / raw_subdir
    for name, (url, must_have, min_len) in entries.items():
        p = d / f"{name}.txt"
        try:
            if not skip_fetch or not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                try:
                    html_text = http_text(url)
                except urllib.error.URLError as e:
                    if "CERTIFICATE_VERIFY_FAILED" not in str(e):
                        raise
                    print(f"    {name}: 本地网络 TLS 拦截，"
                          f"降级为不校验证书抓取（将做关键词完整性校验）", flush=True)
                    html_text = http_text(url, insecure=True)
                p.write_text(html_text, encoding="utf-8")
            t = html_to_text(p.read_text(encoding="utf-8"))
            # 完整性校验：标题 + 法条结构特征 + 最小长度（防降级通道内容被篡改/截断）
            missing = [k for k in must_have if k not in t]
            if len(t) >= min_len and not missing:
                out.append(t)
                print(f"  {tag} ok: {name} ({len(t)} chars, 完整性校验通过)",
                      flush=True)
            else:
                why = f"关键词缺失 {missing}" if missing else f"长度不足 (len={len(t)} < {min_len})"
                print(f"  {tag} FAILED {name}: 完整性校验未通过 — {why}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  {tag} FAILED {name}: {e}", flush=True)
    return out


@source("cn-laws", license="官方法律文本（公开）", domain="privacy", lang="zh",
        note="gov.cn 经本地网络存在 TLS 拦截：降级抓取后做关键词完整性校验")
def s_cn_laws(skip_fetch):
    return _fetch_law_pages(_CN_LAWS, "cn-laws", "cn-law", skip_fetch)


@source("cn-regs", license="官方法规/规章文本（公开）", domain="privacy", lang="zh",
        note="C1 扩展：CAC/gov.cn 现行页面（2026-09-24 核验），同 cn-laws 抓取校验路径")
def s_cn_regs(skip_fetch):
    return _fetch_law_pages(_CN_REGS, "cn-regs", "cn-reg", skip_fetch)


@source("arxiv-cscr", license="arXiv non-exclusive license",
        domain="security")
def s_arxiv(skip_fetch):
    p = RAW / "arxiv-cscr"
    texts = []
    if not skip_fetch:
        p.mkdir(parents=True, exist_ok=True)
        for page in range(10):
            url = ("http://export.arxiv.org/api/query?search_query=cat:cs.CR"
                   f"&sortBy=submittedDate&sortOrder=descending&start={page * 200}"
                   "&max_results=200")
            try:
                atom = http_text(url)
                (p / f"page{page}.xml").write_text(atom, encoding="utf-8")
                time.sleep(3)
            except Exception as e:
                print(f"  arxiv page {page} FAILED: {e}", flush=True)
                break
    for f in sorted(p.glob("page*.xml")):
        texts.extend(convert_arxiv(f.read_text(encoding="utf-8")))
    return texts


# ---------------------------------------------------------------- 主流程 --
def _clean_filename(sid):
    """c0 系默认 c0_ 前缀；c1_/c2_ 批次名透传（如 c2_privacy_gdpr_full）。"""
    if sid.startswith(("c1_", "c2_")):
        return f"{sid}.jsonl"
    return f"c0_{sid}.jsonl"


def write_clean(sid, texts):
    CLEAN.mkdir(parents=True, exist_ok=True)
    seen, n = set(), 0
    p = CLEAN / _clean_filename(sid)
    # ensure_ascii=True：pyarrow 的 JSON 读取器对字符串内原始多字节 UTF-8
    # 存在严格性缺陷（Invalid encoding in string），ASCII 转义形态无此问题，
    # 解码后的内容完全等价。
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for t in texts:
            t = t.strip()
            if len(t) < 40:
                continue
            h = hashlib.md5(t.encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")
            n += 1
    return p, n


def merge_all():
    out, seen = CLEAN / "c0_all.jsonl", set()
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for p in sorted(CLEAN.glob("c0_*.jsonl")):
            if p.name == "c0_all.jsonl":
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                h = hashlib.md5(line.encode("utf-8")).hexdigest()
                if h in seen:
                    continue
                seen.add(h)
                f.write(line + "\n")
    return out


def count_tokens(path):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(SNAPSHOT))
    total, batch = 0, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            batch.append(json.loads(line)["text"])
            if len(batch) >= 1000:
                enc = tok(batch, add_special_tokens=False)["input_ids"]
                total += sum(len(x) for x in enc)
                batch = []
    if batch:
        enc = tok(batch, add_special_tokens=False)["input_ids"]
        total += sum(len(x) for x in enc)
    return total


def upsert_manifest(sid, spec, status, n_docs, tokens, note=""):
    rows = []
    if MANIFEST.exists():
        rows = [json.loads(x) for x in
                MANIFEST.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in rows if r.get("id") != sid and r.get("source") != sid]
    rows.append({
        "id": sid, "name": sid, "url": spec["url"] or "",
        "license": spec["license"], "tier": spec.get("tier", "public"),
        "domain": spec["domain"], "lang": spec["lang"],
        "est_tokens": tokens, "docs": n_docs, "status": status,
        "ingested_at": str(date.today()) if status == "ingested" else "",
        "files": spec.get("files") or [f"data/corpora/clean/{_clean_filename(sid)}"],
        "notes": note or spec.get("note", ""),
    })
    rows.sort(key=lambda r: r.get("id") or r.get("source") or "")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="C0 冒烟雾料管线（docs/04）")
    ap.add_argument("--sources", default="all",
                    help="逗号分隔源 id 或 all")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="只重跑转换（raw 已下载）")
    ap.add_argument("--no-tokens", action="store_true",
                    help="跳过 token 计数（快）")
    args = ap.parse_args(argv)

    ids = list(SOURCES) if args.sources == "all" else \
        [x.strip() for x in args.sources.split(",") if x.strip()]
    for sid in ids:
        if sid not in SOURCES:
            raise SystemExit(f"unknown source: {sid}")
    print(f"C0 pipeline: {ids} (skip_fetch={args.skip_fetch})", flush=True)

    total_tokens = 0
    for sid in ids:
        spec = SOURCES[sid]
        print(f"\n[{sid}]", flush=True)
        try:
            texts = spec["fn"](args.skip_fetch)
            p, n = write_clean(sid, texts)
            tokens = 0 if args.no_tokens else count_tokens(p)
            total_tokens += tokens
            upsert_manifest(sid, spec, "ingested", n, tokens)
            print(f"  -> {p.name}: {n} docs, {tokens:,} tokens", flush=True)
        except Exception as e:  # noqa: BLE001
            upsert_manifest(sid, spec, "planned", 0, 0, note=f"failed: {e}")
            print(f"  FAILED: {type(e).__name__}: {e}", flush=True)

    merged = merge_all()
    n_lines = sum(1 for _ in open(merged, encoding="utf-8"))
    print(f"\nmerged -> {merged} ({n_lines} docs, ~{total_tokens:,} tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
