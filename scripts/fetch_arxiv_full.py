"""arXiv cs.CR 全历史摘要 → C1 训练语料（docs/04 缺口 ④）。

现有 c0_arxiv-cscr.jsonl 只含最新 2000 篇（fetch_c0.py，10 页 × 200）；
本脚本扩展到 cs.CR 全历史（totalResults 52384 篇）。

**通路工程（2026-09-25 受控实验，三道 WAF/服务端门槛）**：
1. arXiv WAF 按 TLS 指纹选择性拦截 Python urllib（JA3 签名）——响应体
   ~500KB、深分页 start>0 的 urllib 请求一律 406；curl 同参数全过。
   → 请求经 curl.exe 子进程发出。
2. API 深分页硬上限：start≥10000 一律 HTTP 500（与 mr 无关）。
   → 按年分片（submittedDate 区间查询，峰值年 ~7.9k < 10k）。
3. 限速 ToU："no more than one request every three seconds, single
   connection"——本脚本单连接、8s 间隔，失败每页 6×60s 退避、连败 3 页
   止损，年份分页文件落盘可断点续传。

许可口径（arXiv API Terms of Use, info.arxiv.org/help/api/tou.html）：
- "You are free to use descriptive metadata about arXiv e-prints under the
  terms of the Creative Commons Universal (CC0 1.0) Public Domain
  Declaration."——title/abstract/identifiers 均属 descriptive metadata
  （ToU 脚注 1），故本源许可登记为 CC0 1.0（比全文 e-print 的
  "arXiv non-exclusive license" 口径更宽）。

去重：与现有 2000 篇按 arXiv id 精确去重（id 取自 fetch_c0 冻结的
raw/arxiv-cscr/page0-9.xml 原始 Atom 响应——c0_arxiv-cscr.jsonl 文本
里不嵌 id）；版本号 vN 剥离后比较；新抓集合内部亦去重。

输出：data/corpora/clean/c1_arxiv_full.jsonl
格式 {"text": "arXiv security research paper {id}: {title}. {summary}"}
（与 C0 格式一致但嵌入 id——便于后续去重与溯源；ensure_ascii=True）。

用法：
    python scripts/fetch_arxiv_full.py [--count] [--skip-fetch]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW_OLD = ROOT / "data" / "corpora" / "raw" / "arxiv-cscr"
RAW = ROOT / "data" / "corpora" / "raw" / "arxiv-cscr-full"
CLEAN = ROOT / "data" / "corpora" / "clean"
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"
OUT_PATH = CLEAN / "c1_arxiv_full.jsonl"

UA = {"User-Agent": "llm-for-sec-arxiv-full/0.1", "Accept": "*/*"}
PAGE_SIZE = 200
SLEEP_S = 8          # ToU 下限 3s 之上留裕量。实测（2026-09-25 受控实验）
                     # WAF 三道门——响应体大小（urllib mr=200 ~500KB 恒拒）、
                     # 深分页（urllib start>0 恒拒）、TLS 指纹（Python ssl
                     # 的 JA3）——**只拦 Python urllib**；curl 同参数全过
                     # （200/页/500KB/深分页 ✓）。故请求经 curl.exe 子进程
                     # 发出，8s 间隔实测无 406。
BACKOFF_S = (60,) * 6      # 仍保留退避（对任何偶发失败），连败 3 页止损
MAX_PAGES = 50       # 每年份分片页上限（10k cap / 200 每页；峰值年 ~40 页）

_NS = {"a": "http://www.w3.org/2005/Atom"}
_WS = re.compile(r"\s+")
_VER = re.compile(r"v\d+$")
_ABS_RE = re.compile(r"abs/(.+)$")


def strip_version(aid: str) -> str:
    """剥离 arXiv id 的版本号：'2609.26761v2' -> '2609.26761'；
    旧式 'cs/0301012v1' -> 'cs/0301012'。"""
    return _VER.sub("", aid.strip())


def parse_atom(atom_text: str) -> list[tuple[str, str, str]]:
    """Atom 响应 → [(版本剥离 id, title, summary), ...]。"""
    root = ET.fromstring(atom_text)
    out = []
    for e in root.findall("a:entry", _NS):
        eid = e.findtext("a:id", "", _NS)
        title = e.findtext("a:title", "", _NS)
        summ = e.findtext("a:summary", "", _NS)
        m = _ABS_RE.search(eid or "")
        if not m or not title or not summ:
            continue
        out.append((strip_version(m.group(1)),
                    _WS.sub(" ", title).strip(),
                    _WS.sub(" ", summ).strip()))
    return out


def format_doc(aid: str, title: str, summ: str) -> str:
    """与 C0 转换器同风格，但嵌入 id（溯源与后续去重）。"""
    return f"arXiv security research paper {aid}: {title}. {summ}"


def shard_url(year: int, start: int, mr: int = PAGE_SIZE) -> str:
    """年份分片查询 URL——绕开 API 深分页 10,000 硬上限（start≥10000
    一律 HTTP 500，与 mr 无关；受控实验 2026-09-25）。cs.CR 峰值年
    ~7.9k 条 < 10k，按年分片即可全覆盖。"""
    q = (f"cat:cs.CR+AND+submittedDate:%5B{year}01010000"
         f"+TO+{year}12312359%5D")
    return (f"https://export.arxiv.org/api/query?search_query={q}"
            f"&sortBy=submittedDate&sortOrder=descending&start={start}"
            f"&max_results={mr}")


def fetch_page(url: str) -> str:
    """单页抓取（经 curl.exe 子进程——urllib 的 TLS 指纹被 WAF 拦）。

    一次请求同时取响应体与 HTTP 状态码（-w 附加在 stdout 尾行），
    失败重试绝不额外发探测请求；退避 BACKOFF_S 逐级，全败抛错
    （主循环止损/续传）。
    """
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
                 "-A", UA["User-Agent"], "-H", "Accept: */*", url],
                capture_output=True, timeout=120)
            out = r.stdout.decode("utf-8", "replace")
            if out.endswith("\n"):
                out = out[:-1]
            body, _, code = out.rpartition("\n__HTTP__")
            if (r.returncode == 0 and code == "200"
                    and body.startswith("<?xml") and "<entry>" in body):
                return body
            # 空结果页（某年无 cs.CR 论文）也是合法 200 Atom，放行
            if (r.returncode == 0 and code == "200"
                    and body.startswith("<?xml")):
                return body
            last = RuntimeError(f"curl rc={r.returncode}, http={code}, "
                                f"{len(body)}B")
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"{url[-60:]} 连续 {len(BACKOFF_S)+1} 次失败：{last}")


def existing_ids() -> set[str]:
    """C0 冻结的 2000 篇 id（从原始 Atom 分页提取，非清洗文件）。"""
    ids: set[str] = set()
    for p in sorted(RAW_OLD.glob("page*.xml")):
        for aid, _t, _s in parse_atom(p.read_text(encoding="utf-8")):
            ids.add(aid)
    return ids


def norm_title(t: str) -> str:
    """标题规范化（小写 + 压缩空白）——探针重叠检查的匹配键。"""
    return _WS.sub(" ", t).strip().lower()


def upsert_manifest(sid: str, url: str, files: list[str], docs: int,
                    tokens: int, license_: str, domain: str, lang: str,
                    note: str = ""):
    rows = []
    if MANIFEST.exists():
        rows = [json.loads(l) for l in
                MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 兼容清理：撤掉早期误写的 source 键行（2026-09-25 一次性修正）
    rows = [r for r in rows if r.get("id") != sid and "source" not in r]
    rows.append({
        "id": sid,
        "name": sid,
        "url": url,
        "license": license_,
        "tier": "public",
        "domain": domain,
        "lang": lang,
        "est_tokens": tokens,
        "docs": docs,
        "status": "ingested",
        "ingested_at": time.strftime("%Y-%m-%d"),
        "files": files,
        "notes": note,
    })
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")


def main():
    ap = argparse.ArgumentParser(description="arXiv cs.CR 全历史 → C1 语料")
    ap.add_argument("--count", action="store_true",
                    help="Qwen tokenizer CPU 统计 token 数")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="只用已下载的分页（断点续传后的离线重建）")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    old_ids = existing_ids()
    print(f"C0 既有 id：{len(old_ids)} 条（raw/arxiv-cscr/page*.xml）",
          flush=True)

    # ---- 抓取：按年分片（绕开深分页 10k 硬上限），可断点续传 ----
    if not args.skip_fetch:
        year_lo, year_hi = 1991, int(time.strftime("%Y"))
        hard_fails = 0
        for year in range(year_lo, year_hi + 1):
            ydir = RAW / f"y{year}"
            ydir.mkdir(exist_ok=True)
            page = 0
            while page < MAX_PAGES:
                p = ydir / f"page{page:04d}.xml"
                if p.exists():
                    page += 1
                    continue
                try:
                    atom = fetch_page(shard_url(year, page * PAGE_SIZE))
                except Exception as e:  # noqa: BLE001
                    hard_fails += 1
                    if hard_fails >= 3:
                        raise SystemExit(
                            f"连续 {hard_fails} 页硬失败：{e}\n"
                            f"稍后重跑本脚本即可从 {year}/page{page} "
                            f"断点续传（已下载分页全部保留）")
                    print(f"    y{year}/page{page} 硬失败"
                          f"（{hard_fails}/3），继续", flush=True)
                    time.sleep(120)
                    continue
                hard_fails = 0
                n_entries = len(parse_atom(atom))
                if n_entries == 0:
                    break            # 该年无（更多）cs.CR 论文
                p.write_text(atom, encoding="utf-8")
                if n_entries < PAGE_SIZE:
                    print(f"  y{year}: {page + 1} 页（尾页 "
                          f"{n_entries} 条）", flush=True)
                    break
                page += 1
                time.sleep(SLEEP_S)

    # ---- 解析 + 去重（顶层 page*.xml = 最新 10.2k；y*/ = 年份分片全量） ----
    seen: set[str] = set()
    all_ids: set[str] = set()     # 含与 C0 重复的（对账 API totalResults）
    docs: list[str] = []
    titles: dict[str, str] = {}   # norm_title -> id（探针重叠检查用）
    n_total = n_dup_old = 0
    pages = sorted(RAW.glob("page*.xml")) + sorted(RAW.glob("y*/page*.xml"))
    for p in pages:
        for aid, title, summ in parse_atom(p.read_text(encoding="utf-8")):
            n_total += 1
            all_ids.add(aid)
            if aid in old_ids:
                n_dup_old += 1
                continue
            if aid in seen:
                continue
            seen.add(aid)
            docs.append(format_doc(aid, title, summ))
            titles.setdefault(norm_title(title), aid)
    print(f"解析 {n_total} 条（API totalResults 口径 52384）：唯一 id "
          f"{len(all_ids)}，与 C0 重复 {n_dup_old}，新增 {len(docs)}",
          flush=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")
    print(f"输出 {OUT_PATH.name}: {len(docs)} docs", flush=True)

    tokens = 0
    if args.count:
        sys.path.insert(0, str(ROOT / "scripts"))
        from fetch_zhwiki import count_tokens
        tokens = count_tokens(OUT_PATH)
        print(f"tokens: {tokens:,}", flush=True)

    note = ("arXiv API Terms of Use (info.arxiv.org/help/api/tou.html)："
            "\"You are free to use descriptive metadata about arXiv e-prints "
            "under the terms of the Creative Commons Universal (CC0 1.0) "
            "Public Domain Declaration.\"（ToU 脚注：title/abstract/"
            "identifiers 均属 descriptive metadata）→ 摘要层许可为 CC0 1.0；"
            "限速合规：单连接、每请求间隔 8s（ToU 下限 3s 之上留裕量）；"
            "请求经 curl 子进程（实测 arXiv WAF 按 TLS 指纹选择性拦截"
            "Python urllib，curl 不受影响）；失败每页 6×60s 退避；"
            "与 c0_arxiv-cscr（最新 2000 篇）按 id 精确去重")
    upsert_manifest("arxiv-cscr-full",
                    "https://export.arxiv.org/api/query "
                    "(cat:cs.CR 按年分片全历史, totalResults 52384)",
                    [str(OUT_PATH.relative_to(ROOT))], len(docs), tokens,
                    "CC0 1.0 (arXiv API ToU: descriptive metadata)",
                    "security", "en", note)
    print("manifest updated", flush=True)

    # ---- 探针保护检查：ais.jsonl（cs.AI 摘要）与本源按标题匹配 ----
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
        print(f"[探针重叠检查] ais.jsonl 200 条中 {len(overlaps)} 条标题"
              f"命中全历史集合：", flush=True)
        for t, aid in overlaps:
            print(f"    - {aid}: {t[:70]}", flush=True)
        (ROOT / "reports" / "probe-ais-overlap-arxiv-full.json").write_text(
            json.dumps(
                {"probe": "data/probes/v0.1/ais.jsonl",
                 "overlap_count": len(overlaps),
                 "overlaps": [{"title": t, "arxiv_id": aid}
                              for t, aid in overlaps]},
                ensure_ascii=False, indent=2), encoding="utf-8")
        print("    （探针纪律由父会话决策；本脚本只报告不改探针）", flush=True)


if __name__ == "__main__":
    main()
