"""GDPR 全文（EUR-Lex 官方文本）→ C2 隐私知识语料（docs/04 C2 小节）。

来源：https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679
（Regulation (EU) 2016/679 官方 HTML；809KB）。C0 时代的"EUR-Lex 对脚本返回
空体"实测只拦 Python urllib——curl.exe（schannel）全通（2026-09-26 验证）。

许可：EU Open Data Licence（CC-BY-4.0）——EUR-Lex 页脚 "The Commission's
re-use of documents is governed by Commission Decision 2011/833/EU";法规文本
本身以 CC-BY-4.0 提供（EUR-Lex legal notice）。

文档粒度：每条 Article 一 doc（"GDPR Article N — 标题: 正文"），序言
(Recitals) 合并为单 doc——全文无遗漏,粒度利于训练混配。

产物：data/corpora/raw/c2-privacy/gdpr_eurlex.html（断点续抓）
      data/corpora/clean/c2_privacy_gdpr_full.jsonl
manifest：id=gdpr-full

用法：python scripts/fetch_gdpr_full.py [--skip-fetch] [--no-tokens]
"""
from __future__ import annotations

import argparse
import html as _html
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "c2-privacy" / "gdpr_eurlex.html"
URL = ("https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679")
UA = "llm-for-sec-c2-privacy/0.1 (privacy corpus research pipeline)"

SPEC = {
    "url": URL,
    "license": "EU Open Data Licence / CC-BY-4.0 (EUR-Lex legal notice)",
    "domain": "privacy",
    "lang": "en",
    "note": ("EUR-Lex legal notice: official texts of EU law are made "
             "available for re-use under the EU Open Data Licence "
             "(Commission Decision 2011/833/EU), which corresponds to "
             "CC-BY-4.0 attribution. Full text of Regulation (EU) 2016/679 "
             "(GDPR): 173 recitals + 99 articles, one document per article "
             "plus one combined recitals document. Fetched via curl.exe "
             "(schannel): EUR-Lex returns empty bodies to Python urllib on "
             "this network."),
    "files": ["data/corpora/clean/c2_privacy_gdpr_full.jsonl"],
}

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")


def curl_get(url: str, timeout: int = 240, retries: int = 4) -> bytes:
    last = b""
    for attempt in range(retries):
        try:
            p = subprocess.run(
                ["curl.exe", "-sSL", "--noproxy", "*", "--max-time", str(timeout),
                 "-A", UA, "-w", "\n__M__%{http_code}|%{size_download}", url],
                capture_output=True, timeout=timeout + 30)
            m = re.search(rb"__M__(\d+)\|(\d+)\s*$", p.stdout)
            if not m:
                raise RuntimeError(f"curl no meta: {p.stderr[:120]!r}")
            status = int(m.group(1))
            if status == 200:
                return p.stdout[: p.stdout.rfind(b"\n__M__")]
            last = f"http {status}".encode()
        except Exception as e:  # noqa: BLE001
            last = str(e).encode()
        time.sleep(2 ** attempt)
    raise RuntimeError(f"curl failed after {retries} tries: {last[:150]!r}")


def _html_to_text(html_text: str) -> str:
    html_text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    html_text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr|/td)[^>]*>", "\n",
                       html_text)
    text = _html.unescape(_TAG.sub(" ", html_text))
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


# ---------------------------------------------------------------- 转换器（纯函数） --
_ART_P = re.compile(r'(?s)<p[^>]*class="oj-ti-art"[^>]*>\s*Article\s*(\d+)\s*</p>'
                    r'\s*(?:<div[^>]*>\s*<p[^>]*class="oj-sti-art"[^>]*>(.*?)</p>)?')


def convert_gdpr(html: str) -> list[str]:
    """GDPR EUR-Lex HTML → docs 列表。

    每条 Article 一 doc（正文含条款列表/子项）；序言区（Article 1 之前的
    Recitals）合并为一个 doc；返回空列表表示无 Article（壳页/拦截页）。
    """
    m0 = _ART_P.search(html)
    if not m0:
        return []
    head_zone = html[: m0.start()]          # 序言（recitals + 标题区）
    art_spans: list[tuple[str, str, str]] = []
    for m in _ART_P.finditer(html):
        nm = _ART_P.search(html, m.end())
        seg = html[m.end(): nm.start() if nm else len(html)]
        art_spans.append((m.group(1), m.group(2) or "", seg))

    docs: list[str] = []
    # 序言 doc
    pre = _html_to_text(head_zone)
    # 剔 EUR-Lex 导航壳:保留从 Regulation 标题/序言第一条开始的部分
    i = re.search(r"(Regulation \(EU\) (?:No )?2016/679|Having regard to the Treaty|"
                  r"The European Parliament and the Council of the European Union)",
                  pre)
    if i:
        pre = pre[i.start():]
    pre = re.sub(r"\n{3,}", "\n\n", pre).strip()
    if len(pre) > 200:
        docs.append("EU General Data Protection Regulation (GDPR) "
                    "Regulation (EU) 2016/679 — Preamble and Recitals.\n" + pre)

    for num, title, seg in art_spans:
        title = " ".join(_html_to_text(title).split())
        body = _html_to_text(seg)
        # 条文尾部剔除:下一阶段导航/页脚标记
        for cutmk in ("OJ L, 04/05/2016", "Entry into force", "Done at "):
            j = body.find(cutmk)
            if j > 200:
                body = body[:j]
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if not body:
            continue
        head = f"EU General Data Protection Regulation (GDPR) Article {num}"
        if title:
            head += f" — {title}"
        docs.append(head + "\n" + body)
    return docs


def main(argv=None):
    ap = argparse.ArgumentParser(description="GDPR full text ingestion (C2)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    args = ap.parse_args(argv)

    if not args.skip_fetch and not (RAW.exists() and RAW.stat().st_size > 100000):
        RAW.parent.mkdir(parents=True, exist_ok=True)
        RAW.write_bytes(curl_get(URL))
        print(f"gdpr html: {RAW.stat().st_size}B", flush=True)
    html_text = RAW.read_text(encoding="utf-8", errors="replace")
    docs = convert_gdpr(html_text)
    print(f"gdpr docs: {len(docs)} (1 recitals + {len(docs)-1} articles)",
          flush=True)
    if not docs:
        raise SystemExit("no articles parsed — likely a shell/challenge page")
    out, n = write_clean("c2_privacy_gdpr_full", docs)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("gdpr-full", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
