"""M1 出口探针集（v0.1）：与训练语料来源隔离的固定文本样本，用于逐 checkpoint PPL 对比。

探针域与来源（docs/05 §7；纪律同 data/heldout：永不入训练、版本化、逐步扩容）：
- sec        Ubuntu 安全通告 USN（ubuntu.com/security/notices.json，Ubuntu 自撰文本，
             与训练用的 cvelistV5/CVE 描述完全不同来源）
- privacy    GDPR 各序言（gdpr-info.eu/recitals；训练语料只含正文 99 条，序言隔离）
- ais        arXiv cs.AI 摘要（训练语料为 cs.CR；按 id 过滤双列目防重叠）
             —— 注意 arXiv API 有严格限流，406 时稍后 --only ais 重试
- general_en 英文维基随机条目（en.wikipedia API；训练不含 enwiki）
- general_zh 中文维基：从本地 zhwiki dump 抽取未入训练采样的条目（标题过滤）

输出：data/probes/v0.1/<域>.jsonl（{"text": ...}，ensure_ascii）
用法：python scripts/fetch_probes.py [--per-domain 500] [--only sec,ais]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "corpora" / "raw" / "probes"
OUT = ROOT / "data" / "probes" / "v0.1"
UA = {"User-Agent": "llm-for-sec-probes/0.1"}


def http(url, data=None, timeout=60, retries=3):
    req = urllib.request.Request(
        url, headers=UA,
        data=json.dumps(data).encode() if data else None,
        method="POST" if data else "GET")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (406, 429):  # 限流：立即上抛，由调用方决定稍后重试
                raise
            last = e
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def write_jsonl(path: Path, texts: list[str], min_chars=200) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for t in texts:
            t = t.strip()
            if len(t) < min_chars:
                continue
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")
            n += 1
    return n


# ---------------------------------------------------------------- 各域 --

def _iter_zip_local_entries(path):
    """流式扫描 zip 本地文件头，产出 (文件名, 数据)——可读不完整 zip。

    逐条校验 CRC；用于抢救被网络重置截断的下载
    （尾部中央目录缺失时 zipfile.ZipFile 不可用）。
    """
    import struct
    import zlib
    with open(path, "rb") as f:
        while True:
            hdr = f.read(30)
            if len(hdr) < 30 or hdr[:4] != b"PK\x03\x04":
                return  # 到达中央目录/截断点/损坏点
            method, crc, csize, _usize = struct.unpack("<H4xIII", hdr[8:26])
            nlen, elen = struct.unpack("<HH", hdr[26:30])
            name = f.read(nlen).decode("utf-8", "replace")
            f.read(elen)
            data = f.read(csize)
            if len(data) < csize:
                return
            if method == 8:
                try:
                    data = zlib.decompress(data, -15)
                except zlib.error:
                    continue
            elif method != 0:
                continue
            if zlib.crc32(data) & 0xFFFFFFFF != crc:
                continue
            yield name, data


def fetch_usn(per_domain: int) -> list[str]:
    """安全域探针：GHSA 通告（github/advisory-database，CC-BY-4.0）。

    取 github-reviewed 目录（GitHub 审核过的通告，即 OSV 同源数据），
    每条通告的 summary/description 由 GHSA 撰写，与训练用的 cvelistV5
    描述不同源不同措辞。OSV API / Ubuntu USN 均因本网络 TLS 拦截不稳弃用。
    实况：zip 下载被网络重置于 396MB，本地头扫描抢救出 37.6 万条
    reviewed 通告 JSON（CRC 全过）；通告文件为 JSON 而非 YAML（仓库已迁移）。
    """
    zpath = RAW / "ghsa-main.zip"
    if not zpath.exists():
        raise SystemExit(f"GHSA zip 不存在：{zpath}（先 curl "
                         "https://github.com/github/advisory-database/"
                         "archive/refs/heads/main.zip）")
    reviewed: list[tuple[str, bytes]] = []
    for name, data in _iter_zip_local_entries(zpath):
        if ("/advisories/github-reviewed/" in name
                and name.endswith(".json")):
            reviewed.append((name, data))
    if len(reviewed) < per_domain:
        raise SystemExit(f"GHSA reviewed 条目不足：{len(reviewed)}")
    # 按路径排序取尾部（最新年份/编号）
    reviewed.sort()
    texts: list[str] = []
    for _name, raw in reviewed[-per_domain * 2:]:
        try:
            d = json.loads(raw.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(d, dict):
            continue
        parts = [f"GHSA advisory {d.get('id', '')}: "
                 f"{d.get('summary', '')}",
                 (d.get('details') or '').strip()]
        aliases = ", ".join((d.get('aliases') or [])[:4])
        if aliases:
            parts.append(f"Aliases: {aliases}")
        texts.append("\n\n".join(p for p in parts if p))
        if len(texts) >= per_domain:
            break
    return texts


def fetch_recitals() -> list[str]:
    """GDPR 173 条序言（训练语料只含正文 99 条，序言来源隔离）。"""
    d = RAW / "gdpr-recitals"
    d.mkdir(parents=True, exist_ok=True)
    texts = []
    for i in range(1, 174):
        p = d / f"recital-{i}.html"
        if not p.exists():
            try:
                p.write_text(http(f"https://gdpr-info.eu/recitals/no-{i}/"),
                             encoding="utf-8")
                time.sleep(0.3)
            except Exception as e:  # noqa: BLE001
                print(f"    recital {i} FAILED: {e}", flush=True)
                continue
        h = p.read_text(encoding="utf-8")
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
        t = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6])[^>]*>", "\n", t)
        t = re.sub(r"<[^>]+>", " ", t)
        import html as _h
        t = _h.unescape(t)
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n")]
        t = "\n".join(ln for ln in lines if ln)
        m = re.search(rf"\({i}\)\s", t)
        if m:
            t = t[m.start():]
            for stop in ("Suitable articles", "GDPR:", "Rate us"):
                idx = t.find(stop)
                if idx > 0:
                    t = t[:idx]
        texts.append(t)
    return texts


def fetch_arxiv_csai(per_domain: int, train_ids: set[str]) -> list[str]:
    """arXiv cs.AI 摘要（训练为 cs.CR；按 id 剔除双列目）。"""
    d = RAW / "arxiv-csai"
    d.mkdir(parents=True, exist_ok=True)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    texts = []
    for page in range(3):
        url = ("http://export.arxiv.org/api/query?search_query=cat:cs.AI"
               f"&sortBy=submittedDate&sortOrder=descending&start={page * 200}"
               "&max_results=200")
        try:
            atom = http(url, retries=1)
            (d / f"page{page}.xml").write_text(atom, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"    cs.AI page {page} FAILED: {e}", flush=True)
            continue
        root = ET.fromstring(atom.encode())
        for entry in root.findall("a:entry", ns):
            eid = (entry.findtext("a:id", "", ns) or "").strip()
            m = re.search(r"(\d{4}\.\d{4,5})", eid)
            if not m or m.group(1) in train_ids:
                continue
            title = re.sub(r"\s+", " ", entry.findtext("a:title", "", ns)).strip()
            summary = re.sub(r"\s+", " ", entry.findtext("a:summary", "", ns)).strip()
            texts.append(f"arXiv cs.AI paper: {title}\n\n{summary}")
        time.sleep(3)
        if len(texts) >= per_domain:
            break
    return texts


def _wiki_random_en(n: int) -> list[str]:
    """英文维基：从 enwiki dump 第一分区（p1p41242，最老的经典条目）确定性采样。

    摘要 dump 已停产；random+extracts API 被限流（429）；
    分区 dump 为完整正文，复用 fetch_zhwiki 的解析与清洗管线。
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_zhwiki import iter_pages, wikitext_to_text
    dump = (ROOT / "data" / "corpora" / "raw" / "enwiki"
            / "enwiki-articles1-p1p41242.bz2")
    if not dump.exists():
        raise SystemExit(f"enwiki 分区 dump 不存在：{dump}")
    picked: list[str] = []
    for title, wt in iter_pages(dump):
        h = int(hashlib.md5(("probe-en:" + title).encode("utf-8"))
                .hexdigest()[:8], 16)
        if h % 1000 >= 15:  # ~1.5% 命中密度，41k 条中取 ~600 再截断
            continue
        t = wikitext_to_text(wt)
        if len(t) < 500:
            continue
        picked.append(f"Wikipedia article: {title}\n\n{t}")
        if len(picked) >= n:
            break
    return picked


def _wiki_zh_from_dump(n: int, exclude_titles: set[str]) -> list[str]:
    """从本地 zhwiki dump 抽取未入训练的条目（确定性采样，标题过滤）。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_zhwiki import DUMP, iter_pages, wikitext_to_text
    if not DUMP.exists():
        raise SystemExit(f"zhwiki dump 不存在：{DUMP}")
    picked: list[str] = []
    tried = 0
    for title, wt in iter_pages(DUMP):
        if title in exclude_titles:
            continue
        tried += 1
        # 确定性采样：与训练采样无关的独立哈希流
        h = int(hashlib.md5(("probe:" + title).encode("utf-8")).hexdigest()[:8], 16)
        if h % 1000 >= 40:  # 目标命中密度 ~4%，凑够 n 篇即停
            continue
        t = wikitext_to_text(wt)
        if len(t) < 500:
            continue
        picked.append(f"维基百科条目：{title}\n\n{t}")
        if len(picked) >= n:
            break
        if tried % 200000 == 0:
            print(f"    zhwiki probe: {len(picked)}/{n}", flush=True)
    return picked


# ---------------------------------------------------------------- 训练侧集合 --

def _train_wiki_titles() -> set[str]:
    titles: set[str] = set()
    for name in ("c1_zhwiki_sec.jsonl", "c1_zhwiki_gen.jsonl"):
        p = ROOT / "data" / "corpora" / "clean" / name
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                t = json.loads(line)["text"]
                if t.startswith("维基百科条目："):
                    titles.add(t.split("\n", 1)[0][len("维基百科条目："):])
    return titles


def _train_arxiv_ids() -> set[str]:
    ids: set[str] = set()
    p = ROOT / "data" / "corpora" / "clean" / "c0_arxiv-cscr.jsonl"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                m = re.search(r"arXiv:(\d{4}\.\d{4,5})", json.loads(line)["text"])
                if m:
                    ids.add(m.group(1))
    return ids


# ---------------------------------------------------------------- 主流程 --

def main():
    ap = argparse.ArgumentParser(description="M1 探针集抓取")
    ap.add_argument("--per-domain", type=int, default=500)
    ap.add_argument("--only", default=None,
                    help="逗号分隔的域列表（默认全部）")
    args = ap.parse_args()

    jobs = {
        "sec": lambda: fetch_usn(args.per_domain),
        "privacy": lambda: fetch_recitals(),
        "ais": lambda: fetch_arxiv_csai(args.per_domain, _train_arxiv_ids()),
        "general_en": lambda: _wiki_random_en(args.per_domain),
        "general_zh": lambda: _wiki_zh_from_dump(args.per_domain, _train_wiki_titles()),
    }
    only = set(args.only.split(",")) if args.only else None
    summary = {}
    for name, fn in jobs.items():
        if only and name not in only:
            continue
        t0 = time.time()
        try:
            texts = fn()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] SOURCE FAILED: {e}", flush=True)
            continue
        n = write_jsonl(OUT / f"{name}.jsonl", texts)
        summary[name] = n
        print(f"[{name}] {n} docs ({time.time()-t0:.0f}s)", flush=True)

    print(json.dumps(summary, ensure_ascii=False))
    if summary:
        (OUT / "README.md").parent.mkdir(parents=True, exist_ok=True)
        readme = (OUT / "README.md")
        existing = readme.read_text(encoding="utf-8") if readme.exists() else (
            "# M1 探针集 v0.1\n\n来源隔离的固定文本样本，仅用于逐 checkpoint PPL 对比"
            "（docs/05 §7）。**永不入训练语料**。\n\n")
        existing += time.strftime("\n- %H:%M 更新: ") + ", ".join(
            f"{k}={v}" for k, v in summary.items()) + "\n"
        readme.write_text(existing, encoding="utf-8")


if __name__ == "__main__":
    main()
