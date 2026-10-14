# -*- coding: utf-8 -*-
"""探针 v0.4 — privacy 换源重建（非 GDPR 原文）。

背景（docs/research/probe-contamination-audit.md）：v0.1.1/v0.3 的 privacy 173 篇
取自 gdpr-info.eu 的**序言（recitals）**页面，而 c0_gdpr.jsonl（训练语料）含
完整 GDPR（含序言）→ 篇级 64.9% 系统性污染；且抓取文本夹带站点导航垃圾
（"Menu and widgets" 等），PPL 读数的绝对幅度不可信。

v0.4 做法：换源到**非 GDPR 原文**的监管指导文本（英国 ICO 的 UK GDPR 指导页，
改写而非逐字条款），并执行项目既有纪律——**单元级预筛是硬闸**：

  1. 抓取（同域有界爬取，限页数/深度，礼貌间隔）→ 正文抽取（stdlib
     html.parser，剥 script/style/nav/footer，段落归并成 ~400-1200 字单元）；
  2. 单元级 8-gram 预筛：候选单元建索引，扫训练侧语料（c0_gdpr /
     c0_cn-laws / c0_cn-regs / c2_privacy_arxiv / c1_arxiv_full /
     c1_zhwiki_sec / sft_m25），共享 ≥60 字符的**单元**即弃（不是弃整页）；
  3. 确定性选取（按 md5 排序取前 N，N 与旧版 173 篇对齐以便纵向量级可比）。

用法：
  python scripts/gen_probes_v04_privacy.py --fetch-only      # 抓取+抽取+落原始单元
  python scripts/gen_probes_v04_privacy.py --screen-only     # 复筛+产出（不联网）
  python scripts/gen_probes_v04_privacy.py                   # 两步都跑
输出：
  data/probes/v0.4/_raw_privacy_units.jsonl（抓取原始，中间件）
  data/probes/v0.4/privacy.jsonl（成品，单字段 {"text": ...}）
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUTDIR = ROOT / "data" / "probes" / "v0.4"
RAW = OUTDIR / "_raw_privacy_units.jsonl"
OUT = OUTDIR / "privacy.jsonl"

SEEDS = [
    "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/",
    "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/",
    "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/",
    "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/",
    "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/",
    "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/security/",
    "https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/international-transfers/",
]
HOST = "ico.org.uk"
PATH_PREFIX = "/for-organisations/uk-gdpr-guidance-and-resources/"
MAX_PAGES = 90
MAX_DEPTH = 3
TARGET_UNITS = 173
MIN_UNIT, MAX_UNIT = 260, 1400
UA = "Mozilla/5.0 (compatible; llm_for_sec-probe-builder/0.4)"

TRAIN_SIDE = [
    ("c0_gdpr", ROOT / "data" / "corpora" / "clean" / "c0_gdpr.jsonl", 0),
    ("c0_cn-laws", ROOT / "data" / "corpora" / "clean" / "c0_cn-laws.jsonl", 0),
    ("c0_cn-regs", ROOT / "data" / "corpora" / "clean" / "c0_cn-regs.jsonl", 0),
    ("c2_privacy_arxiv", ROOT / "data" / "corpora" / "clean" / "c2_privacy_arxiv.jsonl", 0),
    ("c1_arxiv_full", ROOT / "data" / "corpora" / "clean" / "c1_arxiv_full.jsonl", 0),
    ("c1_zhwiki_sec", ROOT / "data" / "corpora" / "clean" / "c1_zhwiki_sec.jsonl", 0),
    ("sft_m25", ROOT / "data" / "lf" / "sft_m25.jsonl", 0),
]

DROP_PAT = re.compile(
    r"(cookie|we use cookies|share this page|skip to main|sign up|newsletter|"
    r"accept all|manage preferences|©|all rights reserved|back to top|"
    r"print this page|email this page|follow us|subscribe)", re.I)


class MainText(HTMLParser):
    """极简正文抽取：只取 body 内可见文本，跳过 script/style/nav/footer。"""

    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg",
            "form", "aside"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.blocks: list[str] = []
        self.cur: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag in ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div",
                   "br", "section", "article", "td"):
            self.flush()
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(v)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag in ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush()

    def handle_data(self, data):
        if self.skip:
            return
        s = data.strip()
        if s:
            self.cur.append(s)

    def flush(self):
        if self.cur:
            t = " ".join(self.cur)
            self.cur = []
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                self.blocks.append(t)


def fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            if r.status != 200:
                return None
            raw = r.read()
        for enc in ("utf-8", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return None
    except Exception:  # noqa: BLE001
        return None


def units_from(blocks: list[str]) -> list[str]:
    """段落归并成 260~1400 字单元；过滤模板/导航垃圾。"""
    units, buf = [], ""
    for b in blocks:
        if len(b) < 25 or DROP_PAT.search(b):
            continue
        if len(b) > MAX_UNIT:
            for k in range(0, len(b), MAX_UNIT):
                chunk = b[k:k + MAX_UNIT].strip()
                if len(chunk) >= MIN_UNIT:
                    units.append(chunk)
            continue
        if len(buf) + len(b) + 1 <= MAX_UNIT:
            buf = (buf + " " + b).strip()
        else:
            if len(buf) >= MIN_UNIT:
                units.append(buf)
            buf = b
    if len(buf) >= MIN_UNIT:
        units.append(buf)
    return units


def crawl() -> list[dict]:
    seen, queue, pages = {SEEDS[0]}, [(u, 0) for u in SEEDS], 0
    raw_units = []
    while queue and pages < MAX_PAGES:
        url, depth = queue.pop(0)
        h = fetch(url)
        pages += 1
        time.sleep(0.4)
        if not h:
            print(f"  [skip] {url}")
            continue
        p = MainText()
        try:
            p.feed(h)
        except Exception:  # noqa: BLE001
            continue
        us = units_from(p.blocks)
        if us:
            for i, u in enumerate(us):
                raw_units.append({"text": u, "src": url, "unit": i})
        print(f"  [{pages:03d}] {len(us):3d} units  {url[:96]}")
        if depth < MAX_DEPTH:
            for href in p.links:
                nu = urllib.parse.urljoin(url, href)
                sp = urllib.parse.urlsplit(nu)
                if (sp.scheme == "https" and sp.netloc.endswith(HOST)
                        and sp.path.startswith(PATH_PREFIX)
                        and nu.split("#")[0] not in seen):
                    seen.add(nu.split("#")[0])
                    queue.append((nu.split("#")[0], depth + 1))
    return raw_units


def train_docs(path: Path, limit: int):
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            try:
                j = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(j.get("text"), str):
                yield j["text"]
            elif j.get("messages"):
                yield "\n".join(m.get("content", "") for m in j["messages"])


def screen(units: list[dict]) -> tuple[list[dict], dict]:
    from check_sft_contamination import (build_ngram_index, doc_probe_hits,
                                         verify_shared_substring)
    index = {f"u{i}": u["text"] for i, u in enumerate(units)}
    idx = build_ngram_index(index)
    dirty: set[str] = set()
    stats = {"units": len(units), "ngram_index_keys": len(idx), "per_source": {}}
    for label, path, limit in TRAIN_SIDE:
        hits = n = 0
        if not path.exists():
            stats["per_source"][label] = "MISSING"
            continue
        for doc in train_docs(path, limit):
            n += 1
            if not doc:
                continue
            for pid, win in doc_probe_hits(doc, idx).items():
                if verify_shared_substring(doc, index[pid], window=win) >= 60:
                    if pid not in dirty:
                        dirty.add(pid)
                        hits += 1
        stats["per_source"][label] = {"docs": n, "new_dirty_units": hits}
        print(f"  scan {label:18s} docs={n:7d} dirty+={hits:4d} (total {len(dirty)})")
    clean = [u for i, u in enumerate(units) if f"u{i}" not in dirty]
    stats["dirty_units"] = len(dirty)
    stats["clean_units"] = len(clean)
    return clean, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--screen-only", action="store_true")
    ap.add_argument("--target", type=int, default=TARGET_UNITS)
    args = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    if not args.screen_only:
        print("== crawl ==")
        units = crawl()
        if not units:
            raise SystemExit("抓取为空——检查网络或种子 URL")
        with RAW.open("w", encoding="utf-8", newline="\n") as f:
            for u in units:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")
        print(f"raw units: {len(units)} -> {RAW}")
        if args.fetch_only:
            return 0

    units = [json.loads(l) for l in RAW.open(encoding="utf-8")]
    print(f"== screen ({len(units)} raw units) ==")
    clean, stats = screen(units)
    print(json.dumps(stats, ensure_ascii=False, indent=1))

    # 页内单元去重（跨页重复的指导文本）
    seen, dedup = set(), []
    for u in clean:
        k = hashlib.md5(u["text"].encode()).hexdigest()
        if k in seen:
            continue
        seen.add(k)
        dedup.append(u)
    dedup.sort(key=lambda u: hashlib.md5(u["text"].encode()).hexdigest())
    picked = dedup[:args.target]
    if len(picked) < args.target:
        raise SystemExit(f"干净单元不足：{len(picked)} < {args.target}")
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for u in picked:
            f.write(json.dumps({"text": u["text"]}, ensure_ascii=False) + "\n")
    lens = sorted(len(u["text"]) for u in picked)
    print(json.dumps({"wrote": len(picked), "out": str(OUT),
                      "chars_min_med_max": [lens[0], lens[len(lens) // 2],
                                            lens[-1]],
                      "sources": len({u["src"] for u in picked})},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
