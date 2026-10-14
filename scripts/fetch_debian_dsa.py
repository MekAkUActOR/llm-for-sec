"""Debian DSA（Debian Security Advisory）→ C1 P1 描述层语料（docs/04 §1 P1）。

来源：lists.debian.org 的 debian-security-announce 邮件归档（MHonArc 逐页）。
  索引    https://lists.debian.org/debian-security-announce/          （年份链接）
  年度    https://lists.debian.org/debian-security-announce/{yyyy}/    （msg 链接）
  单篇    .../{yyyy}/msg{nnnnn}.html                                   （DSA 正文）

许可（Debian WWW Pages License, https://www.debian.org/license，逐字摘录见
manifest notes）：MIT (Expat) OR GPL-2+，2026-09-24 调研核验（docs/research/p1-sources.md §2.7）。

产物：
  data/corpora/raw/debian-dsa/{yyyy}/msg*.html     原始页（断点续抓）
  data/corpora/clean/c0_debian-dsa.jsonl           {"text": ...} 每行一篇
  manifest upsert：id=debian-dsa

设计（与 fetch_c0.py / fetch_zhwiki.py 一致）：
  - 转换器为纯函数（convert_dsa），可单测；
  - 禁用代理（ProxyHandler({})）、自定义 UA、指数退避、已存在文件跳过；
  - ensure_ascii=True 输出（pyarrow 兼容，docs/02 §0.1 #4）；
  - md5 去重、最短长度过滤由 fetch_c0.write_clean 完成。

用法：
  python scripts/fetch_debian_dsa.py [--skip-fetch] [--no-tokens] [--workers 4] [--years 2024,2023]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import CLEAN, count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "debian-dsa"
LIST_URL = "https://lists.debian.org/debian-security-announce/"
UA = "llm-for-sec-c1/0.1 (security corpus research pipeline; contact: local-researcher)"

SPEC = {
    "url": "https://lists.debian.org/debian-security-announce/",
    "license": "MIT-Expat OR GPL-2+ (Debian WWW Pages License)",
    "domain": "security",
    "lang": "en",
    "note": ("Debian WWW Pages License verbatim: \"Since 25 January 2012, the new "
             "material can be redistributed and/or modified under the terms of the "
             "MIT (Expat) License or, at your option, of the GNU General Public "
             "License; either version 2 of the License, or (at your option) any "
             "later version.\" DSA texts served via lists.debian.org (same Debian/SPI "
             "infrastructure as www.debian.org). P1 ingestion 2026-09-24 per "
             "docs/research/p1-sources.md."),
}

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_text(url: str, timeout: int = 30, retries: int = 4) -> str:
    """GET with no proxy + custom UA + exponential backoff."""
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


# ---------------------------------------------------------------- 转换器（纯函数） --
_DSA_ID = re.compile(r"DSA[- ](\d+)-(\d+)")
_PGP_SIG = re.compile(r"(?s)-{3,}BEGIN PGP SIGNATURE-{3,}.*$")
_PGP_HDR = re.compile(r"(?m)^-{3,}BEGIN PGP SIGNED MESSAGE-{3,}\s*$|^Hash: SHA[\d/]+\s*$")
_BODY_MARK = re.compile(r"(?s)<!--X-Body-of-Message-->(.*?)<!--X-Body-of-Message-End-->")
_H1 = re.compile(r"(?s)<h1>(.*?)</h1>")
_X_DATE = re.compile(r"<!--X-Date:\s*([^>]+?)\s*-->")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")


def _html_to_text(fragment: str) -> str:
    import html as _html
    text = _html.unescape(_TAG.sub(" ", fragment))
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def convert_dsa(html: str) -> str | None:
    """单篇 MHonArc 归档页 → DSA 描述层文本；非 DSA 邮件返回 None。

    保留：DSA 编号标题、日期、Package/CVE 元信息、漏洞描述、受影响发行版与
    修复版本、升级建议、tracker 链接；剔除：PGP 签名块、页面导航/表单。
    """
    h1 = _H1.search(html)
    subject = _html_to_text(h1.group(1)).strip() if h1 else ""
    if not subject:
        m = re.search(r"<!--X-Subject:\s*(.*?)\s*-->", html)
        subject = _html_to_text(m.group(1)).strip() if m else ""
    if not _DSA_ID.search(subject):
        return None  # 列表里的非 DSA 邮件（管理通知等）
    date_m = _X_DATE.search(html)
    date = _html_to_text(date_m.group(1)).strip() if date_m else ""
    body_m = _BODY_MARK.search(html)
    if body_m:
        body = _html_to_text(body_m.group(1))
    else:  # 兼容无标记的老页面：取全文，截到导航词之前
        body = _html_to_text(html)
        cut = body.find("Prev by Date")
        if cut > 0:
            body = body[:cut]
    body = _PGP_SIG.sub("", body)
    body = _PGP_HDR.sub("", body)
    body = "\n".join(ln for ln in (l.strip() for l in body.split("\n")) if ln)
    if len(body) < 80:
        return None
    head = f"Debian Security Advisory {subject}"
    if date:
        head += f" ({date})"
    return head + "\n" + body


def convert_year_pages(files: list[Path]) -> list[str]:
    out = []
    for p in files:
        t = convert_dsa(p.read_text(encoding="utf-8", errors="replace"))
        if t:
            out.append(t)
    return out


# ---------------------------------------------------------------- 抓取 --
def discover_years() -> list[str]:
    """lists.debian.org 索引页按"期"组织，但 /{yyyy}/ 年度直链可用（1998–2026，
    1997 归档不存在）。逐个探测，200 的保留。"""
    import urllib.error
    years = []
    for y in range(1998, date.today().year + 1):
        try:
            req = urllib.request.Request(f"{LIST_URL}{y}/", headers={"User-Agent": UA})
            with _OPENER.open(req, timeout=20) as r:
                if r.status == 200:
                    years.append(str(y))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        time.sleep(0.3)
    if len(years) < 20:
        raise RuntimeError(f"year discovery suspicious: {years}")
    return years


def list_year_msgs(year: str) -> list[str]:
    idx = http_text(f"{LIST_URL}{year}/")
    return sorted(set(re.findall(r'href="(msg\d+\.html)"', idx)))


def fetch_msg(year: str, msg: str) -> tuple[str, str, str]:
    """下载单篇到 raw/{year}/{msg}；返回 (year, msg, status)。"""
    dest = RAW / year / msg
    if dest.exists() and dest.stat().st_size > 0:  # 断点续抓
        return year, msg, "skip"
    try:
        html = http_text(f"{LIST_URL}{year}/{msg}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        return year, msg, "ok"
    except Exception as e:  # noqa: BLE001
        return year, msg, f"fail:{type(e).__name__}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Debian DSA ingestion (P1)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--years", default="", help="逗号分隔年份（调试用，默认全部）")
    args = ap.parse_args(argv)

    years = [y.strip() for y in args.years.split(",") if y.strip()] or \
        (discover_years() if not args.skip_fetch else
         sorted(p.name for p in RAW.iterdir() if p.is_dir()))
    print(f"debian-dsa: years={years[0]}..{years[-1]} ({len(years)})", flush=True)

    if not args.skip_fetch:
        jobs = []
        for y in years:
            msgs = list_year_msgs(y)
            print(f"  {y}: {len(msgs)} msgs", flush=True)
            jobs.extend((y, m) for m in msgs)
        print(f"total msg pages: {len(jobs)}", flush=True)
        done = fail = skip = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(fetch_msg, y, m) for y, m in jobs]
            for i, f in enumerate(as_completed(futs), 1):
                _, _, st = f.result()
                if st == "ok":
                    done += 1
                elif st == "skip":
                    skip += 1
                else:
                    fail += 1
                    if fail <= 10 or fail % 100 == 0:
                        print(f"    {st}", flush=True)
                if i % 500 == 0:
                    print(f"    ... {i}/{len(jobs)} (ok={done} skip={skip} fail={fail})",
                          flush=True)
        print(f"fetch done: ok={done} skip={skip} fail={fail}", flush=True)

    files = sorted(RAW.glob("*/msg*.html"))
    print(f"raw pages: {len(files)}", flush=True)
    texts = convert_year_pages(files)
    print(f"converted DSA texts: {len(texts)}", flush=True)
    p, n = write_clean("debian-dsa", texts)
    tokens = 0 if args.no_tokens else count_tokens(p)
    upsert_manifest("debian-dsa", SPEC, "ingested", n, tokens,
                    note=SPEC["note"] + f" Raw pages: {len(files)}, failures recorded in logs.")
    print(f"-> {p.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
