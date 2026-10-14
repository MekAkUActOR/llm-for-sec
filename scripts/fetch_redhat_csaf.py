"""Red Hat CSAF v2 通告（RHSA）→ C1 P1 描述层语料（docs/04 §1 P1）。

来源与通路（2026-09-24 调研实测，docs/research/p1-sources.md §2.4）：
  年目录  https://security.access.redhat.com/data/csaf/v2/advisories/{2001..2026}/
          （静态目录列表，无认证；目录按发布年分组，含少量跨年前缀文件，全局按
          文件名去重）
  文件    rhsa-YYYY_NNNN.json（CSAF v2 JSON，仅取 rhsa- 前缀，过滤 rhba-/rhea-）

许可：CC-BY 4.0 —— 每个 CSAF 文件 document.notes 里带 legal_disclaimer 注记
（"This content is licensed under the Creative Commons Attribution 4.0
License..."），manifest notes 逐字摘录。

产物：
  data/corpora/raw/redhat-csaf/rhsa-*.json   原始 JSON（断点续抓）
  data/corpora/clean/c0_redhat-csaf.jsonl
  manifest upsert：id=redhat-csaf

用法：
  python scripts/fetch_redhat_csaf.py [--skip-fetch] [--no-tokens] [--workers 6]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "redhat-csaf"
BASE = "https://security.access.redhat.com/data/csaf/v2/advisories"
UA = "llm-for-sec-c1/0.1 (security corpus research pipeline; contact: local-researcher)"

SPEC = {
    "url": "https://security.access.redhat.com/data/csaf/v2/advisories/",
    "license": "CC-BY-4.0 (declared in each CSAF legal_disclaimer note)",
    "domain": "security",
    "lang": "en",
    "note": ("Each CSAF file carries a legal_disclaimer note, verbatim: \"This "
             "content is licensed under the Creative Commons Attribution 4.0 "
             "License. If supplying a citation, please use the CC-BY 4.0 "
             "attribution format. This advisory content is provided by Red Hat "
             "under the CC-BY 4.0 license.\""),
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
def _walk_products(node, out: dict, depth: int = 0):
    """递归收集 product_tree 中 product_id → 产品名映射。"""
    if depth > 8 or not isinstance(node, dict):
        return
    for fpn in node.get("full_product_names", []) or []:
        pid, nm = fpn.get("product_id"), fpn.get("name")
        if pid and nm:
            out.setdefault(pid, nm)
    for key in ("branches", "relationships"):
        for ch in node.get(key, []) or []:
            _walk_products(ch, out, depth + 1)
    prod = node.get("product")
    if isinstance(prod, dict):
        _walk_products(prod, out, depth + 1)
    fpn = node.get("full_product_name")
    if isinstance(fpn, dict):
        pid, nm = fpn.get("product_id"), fpn.get("name")
        if pid and nm:
            out.setdefault(pid, nm)


def _product_refs(vuln: dict) -> tuple[list[str], int]:
    ids: list[str] = []
    for status in ("known_affected", "affected", "fixed"):
        ps = vuln.get("product_status", {})
        ids += ps.get(status, []) or []
    return ids, len(ids)


def convert_redhat_csaf(data: dict, max_products: int = 15) -> str | None:
    """单篇 Red Hat CSAF JSON → 描述层文本。

    保留：RHSA 号/标题/日期、严重级、summary/general 注记、每漏洞 CVE/标题/
    CWE/CVSS 分数、涉及产品（去重封顶）；剔除：法律免责声明全文（许可文本已存
    manifest）、references URL 堆、逐产品修复细节表。
    """
    doc = data.get("document") or {}
    title = (doc.get("title") or "").strip()
    if not title:
        return None
    tracking = doc.get("tracking") or {}
    rhid = tracking.get("id", "")
    date = (tracking.get("initial_release_date") or "")[:10]
    head = f"Red Hat Security Advisory {rhid}: {title}"
    if date:
        head += f" ({date})"
    lines = [head]
    sev = (doc.get("aggregate_severity") or {}).get("text")
    if sev:
        lines.append(f"Severity: {sev}")
    for note in doc.get("notes", []) or []:
        if note.get("category") in ("summary", "general"):
            t = " ".join((note.get("text") or "").split())
            if t:
                lines.append(t)

    products: dict[str, str] = {}
    _walk_products(data.get("product_tree") or {}, products)

    for v in data.get("vulnerabilities", []) or []:
        cve = v.get("cve", "")
        vtitle = v.get("title", "")
        vh = f"Vulnerability {cve}" if cve else "Vulnerability"
        if vtitle:
            vh += f": {vtitle}"
        cwe = v.get("cwe") or {}
        if cwe.get("name"):
            vh += f" [CWE: {cwe['name']}]"
        lines.append(vh)
        for s in v.get("scores", []) or []:
            cv = s.get("cvss_v3") or s.get("cvss_v2") or {}
            score = cv.get("baseScore")
            if score is not None:
                sevtxt = cv.get("baseSeverity", "")
                lines.append(f"CVSS base score: {score}"
                             + (f" ({sevtxt})" if sevtxt else ""))
                break
        ids, total = _product_refs(v)
        names, seen = [], set()
        for pid in ids:
            nm = re.sub(r"\s+", " ", products.get(pid, "")).strip()
            if nm and nm.lower() not in seen:
                seen.add(nm.lower())
                names.append(nm)
        if names:
            extra = f" (and {total - len(names)} more product references)" \
                if total > len(names) else ""
            lines.append("Products: " + "; ".join(names[:max_products]) + extra)
    text = "\n".join(l for l in lines if l.strip())
    if len(text) < 120:
        return None
    return text


# ---------------------------------------------------------------- 抓取 --
def list_year_files(year: int) -> list[str]:
    html = _http(f"{BASE}/{year}/").decode("utf-8", "replace")
    return sorted(set(re.findall(r'href="(rhsa-\d+_\d+\.json)"', html)))


def fetch_one(fname: str) -> str:
    dest = RAW / fname
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    try:
        # 文件名里的年份前缀可能与所在目录不同，双试
        year = fname.split("-")[1].split("_")[0]
        candidates = [f"{BASE}/{year}/{fname}"]
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_http(candidates[0]))
            return "ok"
        except Exception:
            pass
        # 回退：在全部年目录中找（前缀年 ≠ 发布年时）
        for y in range(int(year), min(2027, int(year) + 3)):
            try:
                dest.write_bytes(_http(f"{BASE}/{y}/{fname}"))
                return "ok"
            except Exception:
                continue
        return "fail:notfound"
    except Exception as e:  # noqa: BLE001
        return f"fail:{type(e).__name__}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Red Hat CSAF ingestion (P1)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)

    if not args.skip_fetch:
        years = sorted(set(re.findall(
            r'href="(\d{4})/"',
            _http(f"{BASE}/").decode("utf-8", "replace"))))
        print(f"year dirs: {years[0]}..{years[-1]} ({len(years)})", flush=True)
        all_files: set[str] = set()
        for y in years:
            try:
                files = list_year_files(int(y))
                all_files.update(files)
                print(f"  {y}: {len(files)} rhsa files (cum {len(all_files)})",
                      flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  {y}: LIST FAIL {e}", flush=True)
            time.sleep(0.3)
        print(f"unique rhsa files: {len(all_files)}", flush=True)
        RAW.mkdir(parents=True, exist_ok=True)
        stat = {"ok": 0, "skip": 0, "fail": 0}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for i, r in enumerate(ex.map(fetch_one, sorted(all_files)), 1):
                stat[r.split(":")[0]] += 1
                if r.startswith("fail") and stat["fail"] <= 20:
                    print(f"    {r}", flush=True)
                if i % 1000 == 0:
                    print(f"    ... {i}/{len(all_files)} {stat}", flush=True)
        print(f"redhat fetch: {stat}", flush=True)

    files = sorted(RAW.glob("rhsa-*.json"))
    print(f"raw CSAF files: {len(files)}", flush=True)
    texts = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        t = convert_redhat_csaf(data)
        if t:
            texts.append(t)
    print(f"converted: {len(texts)}/{len(files)}", flush=True)
    out, n = write_clean("redhat-csaf", texts)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("redhat-csaf", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
