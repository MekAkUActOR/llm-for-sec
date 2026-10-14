"""SANS Internet Storm Center 日记 → C1 P1 描述层语料（docs/04 §1 P1）。

来源与通路（2026-09-24 调研实测，docs/research/p1-sources.md §2.6）：
  归档  https://isc.sans.edu/diaryarchive.html?year={Y}&month={M}
        （每卡片含 "Published: YYYY-MM-DD" + ../diary/{slug}/{id}/ 链接；
        无效年月会回退到"近期日记"页 → 用日期前缀校验过滤）
  正文  https://isc.sans.edu/diary/{id}
        （custom UA 必须——默认 UA 被拒；Python urllib TLS 在本网络握手失败，
        全程 curl.exe 子进程，同 Oracle 通路）
  规模  2001–2026 约 6–9k 篇（每月 20–30 篇）

许可：CC BY-NC-SA 4.0（页面页脚 "the data is provided using a
Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)
License."）；2026-09-24 项目决策纳入 C1（docs/04 D3 风险注记）。

产物：
  data/corpora/raw/sans-isc/{id}.html          原始页（断点续抓）
  data/corpora/clean/c0_sans-isc.jsonl
  manifest upsert：id=sans-isc

用法：
  python scripts/fetch_sans_isc.py [--skip-fetch] [--no-tokens] [--workers 4]
"""
from __future__ import annotations

import argparse
import html as _html
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "sans-isc"
BASE = "https://isc.sans.edu"
UA = "llm-for-sec-c1/0.1 (security corpus research pipeline; contact: local-researcher)"

SPEC = {
    "url": "https://isc.sans.edu/diaryarchive.html",
    "license": "CC BY-NC-SA 4.0 (project decision 2026-09-24, docs/04 D3)",
    "domain": "security",
    "lang": "en",
    "note": ("SANS ISC footer verbatim: \"the data is provided using a "
             "Attribution-NonCommercial-ShareAlike 4.0 International "
             "(CC BY-NC-SA 4.0) License.\" Ingested per project decision "
             "(C1, D3 risk note in docs/04). Python urllib TLS handshake fails "
             "against isc.sans.edu on this network; fetched via curl.exe "
             "(schannel) with custom UA (default UAs blocked)."),
}


def curl_get(url: str, timeout: int = 60, retries: int = 5) -> tuple[int, bytes]:
    """curl.exe（schannel）GET；状态 0（连接失败）指数退避重试。"""
    last = b""
    for attempt in range(retries):
        try:
            p = subprocess.run(
                ["curl.exe", "-sSL", "--noproxy", "*", "--max-time", str(timeout),
                 "-A", UA, "-w", "\n__M__%{http_code}|%{size_download}", url],
                capture_output=True, timeout=timeout + 15)
            m = re.search(rb"__M__(\d+)\|(\d+)\s*$", p.stdout)
            if not m:
                raise RuntimeError(f"curl no meta: {p.stderr[:120]!r}")
            status = int(m.group(1))
            if status != 0:
                return status, p.stdout[: p.stdout.rfind(b"\n__M__")]
            last = p.stderr
        except Exception as e:  # noqa: BLE001
            last = str(e).encode()
        time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"curl failed after {retries} tries: {url}: {last[:150]!r}")


# ---------------------------------------------------------------- 转换器（纯函数） --
_TITLE = re.compile(r"(?s)<title>(.*?)</title>")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_CARD = re.compile(
    r'(?s)Published:\s*(\d{4}-\d{2}-\d{2}).{0,300}?'
    r'<h2 class="card-title">\s*<a href="[^"]*/diary/[^/"]+/(\d+)/[^"]*">(.*?)</a>')


def parse_archive_cards(html: str, year: int, month: int) -> list[dict]:
    """解析归档月页卡片。

    每卡片：published/slug-id/标题。只保留 published 前缀 == 请求年月的条目
    （无效年月参数会回退到"近期日记"页，其日期与请求不符，天然被滤除）。
    """
    out = []
    for m in _CARD.finditer(html):
        date, did, title = m.group(1), m.group(2), m.group(3)
        prefix = f"{year:04d}-{month:02d}"
        if not date.startswith(prefix):
            continue
        title = _html.unescape(_TAG.sub(" ", title))
        out.append({"id": did, "date": date, "title": " ".join(title.split())})
    # 同 id 可能跨卡片重复
    seen, uniq = set(), []
    for r in out:
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)
    return uniq


def _html_to_text(html_text: str) -> str:
    html_text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    html_text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr|/pre)[^>]*>", "\n",
                       html_text)
    text = _html.unescape(_TAG.sub(" ", html_text))
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def convert_sans_diary(html: str, date_hint: str = "") -> str | None:
    """单篇 SANS diary 页 → 描述层文本。

    保留：标题、发布日期/作者（diaryheader）、正文（diarybody）、关键词
    （diarykeywords div 首行）；剔除：站点导航、评论区、课程广告、分页。
    2010–2015 年部分短日记无 diarybody（"oneliner" 模板）→ 取
    class="oneliner" div 为正文，日期用归档缓存 date_hint。
    """
    tm = _TITLE.search(html)
    title = " ".join(_html_to_text(tm.group(1)).split()).replace(" - SANS ISC", "") \
        if tm else ""
    if not title:
        return None

    ib = html.find('class="diarybody"')
    if ib < 0:
        # 老模板:oneliner 短日记
        io_ = html.find('class="oneliner"')
        if io_ < 0:
            return None
        s = html.find(">", io_) + 1
        e = html.find("</div>", s)
        body = _html_to_text(html[s:e if e > 0 else len(html)]).strip()
        if not body:
            return None
        lines = [f"SANS Internet Storm Center diary: {title}"]
        if date_hint:
            lines.append(f"Published {date_hint}")
        text = "\n".join(lines) + "\n" + body
        return text if len(text) >= 100 else None
    ib = html.find(">", ib) + 1  # 跳过容器开标签（find 定位在属性中段）

    ih = html.find('class="diaryheader"')
    ih = html.find(">", ih) + 1 if ih >= 0 else 0
    header = html[ih:ib] if ih < ib else ""

    ik = html.find('class="diarykeywords"')
    end = html.rfind("<", 0, ik) if ik > ib else len(html)  # 截在开标签的 "<" 前
    if end < ib:
        end = len(html)
    body_html = html[ib:end]
    # 无 keywords 时的后备截断：课程广告 / 分页 / 评论区
    for tail_marker in ('class="teachingschedule"', 'class="diaryPagination"',
                        'class="ico-comments"', "id=\"comments\""):
        j = body_html.find(tail_marker)
        if j > 0:
            j = body_html.rfind("<", 0, j)
            body_html = body_html[:j if j > 0 else len(body_html)]

    htext = _html_to_text(header)
    mdate = re.search(r"(\d{4}-\d{2}-\d{2})", htext)
    mauth = re.search(r"by\s+(.+?)\s+\(Version", htext)
    meta = []
    if mdate:
        meta.append(f"Published {mdate.group(1)}")
    if mauth:
        meta.append(f"by {' '.join(mauth.group(1).split())}")

    body = _html_to_text(body_html)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not body:
        return None

    lines = [f"SANS Internet Storm Center diary: {title}"]
    if meta:
        lines.append(", ".join(meta))
    if ik > 0:
        kw_start = html.find(">", ik) + 1  # 跳过开标签（find 定位在属性中段）
        kw_block = html[kw_start:]
        kw_end = kw_block.find("</div>")
        kw_text = _html_to_text(kw_block[:kw_end if kw_end > 0 else len(kw_block)])
        kw_line = kw_text.split("\n")[0].strip()
        if kw_line.startswith("Keywords:"):
            lines.append(kw_line[:200])
    text = "\n".join(lines) + "\n" + body
    if len(text) < 120:
        return None
    return text


# ---------------------------------------------------------------- 抓取 --
def enumerate_archive(year_from: int = 2001, year_to: int = 2026) -> list[dict]:
    """按年月翻归档页；日期校验防"回退近期页"。"""
    out: dict[str, dict] = {}
    for y in range(year_from, year_to + 1):
        for m in range(1, 13):
            try:
                st, body = curl_get(f"{BASE}/diaryarchive.html?year={y}&month={m}")
                if st != 200:
                    continue
                cards = parse_archive_cards(
                    body.decode("utf-8", "replace"), y, m)
                for c in cards:
                    out.setdefault(c["id"], c)
            except Exception as e:  # noqa: BLE001
                print(f"    {y}-{m:02d}: FAIL {type(e).__name__}", flush=True)
            time.sleep(0.4)
        print(f"  archive {y}: cumulative {len(out)} diaries", flush=True)
    return list(out.values())


def fetch_one(rec: dict) -> str:
    did = rec["id"]
    dest = RAW / f"{did}.html"
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    try:
        st, body = curl_get(f"{BASE}/diary/{did}")
        if st != 200:
            return f"fail:{st}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        time.sleep(0.25)
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"fail:{type(e).__name__}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="SANS ISC diary ingestion (P1)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--reuse-archive", action="store_true",
                    help="复用 raw/_archive.json 缓存,跳过月度归档枚举")
    ap.add_argument("--no-tokens", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--year-from", type=int, default=2001)
    ap.add_argument("--year-to", type=int, default=2026)
    args = ap.parse_args(argv)

    if not args.skip_fetch:
        cache = RAW / "_archive.json"
        if args.reuse_archive and cache.exists():
            recs = __import__("json").loads(cache.read_text(encoding="utf-8"))
            print(f"sans-isc: reuse cached archive: {len(recs)} diaries", flush=True)
        else:
            recs = enumerate_archive(args.year_from, args.year_to)
            print(f"sans-isc: {len(recs)} diaries", flush=True)
        RAW.mkdir(parents=True, exist_ok=True)
        (RAW / "_archive.json").write_text(
            __import__("json").dumps(recs, indent=0), encoding="utf-8")
        stat = {"ok": 0, "skip": 0, "fail": 0}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for i, r in enumerate(ex.map(fetch_one, recs), 1):
                stat[r.split(":")[0]] += 1
                if r.startswith("fail") and stat["fail"] <= 20:
                    print(f"    {r}", flush=True)
                if i % 500 == 0:
                    print(f"    ... {i}/{len(recs)} {stat}", flush=True)
        print(f"sans fetch: {stat}", flush=True)

    files = sorted(RAW.glob("*.html"), key=lambda p: int(p.stem))
    print(f"raw diary pages: {len(files)}", flush=True)
    arch = {}
    cache = RAW / "_archive.json"
    if cache.exists():
        arch = {r["id"]: r.get("date", "")
                for r in __import__("json").loads(cache.read_text(encoding="utf-8"))}
    texts = []
    for p in files:
        try:
            html = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:  # 瞬时文件锁(AV 扫描/句柄未释放)→跳过该篇
            print(f"    read fail {p.name}: {e}", flush=True)
            continue
        t = convert_sans_diary(html, date_hint=arch.get(p.stem, ""))
        if t:
            texts.append(t)
    print(f"converted: {len(texts)}/{len(files)}", flush=True)
    out, n = write_clean("sans-isc", texts)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("sans-isc", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
