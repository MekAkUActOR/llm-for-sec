"""MSRC CVRF API v3.0 → C1 P1 描述层语料（docs/04 §1 P1）。

来源与通路（2026-09-24 调研实测，docs/research/p1-sources.md §2.1）：
  索引  https://api.msrc.microsoft.com/cvrf/v3.0/Updates
        （免 API key，单页全量 192 条 {ID, Alias, DocumentTitle, Severity, dates}）
  单文档 .../cvrf/v3.0/cvrf/{ID}    如 2025-Jan（CVRF 1.1 XML，6.7KB–9.8MB）
  备注  HEAD 不支持（405）；v2.0 已下线。

许可：MSRC CVRF API swagger 无 termsOfService 字段（许可未声明）；Microsoft Learn
Terms of Use（learn.microsoft.com/en-us/legal/termsofuse）限定个人非商用——
"Unless otherwise specified, the Services are for your personal and non-commercial
use. You may not modify, copy, distribute, transmit, publicly display, perform,
reproduce, publish, license, create derivative works from, transfer or sell any
information, software, products or services obtained from the Services (except
for your own, personal, non-commercial use) without prior written consent from
Microsoft."  2026-09-24 项目决策纳入 C1（docs/04 D3 风险注记）。

产物：
  data/corpora/raw/msrc-cvrf/{ID}.xml          原始 CVRF（断点续抓）
  data/corpora/clean/c0_msrc-cvrf.jsonl
  manifest upsert：id=msrc-cvrf

用法：
  python scripts/fetch_msrc_cvrf.py [--skip-fetch] [--no-tokens] [--workers 3]
"""
from __future__ import annotations

import argparse
import html as _html
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
RAW = ROOT / "data" / "corpora" / "raw" / "msrc-cvrf"
BASE = "https://api.msrc.microsoft.com/cvrf/v3.0"
UA = "llm-for-sec-c1/0.1 (security corpus research pipeline; contact: local-researcher)"

SPEC = {
    "url": "https://api.msrc.microsoft.com/cvrf/v3.0/Updates",
    "license": ("MSRC CVRF API: no termsOfService declared in swagger; Microsoft "
                "Learn TOU personal/non-commercial (project decision 2026-09-24, docs/04 D3)"),
    "domain": "security",
    "lang": "en",
    "note": ("MSRC CVRF API v3.0 has no declared terms of use (swagger "
             "termsOfService field absent). Microsoft Learn Terms of Use verbatim: "
             "\"Unless otherwise specified, the Services are for your personal and "
             "non-commercial use. You may not modify, copy, distribute, transmit, "
             "publicly display, perform, reproduce, publish, license, create "
             "derivative works from, transfer or sell any information, software, "
             "products or services obtained from the Services (except for your own, "
             "personal, non-commercial use) without prior written consent from "
             "Microsoft.\" Ingested per project decision (C1, D3 risk note in docs/04)."),
}

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_TAG = re.compile(r"<[^>]+>")

_SEV_RANK = {"critical": 4, "important": 3, "moderate": 2, "low": 1, "none": 0}


def _http(url: str, timeout: int = 240, retries: int = 4) -> bytes:
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
    if elem is None:
        return ""
    # MSRC Notes 正文是 HTML 转义片段：反转义后剥标签
    raw = (elem.text or "")
    if "&lt;" in raw or "&amp;" in raw:
        raw = _html.unescape(raw)
    raw = _TAG.sub(" ", raw)
    return " ".join(raw.split())


def _text_plain(elem) -> str:
    return " ".join((elem.text or "").split()) if elem is not None else ""


def _product_names(root) -> dict[str, str]:
    out: dict[str, str] = {}
    tree = _first_child(root, "ProductTree")
    if tree is None:
        return out
    for fe in tree.iter():
        if _local(fe.tag) == "FullProductName":
            pid = fe.get("ProductID", "")
            nm = _text_plain(fe)
            if pid and nm:
                out[pid] = nm
    return out


def _max_severity(vuln) -> str:
    best, rank = "", -1
    for thr in vuln.iter():
        if _local(thr.tag) == "Threat" and (thr.get("Type") or "") == "Severity":
            desc = _text_plain(_first_child(thr, "Description"))
            r = _SEV_RANK.get(desc.lower().strip(), -1)
            if r > rank:
                best, rank = desc, r
    return best


def _affected_products(vuln, products: dict[str, str],
                       cap: int = 25) -> tuple[list[str], int]:
    seen, out = set(), []
    total = 0
    statuses = _first_child(vuln, "ProductStatuses")
    if statuses is None:
        return out, total
    for st in _direct_children(statuses, "Status"):
        if (st.get("Type") or "") != "Known Affected":
            continue
        for pid_el in _direct_children(st, "ProductID"):
            pid = _text_plain(pid_el)
            if not pid:
                continue
            total += 1
            nm = products.get(pid, "")
            nm = re.sub(r"\s+", " ", nm).strip()
            if nm and nm.lower() not in seen:
                seen.add(nm.lower())
                out.append(nm)
    return out, total


def _remediations(vuln, cap: int = 5) -> list[str]:
    out, seen = [], set()
    rem = _first_child(vuln, "Remediations")
    if rem is None:
        return out
    for r in _direct_children(rem, "Remediation"):
        desc = _text_plain(_first_child(r, "Description"))
        if not desc:
            continue
        key = desc.lower()
        if key not in seen:
            seen.add(key)
            out.append(desc)
    return out[:cap]


def convert_msrc_cvrf(xml_text: str, max_products: int = 25) -> str | None:
    """单篇 MSRC CVRF 文档 → 描述层文本。

    保留：文档标题、Details 文档注记、每漏洞的 CVE/标题/FAQ 描述、最高严重级、
    CWE、受影响产品（去重封顶）、修复项（KB 标题，封顶 5）；剔除：Tag/CNA/Other
    短注记、逐 ProductID 展开的海量重复、法律免责声明。
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    title = _text_plain(_first_child(root, "DocumentTitle"))
    if not title:
        return None
    doc_type = _text_plain(_first_child(root, "DocumentType")) or "Security Update"
    lines = [f"Microsoft {doc_type}: {title}"]

    # 文档级 Details 注记
    dnotes = _first_child(root, "DocumentNotes")
    if dnotes is not None:
        for note in _direct_children(dnotes, "Note"):
            if (note.get("Type") or "") in ("Details", "General", "Summary"):
                body = _txt(note)
                if len(body) > 80:
                    lines.append(body)
                    break

    products = _product_names(root)
    vulns = [e for e in root if _local(e.tag) == "Vulnerability"]
    for vuln in vulns:
        cve = _text_plain(_first_child(vuln, "CVE"))
        vtitle = _text_plain(_first_child(vuln, "Title"))
        head = f"Vulnerability {cve}" if cve else "Vulnerability"
        if vtitle:
            head += f": {vtitle}"
        sev = _max_severity(vuln)
        cwe = _first_child(vuln, "CWE")
        if cwe is not None:
            cwe_txt = _text_plain(cwe) or cwe.get("ID", "")
            head += f" [CWE: {cwe_txt}]" if cwe_txt else ""
        lines.append(head)
        if sev:
            lines.append(f"Maximum severity: {sev}")
        # FAQ/Description 注记（跳过空与短标签注记）
        vnotes = _first_child(vuln, "Notes")
        if vnotes is not None:
            for note in _direct_children(vnotes, "Note"):
                ntype = note.get("Type") or ""
                if ntype in ("Description", "FAQ", "General", "Additional Information"):
                    body = _txt(note)
                    if len(body) > 80:
                        lines.append((f"{ntype}: " if ntype != "Description" else "") + body)
        affected, total = _affected_products(vuln, products, max_products)
        if affected:
            extra = f" (and {total - len(affected)} more product references)" \
                if total > len(affected) else ""
            lines.append("Affected products: " + "; ".join(affected[:max_products]) + extra)
        rem = _remediations(vuln)
        if rem:
            lines.append("Remediation: " + "; ".join(rem))
    text = "\n".join(l for l in lines if l.strip())
    if len(text) < 120:
        return None
    return text


# ---------------------------------------------------------------- 抓取 --
def enumerate_updates() -> list[dict]:
    data = _http(f"{BASE}/Updates")
    payload = json.loads(data.decode("utf-8", "replace"))
    if isinstance(payload, dict):
        # OData 包装:{"@odata.context": ..., "value": [...]}
        rows = payload.get("value", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    return [r for r in rows if isinstance(r, dict) and r.get("ID")]


def fetch_one(rec: dict) -> str:
    ident = rec["ID"]
    dest = RAW / f"{ident}.xml"
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_http(f"{BASE}/cvrf/{ident}"))
        time.sleep(0.3)
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"fail:{type(e).__name__}:{e}"[:160]


def main(argv=None):
    ap = argparse.ArgumentParser(description="MSRC CVRF ingestion (P1)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args(argv)

    if not args.skip_fetch:
        updates = enumerate_updates()
        print(f"msrc-cvrf: {len(updates)} update IDs", flush=True)
        (RAW / "_updates.json").parent.mkdir(parents=True, exist_ok=True)
        (RAW / "_updates.json").write_text(json.dumps(updates, indent=0),
                                           encoding="utf-8")
        stat = {"ok": 0, "skip": 0, "fail": 0}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for i, r in enumerate(ex.map(fetch_one, updates), 1):
                stat[r.split(":")[0]] += 1
                if r.startswith("fail") and stat["fail"] <= 10:
                    print(f"    {r}", flush=True)
                if i % 20 == 0:
                    print(f"    ... {i}/{len(updates)} {stat}", flush=True)
        print(f"msrc fetch: {stat}", flush=True)

    files = sorted(RAW.glob("*.xml"))
    print(f"raw CVRF files: {len(files)}", flush=True)
    texts = []
    for p in files:
        t = convert_msrc_cvrf(p.read_text(encoding="utf-8", errors="replace"))
        if t:
            texts.append(t)
    print(f"converted: {len(texts)}/{len(files)}", flush=True)
    out, n = write_clean("msrc-cvrf", texts)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("msrc-cvrf", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
