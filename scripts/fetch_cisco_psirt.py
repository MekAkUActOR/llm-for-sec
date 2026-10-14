"""Cisco PSIRT 通告（CVRF 1.2）→ C1 P1 描述层语料（docs/04 §1 P1）。

来源与通路（2026-09-24 调研实测，docs/research/p1-sources.md §2.2）：
  枚举  https://sec.cloudapps.cisco.com/security/center/getCvrfPaginationRecords.x
         ?offset=N&limit=100    （匿名 JSON，X-Total-Count ≈ 5286，含 identifier/typeName）
  下载  .../security/center/contentxml/{typeName}/{identifier}/cvrf/{identifier}_cvrf.xml
         （匿名直链，CVRF 1.2 XML；URL 模式取自官方 cvrfListing.x Angular 模板）
  备注  openVuln API（apix.cisco.com）需 OAuth，未采用；www.cisco.com 对脚本 403。

许可：通告内容 © Cisco，Cisco Baseline API Terms（PDF 在本网络 403 不可取，
如实记录）；2026-09-24 项目决策纳入 C1（docs/04 D3 风险注记）。

产物：
  data/corpora/raw/cisco-psirt/{identifier}_cvrf.xml   原始 XML（断点续抓）
  data/corpora/clean/c0_cisco-psirt.jsonl
  manifest upsert：id=cisco-psirt

用法：
  python scripts/fetch_cisco_psirt.py [--skip-fetch] [--no-tokens] [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "cisco-psirt"
BASE = "https://sec.cloudapps.cisco.com/security/center"
UA = "llm-for-sec-c1/0.1 (security corpus research pipeline; contact: local-researcher)"

SPEC = {
    "url": "https://sec.cloudapps.cisco.com/security/center/cvrfListing.x",
    "license": "Cisco Baseline API Terms / (c) Cisco (project decision 2026-09-24, docs/04 D3)",
    "domain": "security",
    "lang": "en",
    "note": ("Advisory content (c) Cisco; governed by Cisco Baseline API Terms "
             "(https://www.cisco.com/c/dam/en_us/about/doing_business/legal/"
             "supplemental-terms/Baseline-API-Terms.pdf, not fetchable from this "
             "network - 403). Ingested per project decision (C1, D3 risk note in "
             "docs/04). CVRF XML fetched anonymously via contentxml/ endpoints "
             "observed in the official cvrfListing.x Angular template."),
}

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http(url: str, timeout: int = 60, retries: int = 4) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with _OPENER.open(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"GET failed after {retries} tries: {url}: {last}")


# ---------------------------------------------------------------- 转换器（纯函数） --
def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _direct_children(elem, name):
    return [c for c in elem if _local(c.tag) == name]


def _first_child(elem, name):
    for c in elem:
        if _local(c.tag) == name:
            return c
    return None


def _txt(elem) -> str:
    return " ".join((elem.text or "").split()) if elem is not None else ""


def convert_cisco_cvrf(xml_text: str, max_products: int = 40) -> str | None:
    """单篇 Cisco CVRF XML → 描述层文本。

    保留：标题、文档摘要、每个漏洞的 CVE/标题/Notes（Summary/Details/Workaround/
    Current Impact…）、CVSS 分数、受影响产品（去重，超限截断）；剔除：联系信息、
    超长版本号表、重复 CPE 展开。
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    title = _txt(_first_child(root, "DocumentTitle"))
    if not title:
        return None
    doc_type = _txt(_first_child(root, "DocumentType")) or "Cisco Security Advisory"

    # 产品树:ProductID -> 产品名
    products: dict[str, str] = {}
    tree = _first_child(root, "ProductTree")
    if tree is not None:
        for fe in tree.iter():
            if _local(fe.tag) == "FullProductName":
                pid = fe.get("ProductID", "")
                nm = _txt(fe)
                if pid and nm:
                    products[pid] = nm

    lines = [f"{doc_type}: {title}"]

    # 文档级 Notes（通常是 Summary）
    for note in _notes_of(root):
        lines.append(note)

    # 逐漏洞
    vulns = _direct_children(root, "Vulnerability") or \
        [e for e in root.iter() if _local(e.tag) == "Vulnerability"]
    for vuln in vulns:
        cve = _txt(_first_child(vuln, "CVE"))
        vtitle = _txt(_first_child(vuln, "Title"))
        head = f"Vulnerability {cve}" if cve else "Vulnerability"
        if vtitle:
            head += f": {vtitle}"
        lines.append(head)
        score = _cvss_of(vuln)
        if score:
            lines.append(f"CVSS base score: {score}")
        for note in _notes_of(vuln):
            lines.append(note)
        affected = _affected_products(vuln, products)
        if affected:
            shown = affected[:max_products]
            extra = f" (and {len(affected) - max_products} more)" \
                if len(affected) > max_products else ""
            lines.append("Affected products: " + "; ".join(shown) + extra)
    text = "\n".join(l for l in lines if l.strip())
    if len(text) < 120:
        return None
    return text


def _notes_of(elem) -> list[str]:
    """收集 Notes（文档级容器为 DocumentNotes，漏洞级为 Notes）。"""
    out = []
    notes = _first_child(elem, "Notes")
    if notes is None:
        notes = _first_child(elem, "DocumentNotes")
    if notes is None:
        return out
    for note in _direct_children(notes, "Note"):
        ntype = (note.get("Type") or "").strip()
        body = _txt(note)
        if not body:
            continue
        low = body.lower()
        if ntype == "Legal Disclaimers" or "psirt@cisco.com" in low[:200]:
            continue
        label = f"{ntype}: " if ntype and ntype != "Summary" else ""
        out.append(label + body)
    return out


def _cvss_of(vuln) -> str:
    for e in vuln.iter():
        ln = _local(e.tag)
        if ln.startswith("BaseScore") and (e.text or "").strip():
            return (e.text or "").strip()
    return ""


def _affected_products(vuln, products: dict[str, str]) -> list[str]:
    seen, out = set(), []
    statuses = _first_child(vuln, "ProductStatuses")
    if statuses is None:
        return out
    for st in _direct_children(statuses, "Status"):
        if (st.get("Type") or "") != "Known Affected":
            continue
        for pid in (st.text or "").split():
            nm = products.get(pid, "")
            nm = re.sub(r"\s+", " ", nm).strip()
            if nm and nm.lower() not in seen:
                seen.add(nm.lower())
                out.append(nm)
    return out


# ---------------------------------------------------------------- 抓取 --
def enumerate_cvrf() -> list[dict]:
    """getCvrfPaginationRecords.x 全量枚举。

    官方 UI 分页参数为 pageIndex/itemsPerPage（offset 会被忽略——实测 2026-09-24）；
    itemsPerPage=All 可单请求取全量（5286 条，~1.5MB JSON）。
    """
    url = f"{BASE}/getCvrfPaginationRecords.x?pageIndex=0&itemsPerPage=All"
    rows = json.loads(_http(url, timeout=300).decode("utf-8", "replace"))
    records: dict[str, dict] = {}
    for r in rows:
        ident = r.get("identifier", "")
        if ident:
            records[ident] = r
    return list(records.values())


def fetch_one(rec: dict) -> str:
    ident = rec["identifier"]
    tname = rec.get("typeName", "CiscoSecurityAdvisory")
    dest = RAW / f"{ident}_cvrf.xml"
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    try:
        url = f"{BASE}/contentxml/{tname}/{ident}/cvrf/{ident}_cvrf.xml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_http(url))
        time.sleep(0.25)
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"fail:{type(e).__name__}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cisco PSIRT CVRF ingestion (P1)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    if not args.skip_fetch:
        records = enumerate_cvrf()
        print(f"cisco-psirt: {len(records)} CVRF records", flush=True)
        (RAW / "_records.json").parent.mkdir(parents=True, exist_ok=True)
        (RAW / "_records.json").write_text(
            json.dumps(records, indent=0), encoding="utf-8")
        stat = {"ok": 0, "skip": 0, "fail": 0}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for i, r in enumerate(ex.map(fetch_one, records), 1):
                stat[r.split(":")[0]] += 1
                if r.startswith("fail") and stat["fail"] <= 10:
                    print(f"    {r} {r}", flush=True)
                if i % 500 == 0:
                    print(f"    ... {i}/{len(records)} {stat}", flush=True)
        print(f"cisco fetch: {stat}", flush=True)

    files = sorted(RAW.glob("*_cvrf.xml"))
    print(f"raw CVRF files: {len(files)}", flush=True)
    texts = []
    for p in files:
        t = convert_cisco_cvrf(p.read_text(encoding="utf-8", errors="replace"))
        if t:
            texts.append(t)
    print(f"converted: {len(texts)}/{len(files)}", flush=True)
    out, n = write_clean("cisco-psirt", texts)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("cisco-psirt", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
