"""中国四部网安/数据/保密法律全文 → C2 隐私知识语料（docs/04 C2 小节）。

来源（2026-09-26 全文性逐一验证：末条在文、条数齐）：
  PIPL 个人信息保护法   https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm （网信办转载,74 条全）
  CSL  网络安全法(2025 修订) https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm （网信办转载,全文）
  DSL  数据安全法       http://www.npc.gov.cn/c2/c30834/202106/t20210610_311888.html （人大网,55 条全）
  保密法(2024 修订)      https://www.huizhou.jcy.gov.cn/zywj/202402/t20240228_7123932.shtml （惠州检察院转载,65 条全;npc/gov.cn 旧链已 404,flk.npc.gov.cn 为纯 SPA）

许可：法条本身不受著作权保护（《著作权法》第五条第(一)项——"法律、法规,
国家机关的决议、决定……及其官方正式译文"不适用本法）;来源页为政府网站
公开转载。C0 的 cn-laws 源为节选级（3 docs/14.8k tok）,本源为全文级。

网络注记：gov 系站点对本网络存在 TLS 拦截（docs/04 C0 实况）,统一走
curl.exe/schannel + 关键词完整性校验（首条+末条在场）。

产物：data/corpora/raw/c2-privacy/cn_laws/{law}.html（断点续抓）
      data/corpora/clean/c2_privacy_cn_laws_full.jsonl（每法一 doc）
manifest：id=cn-laws-full

用法：python scripts/fetch_cn_laws_full.py [--skip-fetch] [--no-tokens]
"""
from __future__ import annotations

import argparse
import html as _html
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "c2-privacy" / "cn_laws"
UA = "llm-for-sec-c2-privacy/0.1 (privacy corpus research pipeline)"

LAWS = {
    "PIPL-个人信息保护法": {
        "url": "https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm",
        "title": "中华人民共和国个人信息保护法",
        "first": "为了保护个人信息权益，规范个人信息处理活动",
        "last_art": "第七十四条",
    },
    "CSL-网络安全法2025": {
        "url": "https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm",
        "title": "中华人民共和国网络安全法（2025 年修正）",
        "first": "为了保障网络安全，维护网络空间主权",
        "last_art": "第七十九条",
    },
    "DSL-数据安全法": {
        "url": "http://www.npc.gov.cn/c2/c30834/202106/t20210610_311888.html",
        "title": "中华人民共和国数据安全法",
        "first": "为了规范数据处理活动，保障数据安全",
        "last_art": "第五十五条",
    },
    "SecrecyLaw-保密法2024": {
        "url": "https://www.huizhou.jcy.gov.cn/zywj/202402/t20240228_7123932.shtml",
        "title": "中华人民共和国保守国家秘密法（2024 年修订）",
        "first": "为了保守国家秘密，维护国家安全和利益",
        "last_art": "第六十五条",
    },
}

SPEC = {
    "url": "https://www.cac.gov.cn/ , npc.gov.cn , huizhou.jcy.gov.cn (official re-publications)",
    "license": ("Statutory texts - not subject to copyright (PRC Copyright Law "
                "Art. 5(1): laws and regulations are excluded from protection)"),
    "domain": "privacy",
    "lang": "zh",
    "note": ("《著作权法》第五条第(一)项：法律、法规不适用该法（法条文本本身"
             "不受著作权保护）。来源为政府网站公开转载：PIPL/CSL-2025 网信办"
             "（cac.gov.cn）、DSL 人大网（npc.gov.cn）、保密法 2024 惠州市检察院"
             "转载页（npc.gov.cn/gov.cn 旧链 2026-09-26 已 404，flk.npc.gov.cn 为"
             "纯 SPA 无法脚本取文）。每法单 doc 全文，末条在场完整性校验。"
             "gov 系站点本网络 TLS 拦截 → curl.exe/schannel 通道。"),
    "files": ["data/corpora/clean/c2_privacy_cn_laws_full.jsonl"],
}

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t　]+")


def curl_get(url: str, timeout: int = 120, retries: int = 4) -> bytes:
    import subprocess
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
    raise RuntimeError(f"curl failed after {retries} tries: {url}: {last[:150]!r}")


# ---------------------------------------------------------------- 转换器（纯函数） --
def _html_to_text(html_text: str) -> str:
    html_text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    html_text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr|/td)[^>]*>", "\n",
                       html_text)
    text = _html.unescape(_TAG.sub(" ", html_text))
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


_ART_ZH = re.compile(r"第[一二三四五六七八九十百]+条")


def convert_law(html: str, meta: dict) -> str | None:
    """单法页 → 全文 doc。完整性校验:首条关键词与末条号在场,否则 None。"""
    text = _html_to_text(html)
    # 从"第一条"所在段截到末条之后（剔站点导航/相关链接尾部）
    i = text.find("第一条")
    if i < 0:
        return None
    last = meta["last_art"]
    j = text.rfind(last)
    if j < 0:  # 末条不在文 → 节选/壳页
        return None
    # 末条段落结束:其后的下一个"附件/来源/分享"类词或文末
    tail_zone = text[j + len(last):]
    m = re.search(r"(附件[：:]|来源[：:]|分享[：:]|【相关链接】|扫描二维码|打印本页)",
                  tail_zone)
    end = j + len(last) + (m.start() if m else min(len(tail_zone), 20000))
    body = text[i:end].strip()
    if meta["first"] not in body[:600]:
        return None
    arts = set(_ART_ZH.findall(body))
    if len(arts) < 20:  # 完整法应几十条起
        return None
    head = f"{meta['title']}（全文）"
    return head + "\n" + re.sub(r"\n{3,}", "\n\n", body)


def main(argv=None):
    ap = argparse.ArgumentParser(description="CN laws full text ingestion (C2)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    args = ap.parse_args(argv)

    RAW.mkdir(parents=True, exist_ok=True)
    docs, failed = [], []
    for name, meta in LAWS.items():
        p = RAW / f"{name}.html"
        if not (p.exists() and p.stat().st_size > 10000):
            if args.skip_fetch:
                failed.append(f"{name}: no cached page")
                continue
            p.write_bytes(curl_get(meta["url"]))
            time.sleep(1.0)
        t = convert_law(p.read_text(encoding="utf-8", errors="replace"), meta)
        if t:
            docs.append(t)
            print(f"  {name}: ok, {len(t)} chars", flush=True)
        else:
            failed.append(f"{name}: integrity check failed (节选或壳页)")
            print(f"  {name}: FAIL", flush=True)
    if failed:
        print(f"FAILED: {failed}", flush=True)
    if not docs:
        raise SystemExit("no law converted")
    out, n = write_clean("c2_privacy_cn_laws_full", docs)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("cn-laws-full", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
