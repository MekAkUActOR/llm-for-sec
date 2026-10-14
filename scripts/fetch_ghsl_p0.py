"""GitHub Security Lab advisories + Project Zero 0days-in-the-wild → C1 P1 描述层。

源 A：ghsl-advisories
  索引  https://securitylab.github.com/advisories/          （单页全量，~1.9MB）
  单篇  https://securitylab.github.com/advisories/{slug}/    （HTML）
  许可  MIT —— github/securitylab 仓库 LICENSE.md（manifest notes 逐字摘录），
        2026-09-24 调研核验（docs/research/p1-sources.md §2.9）。
  红线  github/securitylab 的 SecurityExploits/ 目录（武器化倾向的深度利用
        研究）不在本源采集范围 —— 仅采集官方 advisories 页。

源 B：p0-0days
  仓库  https://github.com/googleprojectzero/0days-in-the-wild（git clone）
  语料  0day-RCAs/**/*.md —— P0 团队在野 0day 根因分析 writeup（排除 template.md）
  许可  Apache-2.0（仓库 LICENSE，manifest notes 记录）。
  限制  0day 追踪总表托管在 Google Sheets（docs.google.com），本网络阻断，
        不可采集（如实记录）。

产物：
  data/corpora/raw/ghsl/{slug}.html                     原始页（断点续抓）
  data/corpora/raw/p0-0days/                            git 仓库（clone/pull）
  data/corpora/clean/c0_ghsl-advisories.jsonl
  data/corpora/clean/c0_p0-0days.jsonl
  manifest upsert：id=ghsl-advisories / p0-0days

设计（与 fetch_c0.py 一致）：禁代理、自定义 UA、指数退避、文件级断点续抓、
ensure_ascii=True、md5 去重、最短长度过滤。

用法：
  python scripts/fetch_ghsl_p0.py [--skip-fetch] [--no-tokens] [--workers 4] [--only ghsl|p0]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw"
GHSL_RAW = RAW / "ghsl"
P0_DIR = RAW / "p0-0days"
SITE = "https://securitylab.github.com"
UA = "llm-for-sec-c1/0.1 (security corpus research pipeline; contact: local-researcher)"

GHSL_SPEC = {
    "url": "https://securitylab.github.com/advisories/",
    "license": "MIT (github/securitylab)",
    "domain": "security",
    "lang": "en",
    "note": ("MIT License, github/securitylab repo LICENSE.md verbatim: "
             "\"Permission is hereby granted, free of charge, to any person obtaining "
             "a copy of this software and associated documentation files (the "
             "\\\"Software\\\"), to deal in the Software without restriction, including "
             "without limitation the rights to use, copy, modify, merge, publish, "
             "distribute, sublicense, and/or sell copies of the Software...\" "
             "Scope: official GHSL advisory pages only; SecurityExploits/ deferred per "
             "uplift policy (docs/04 §0)."),
}
P0_SPEC = {
    "url": "https://github.com/googleprojectzero/0days-in-the-wild",
    "license": "Apache-2.0",
    "domain": "security",
    "lang": "en",
    "note": ("Apache License 2.0 (repo LICENSE). Corpus = 0day-RCAs/ root cause "
             "analyses (git clone). The 0-day tracking sheet itself is hosted on "
             "docs.google.com (blocked from this network) and was not collected."),
}

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_text(url: str, timeout: int = 30, retries: int = 4) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with _OPENER.open(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"GET failed after {retries} tries: {url}: {last}")


# ---------------------------------------------------------------- GHSL 转换器 --
_H1 = re.compile(r"(?s)<h1[^>]*>(.*?)</h1>")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")


def _strip_tags(fragment: str) -> str:
    import html as _html
    return _html.unescape(_TAG.sub(" ", fragment))


def _html_to_text(html_text: str) -> str:
    import html as _html
    html_text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    html_text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", html_text)
    text = _html.unescape(_TAG.sub(" ", html_text))
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def convert_ghsl(html: str) -> str | None:
    """单篇 GHSL advisory 页 → 描述层文本；非 advisory 页返回 None。

    正文取自 <main> 容器（唯一 h1 所在，避开 head/og:title 与站点导航）；
    保留：GHSL 编号标题、披露日期、Summary/Details/Impact/时间线/Credit 正文；
    剔除：站点导航、页脚（Product/Features/... GitHub Inc.）。
    """
    h1 = _H1.search(html)
    title = " ".join(_strip_tags(h1.group(1)).split()) if h1 else ""
    if not title.startswith("GHSL-"):
        return None
    main_m = re.search(r"(?s)<main[^>]*>(.*?)</main>", html)
    pre_main = html[:main_m.start()] if main_m else html
    dates = re.findall(r"[A-Z][a-z]+ \d{1,2}, \d{4}", pre_main)
    date = dates[-1] if dates else ""
    main_m = re.search(r"(?s)<main[^>]*>(.*?)</main>", html)
    if main_m:
        text = _html_to_text(main_m.group(1))  # 正文容器：Summary 起的章节内容
    else:  # 兼容无 <main> 的页面：从标题行起截
        text = _html_to_text(html)
        i = text.find(title)
        if i < 0:
            return None
        text = text[i:]
    body = text
    for marker in ("Product\nFeatures\nSecurity", "GitHub Inc. ©", "GitHub Inc. (c)"):
        j = body.find(marker)
        if j > 0:
            body = body[:j]
    body = body.strip()
    if len(body) < 120:
        return None
    head = f"GitHub Security Lab advisory {title}"
    if date:
        head += f" ({date})"
    return head + "\n" + body


def parse_index(html: str) -> list[str]:
    """advisories 索引页 → 去重 slug 列表（保持出现序）。"""
    seen, out = set(), []
    for m in re.finditer(r'href="(/advisories/[^"#?]+/)"', html):
        slug = m.group(1).strip("/").split("/")[-1]
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


# ---------------------------------------------------------------- P0 转换器 --
_FRONTMATTER = re.compile(r"(?s)\A---\s*\n.*?\n---\s*\n")
_HTML_COMMENT = re.compile(r"(?s)<!--.*?-->")


def convert_rca(md_text: str) -> str | None:
    """0day RCA markdown → 文本：剥离 YAML frontmatter 与 HTML 注释，保留正文。"""
    t = _FRONTMATTER.sub("", md_text)
    t = _HTML_COMMENT.sub("", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) < 200 or t.startswith("# 0-day Root Cause Analysis Template"):
        return None
    return "Google Project Zero 0-day root cause analysis.\n" + t


def _git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    # git 进度走 stderr，重定向避免 PowerShell NativeCommandError 误报
    return subprocess.run(["git"] + args, capture_output=True, text=True,
                          timeout=300, check=check)


def ensure_p0_repo(skip_fetch: bool) -> None:
    if (P0_DIR / ".git").exists():
        if not skip_fetch:
            try:
                _git(["-C", str(P0_DIR), "pull", "--ff-only"], check=False)
            except Exception as e:  # noqa: BLE001
                print(f"  p0 pull skipped: {e}", flush=True)
        return
    if skip_fetch:
        raise RuntimeError("p0-0days repo missing and --skip-fetch given")
    P0_DIR.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):  # github.com 间歇抖动：指数退避重试
        try:
            _git(["clone", "--depth", "1",
                  "https://github.com/googleprojectzero/0days-in-the-wild.git",
                  str(P0_DIR)])
            return
        except Exception as e:  # noqa: BLE001
            print(f"  clone attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("git clone failed after 5 attempts")


# ---------------------------------------------------------------- 主流程 --
def run_ghsl(skip_fetch: bool, no_tokens: bool, workers: int):
    idx_path = GHSL_RAW / "_index.html"
    if not skip_fetch or not idx_path.exists():
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        idx_path.write_text(http_text(GHSL_SPEC["url"]), encoding="utf-8")
    slugs = parse_index(idx_path.read_text(encoding="utf-8"))
    print(f"ghsl: {len(slugs)} advisory slugs", flush=True)

    if not skip_fetch:
        def grab(slug):
            dest = GHSL_RAW / f"{slug}.html"
            if dest.exists() and dest.stat().st_size > 0:
                return "skip"
            try:
                dest.write_text(http_text(f"{SITE}/advisories/{slug}/"), encoding="utf-8")
                return "ok"
            except Exception as e:  # noqa: BLE001
                return f"fail:{type(e).__name__}"
        stat = {"ok": 0, "skip": 0, "fail": 0}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for i, r in enumerate(ex.map(grab, slugs), 1):
                stat[r.split(":")[0]] += 1
                if i % 200 == 0:
                    print(f"    ... {i}/{len(slugs)} {stat}", flush=True)
        print(f"ghsl fetch: {stat}", flush=True)

    texts = []
    for p in sorted(GHSL_RAW.glob("*.html")):
        if p.name == "_index.html":
            continue
        t = convert_ghsl(p.read_text(encoding="utf-8", errors="replace"))
        if t:
            texts.append(t)
    print(f"ghsl converted: {len(texts)}", flush=True)
    out, n = write_clean("ghsl-advisories", texts)
    tokens = 0 if no_tokens else count_tokens(out)
    upsert_manifest("ghsl-advisories", GHSL_SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)


def run_p0(skip_fetch: bool, no_tokens: bool):
    ensure_p0_repo(skip_fetch)
    texts = []
    for p in sorted((P0_DIR / "0day-RCAs").rglob("*.md")):
        t = convert_rca(p.read_text(encoding="utf-8", errors="replace"))
        if t:
            texts.append(t)
    print(f"p0-0days converted RCA writeups: {len(texts)}", flush=True)
    out, n = write_clean("p0-0days", texts)
    tokens = 0 if no_tokens else count_tokens(out)
    upsert_manifest("p0-0days", P0_SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="GHSL advisories + P0 0days ingestion (P1)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", choices=["ghsl", "p0"], default="")
    args = ap.parse_args(argv)
    if args.only in ("", "ghsl"):
        run_ghsl(args.skip_fetch, args.no_tokens, args.workers)
    if args.only in ("", "p0"):
        run_p0(args.skip_fetch, args.no_tokens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
