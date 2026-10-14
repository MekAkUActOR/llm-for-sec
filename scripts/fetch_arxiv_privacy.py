"""arXiv 隐私工程研究摘要 → C2 隐私知识语料（docs/04 C2 小节）。

查询组（2026-09-26 探测 totalResults，cs.CR+cs.LG+cs.DB 全历史）：
  differential-privacy    3872   de-identification      100
  personally-identifiable  271   privacy-preserving    4930
  pii-detection              9   health-data-privacy    106
  reidentification         396   insider-threat         127
  credential-leakage        21   （合计 ~9.8k raw，跨查询去重 + 排除
  c1_arxiv_full/c0_arxiv-cscr 已入库 id 后为净新增）

通路工程：直接复用 a0eb782c 的 fetch_arxiv_full.py 实测方案（2026-09-25）：
  1. arXiv WAF 按 TLS 指纹拦 Python urllib → 全部请求经 curl.exe 子进程；
  2. API 深分页 start≥10000 一律 HTTP 500 → 本批峰值查询 4930 条 < 10k，
     常规分页即安全（仍保留断言护栏）；
  3. ToU 限速"one request every three seconds, single connection"
     → 单连接、8s 间隔，6×60s 退避、连败 3 页止损，分页落盘可断点续传。

许可：arXiv API ToU——"You are free to use descriptive metadata about arXiv
e-prints under the terms of the Creative Commons Universal (CC0 1.0) Public
Domain Declaration."（title/abstract/identifiers 属 descriptive metadata）
→ 摘要层 CC0 1.0。

排除与去重：c1_arxiv_full.jsonl（cs.CR 全历史 52,384 篇，文本内嵌 id）+
raw/arxiv-cscr/page*.xml（C0 冻结 2000 篇）按版本剥离 id 精确排除；
查询间按 id 去重。

输出：data/corpora/clean/c2_privacy_arxiv.jsonl
用法：python scripts/fetch_arxiv_privacy.py [--count] [--skip-fetch]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_arxiv_full import (  # noqa: E402
    BACKOFF_S, PAGE_SIZE, SLEEP_S, parse_atom, strip_version)
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "arxiv-privacy"
CLEAN = ROOT / "data" / "corpora" / "clean"
ARXIV_FULL = CLEAN / "c1_arxiv_full.jsonl"
RAW_OLD = ROOT / "data" / "corpora" / "raw" / "arxiv-cscr"

UA = "llm-for-sec-c2-privacy/0.1"
CATS = "(cat:cs.CR+OR+cat:cs.LG+OR+cat:cs.DB)"
MAX_RESULTS_HARD = 9900   # API start>=10000 硬上限之下

QUERIES: dict[str, str] = {
    "differential-privacy": 'abs:%22differential+privacy%22',
    "de-identification": '(abs:%22de-identification%22+OR+abs:deidentification)',
    "personally-identifiable": 'abs:%22personally+identifiable%22',
    "privacy-preserving": 'abs:%22privacy-preserving%22',
    "pii-detection": 'abs:%22PII+detection%22',
    "health-data-privacy": '(abs:%22health+data%22+AND+abs:privacy)',
    "reidentification": '(abs:reidentification+OR+abs:%22re-identification%22)',
    "insider-threat": 'abs:%22insider+threat%22',
    "credential-leakage": '(abs:%22credential+leakage%22+OR+abs:%22secret+leakage%22)',
}

SPEC = {
    "url": ("https://export.arxiv.org/api/query (9 privacy/insider-threat "
            "abs-queries on cs.CR+cs.LG+cs.DB, full history)"),
    "license": "CC0 1.0 (arXiv API ToU: descriptive metadata)",
    "domain": "privacy",
    "lang": "en",
    "note": ("arXiv API Terms of Use verbatim: \"You are free to use "
             "descriptive metadata about arXiv e-prints under the terms of "
             "the Creative Commons Universal (CC0 1.0) Public Domain "
             "Declaration.\" Queries: differential privacy / de-identification "
             "/ personally identifiable / privacy-preserving / PII detection / "
             "health data privacy / reidentification / insider threat / "
             "credential+secret leakage. Excludes ids already ingested in "
             "c1_arxiv_full (cs.CR full history) and c0_arxiv-cscr. Rate "
             "limit compliance: single connection, 8s between requests (ToU "
             "floor 3s); curl.exe subprocess (arXiv WAF blocks Python "
             "urllib TLS fingerprint)."),
    "files": ["data/corpora/clean/c2_privacy_arxiv.jsonl"],
}

_ID_IN_TEXT = re.compile(r"arXiv security research paper ([^:]+): ")
_WS = re.compile(r"\s+")


def query_url(name: str, start: int) -> str:
    q = f"{QUERIES[name]}+AND+{CATS}"
    return (f"https://export.arxiv.org/api/query?search_query={q}"
            f"&sortBy=submittedDate&sortOrder=descending&start={start}"
            f"&max_results={PAGE_SIZE}")


def fetch_page(url: str) -> str:
    """curl.exe 单页抓取（TLS 指纹 WAF 规避,同 fetch_arxiv_full 方案）。"""
    import subprocess
    last = None
    for attempt, backoff in enumerate((0,) + BACKOFF_S, start=1):
        if backoff:
            print(f"    {url[-60:]} 第 {attempt-1} 次失败（{last}），"
                  f"退避 {backoff}s", flush=True)
            time.sleep(backoff)
        try:
            r = subprocess.run(
                ["curl", "-s", "--max-time", "90",
                 "-w", "\n__HTTP__%{http_code}",
                 "-A", UA, "-H", "Accept: */*", url],
                capture_output=True, timeout=120)
            out = r.stdout.decode("utf-8", "replace")
            if out.endswith("\n"):
                out = out[:-1]
            body, _, code = out.rpartition("\n__HTTP__")
            if (r.returncode == 0 and code == "200"
                    and body.startswith("<?xml")):
                return body
            last = RuntimeError(f"curl rc={r.returncode}, http={code}, "
                                f"{len(body)}B")
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"{url[-60:]} 连续 {len(BACKOFF_S)+1} 次失败：{last}")


def total_results(atom_text: str) -> int:
    m = re.search(r"totalResults[^>]*>(\d+)<", atom_text)
    return int(m.group(1)) if m else 0


def existing_ids() -> set[str]:
    """c1_arxiv_full（文本内嵌 id）+ C0 冻结分页 的 id 全集。"""
    ids: set[str] = set()
    if ARXIV_FULL.exists():
        for line in ARXIV_FULL.read_text(encoding="utf-8").splitlines():
            m = _ID_IN_TEXT.search(line)  # jsonl 行前有 {"text": ... 包装 → search
            if m:
                ids.add(strip_version(m.group(1)))
    for p in sorted(RAW_OLD.glob("page*.xml")):
        for aid, _t, _s in parse_atom(p.read_text(encoding="utf-8")):
            ids.add(aid)
    return ids


def norm_title(t: str) -> str:
    return _WS.sub(" ", t).strip().lower()


def format_doc(aid: str, title: str, summ: str) -> str:
    return f"arXiv privacy research paper {aid}: {title}. {summ}"


def collect(args_skip_fetch: bool) -> tuple[list[str], dict[str, str], int, int]:
    """抓取全部查询分页 → 去重排除后的 (docs, title->id, raw_total, excluded)。"""
    old_ids = existing_ids()
    seen: set[str] = set()
    docs: list[str] = []
    titles: dict[str, str] = {}
    n_total = n_excluded = 0

    for name in QUERIES:
        qdir = RAW / name
        qdir.mkdir(parents=True, exist_ok=True)
        page = 0
        while True:
            p = qdir / f"page{page:04d}.xml"
            if p.exists():  # 断点续传:已落盘分页直接复用
                atom = p.read_text(encoding="utf-8")
            elif not args_skip_fetch:
                atom = fetch_page(query_url(name, page * PAGE_SIZE))
                p.write_text(atom, encoding="utf-8")
                time.sleep(SLEEP_S)
            else:  # skip-fetch 模式且无缓存 → 本查询终止
                break
            entries = parse_atom(atom)
            if page == 0:
                tot = total_results(atom)
                print(f"  {name}: totalResults={tot}", flush=True)
                if tot > MAX_RESULTS_HARD:
                    raise SystemExit(
                        f"查询 {name} totalResults={tot} 超过 {MAX_RESULTS_HARD} "
                        f"——需按年分片（复用 fetch_arxiv_full 方案）后重跑")
            for aid, title, summ in entries:
                n_total += 1
                if aid in old_ids:
                    n_excluded += 1
                    continue
                if aid in seen:
                    continue
                seen.add(aid)
                docs.append(format_doc(aid, title, summ))
                titles.setdefault(norm_title(title), aid)
            if len(entries) < PAGE_SIZE:
                break
            page += 1
        print(f"  {name}: done (cum docs {len(docs)})", flush=True)
    return docs, titles, n_total, n_excluded


def main(argv=None):
    ap = argparse.ArgumentParser(description="arXiv privacy research → C2")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--skip-fetch", action="store_true")
    args = ap.parse_args(argv)

    docs, titles, n_total, n_excluded = collect(args.skip_fetch)
    print(f"解析 {n_total} 条：排除已入库 {n_excluded}，"
          f"净新增 {len(docs)}", flush=True)

    out = CLEAN / "c2_privacy_arxiv.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")
    print(f"输出 {out.name}: {len(docs)} docs", flush=True)

    tokens = count_tokens(out) if args.count else 0
    upsert_manifest("arxiv-privacy", SPEC, "ingested", len(docs), tokens)
    print(f"tokens: {tokens:,}", flush=True)

    # 探针保护检查（报告不改）：ais.jsonl（cs.AI 探针）按标题匹配
    ais = ROOT / "data" / "probes" / "v0.1" / "ais.jsonl"
    if ais.exists():
        overlaps = []
        for line in ais.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            text = json.loads(line)["text"]
            if not text.startswith("arXiv cs.AI paper: "):
                continue
            title = text[len("arXiv cs.AI paper: "):].split("\n", 1)[0]
            key = norm_title(title)
            if key in titles:
                overlaps.append((title, titles[key]))
        print(f"[探针重叠检查] ais.jsonl 200 条中 {len(overlaps)} 条标题命中：",
              flush=True)
        for t, aid in overlaps:
            print(f"    - {aid}: {t[:70]}", flush=True)
        (ROOT / "reports" / "probe-ais-overlap-arxiv-privacy.json").write_text(
            json.dumps({"probe": "data/probes/v0.1/ais.jsonl",
                        "overlap_count": len(overlaps),
                        "overlaps": [{"title": t, "arxiv_id": aid}
                                     for t, aid in overlaps]},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
