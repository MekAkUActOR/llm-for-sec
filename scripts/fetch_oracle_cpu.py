"""Oracle CPU / Security Alerts → C1 P1 描述层语料（docs/04 §1 P1）。

来源：oracle.com/security-alerts（主索引 + cpuarchive/alertsarchive/
solarisbulletinsarchive 三个归档页枚举全部通告，约 140 篇）。
  主索引  https://www.oracle.com/security-alerts/
  归档    .../cpuarchive.html（2007–2020 季度 CPU + javacpu/cspu 变体）
          .../alertsarchive.html（独立 CVE alert 2010–2020）
          .../solarisbulletinsarchive.html（Solaris Third Party Bulletin 2021–2026）

许可：Oracle Web Sites Terms of Use（https://www.oracle.com/legal/terms/，样本
docs/research/_oracle_terms_sample.html）——"All rights, title and interest not
expressly granted ... are reserved."；2026-09-24 项目决策纳入 C1（docs/04 D3
风险注记），manifest notes 逐字摘录。

网络事实（2026-09-24 调研，docs/research/p1-sources.md §2.3）：oracle.com 对
Python urllib/OpenSSL TLS 握手超时，curl.exe（schannel）0.5–4s 稳定 → 本脚本
全程 curl.exe 子进程。

产物：
  data/corpora/raw/oracle-cpu/*.html               原始页（断点续抓）
  data/corpora/clean/c0_oracle-cpu.jsonl
  manifest upsert：id=oracle-cpu

用法：
  python scripts/fetch_oracle_cpu.py [--skip-fetch] [--no-tokens] [--workers 3]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "oracle-cpu"
BASE = "https://www.oracle.com/security-alerts/"
UA = "llm-for-sec-c1/0.1 (security corpus research pipeline; contact: local-researcher)"

SPEC = {
    "url": "https://www.oracle.com/security-alerts/",
    "license": "Oracle Web Sites Terms of Use (all rights reserved; project decision 2026-09-24, docs/04 D3)",
    "domain": "security",
    "lang": "en",
    "note": ("Oracle Web Sites Terms of Use verbatim: \"The Site and Content provided "
             "on or through the Site are the intellectual property and copyrighted "
             "works of Oracle or a third party provider. All rights, title and "
             "interest not expressly granted with respect to the Site and Content "
             "provided on or through the Site are reserved.\" Ingested per project "
             "decision (C1, D3 risk note in docs/04). Fetch via curl.exe (schannel): "
             "oracle.com resets TLS handshakes from Python/OpenSSL on this network "
             "(docs/research/p1-sources.md §2.3)."),
}

# 只采通告页；排除导航/映射/订阅类页面（按文件名）
_EXCLUDE = {
    "securityemail.html", "public-vuln-to-advisory-mapping.html",
    "public-vuln-to-bulletin-mapping.html", "sunalertslisting.html",
    "alertsarchive.html", "cpuarchive.html", "solarisbulletinsarchive.html",
    "all-oracle-cves-outside-other-oracle-public-documents.html",
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


def extract_links(html: str) -> list[str]:
    out = []
    for m in re.finditer(r'href="(/security-alerts/[^"#?]+\.html)"', html):
        name = m.group(1).rsplit("/", 1)[-1]
        if name not in _EXCLUDE and not name.startswith("index"):
            out.append(name)
    return sorted(set(out))


# ---------------------------------------------------------------- 转换器（纯函数） --
_TITLE = re.compile(r"(?s)<title>(.*?)</title>")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")


def _html_to_text(html_text: str) -> str:
    import html as _html
    html_text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    html_text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", html_text)
    text = _html.unescape(_TAG.sub(" ", html_text))
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def convert_oracle(html: str) -> str | None:
    """单篇 Oracle 通告页 → 描述层文本。

    保留：标题、Description、风险矩阵（逐行文本化）、Patch Availability、
    References；剔除：站点导航（QUICK LINKS 菜单）、页脚（Copyright/Legal）。
    """
    tm = _TITLE.search(html)
    title = " ".join(_html_to_text(tm.group(1)).split()) if tm else ""
    if not title:
        return None
    text = _html_to_text(html)
    first = text.find(title)
    start = text.find(title, first + 1) if first >= 0 else -1
    if start < 0:
        start = first if first >= 0 else 0
    body = text[start:]
    # 页脚截断：所有候选标记中最早出现（>300 字符后）的位置
    cuts = [body.find(mk) for mk in
            ("Copyright ©", "Copyright (c)", "© Oracle", "© 20",
             "Legal Notices and Terms", "Site Map |", "Do Not Sell My Info")]
    cuts = [j for j in cuts if j > 300]
    if cuts:
        body = body[:min(cuts)]
    body = body.strip()
    if len(body) < 300:  # 薄页（跳转壳/空壳）剔除
        return None
    return f"Oracle security advisory: {title}\n{body}"


# ---------------------------------------------------------------- 主流程 --
def fetch_page(name: str) -> str:
    dest = RAW / name
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    status, body = curl_get(BASE + name)
    if status != 200:
        return f"fail:{status}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    time.sleep(0.3)
    return "ok"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Oracle CPU ingestion (P1)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args(argv)

    idx_names = ["", "cpuarchive.html", "alertsarchive.html",
                 "solarisbulletinsarchive.html"]
    pages: set[str] = set()
    if not args.skip_fetch:
        for n in idx_names:
            st, body = curl_get(BASE + n)
            if st != 200:
                raise RuntimeError(f"index fetch failed: {BASE + n} -> {st}")
            found = extract_links(body.decode("utf-8", "replace"))
            print(f"  index '{n or 'main'}': {len(found)} advisory links", flush=True)
            pages.update(found)
            time.sleep(0.5)
        print(f"unique advisory pages: {len(pages)}", flush=True)
        RAW.mkdir(parents=True, exist_ok=True)
        stat = {"ok": 0, "skip": 0, "fail": 0}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(fetch_page, sorted(pages)):
                stat[r.split(":")[0]] += 1
                if r.startswith("fail"):
                    print(f"    {r}", flush=True)
        print(f"oracle fetch: {stat}", flush=True)
    else:
        pages = {p.name for p in RAW.glob("*.html")}

    files = sorted(RAW.glob("*.html"))
    texts = []
    for p in files:
        t = convert_oracle(p.read_text(encoding="utf-8", errors="replace"))
        if t:
            texts.append(t)
    print(f"converted: {len(texts)}/{len(files)}", flush=True)
    out, n = write_clean("oracle-cpu", texts)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("oracle-cpu", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
