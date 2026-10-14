"""英文维基百科 dump 分区 → C1 训练语料（en 通用回放层）。

docs/04 C1 缺口分析优先级第一：en 回放层目标 300–500M tokens。
分区下载页 https://dumps.wikimedia.org/enwiki/latest/ ，文件名形如
enwiki-latest-pages-articles2.xml-p41243p151573.bz2（每分区 300–800MB）。

与 fetch_zhwiki.py 的关系：
- 复用其 iter_pages / wikitext_to_text / write_docs / count_tokens
  （清洗器语言无关，_CJK_GAP 只影响 CJK 邻接空格，英文空格不受影响）；
- zhwiki 管线按安全域分两个子集；本管线只做**纯通用回放**（en 安全域
  由 C0 的 CVE/CWE/ATT&CK/OWASP 等来源覆盖，enwiki 中零星安全条目
  作为回放成分保留，不做域拆分）。

**探针隔离（硬约束）**：分区 1（p1p41242）已被 M1 出口探针
data/probes/v0.1/general_en 占用，**永不用于训练语料**——
select_partition_files 强制排除分区 1。

输出：data/corpora/clean/c1_enwiki_gen.jsonl
格式 {"text": "Wikipedia article: {title}\n\n{text}"}，ensure_ascii=True。

用法：
    python scripts/fetch_enwiki.py [--count] [--parts 2,3]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fetch_zhwiki import (  # noqa: E402
    MIN_CHARS,
    CLEAN,
    MANIFEST,
    ROOT,
    count_tokens,
    iter_pages,
    wikitext_to_text,
    write_docs,
)

RAW_EN = ROOT / "data" / "corpora" / "raw" / "enwiki"
OUT_PATH = CLEAN / "c1_enwiki_gen.jsonl"

# 分区 1 已被探针占用（data/probes/v0.1/general_en）——来源隔离，禁止入训练
PROBE_PARTITION = 1
_DUMPS_URL = "https://dumps.wikimedia.org/enwiki/latest/"

# 兼容两种命名：官方全名 articles2.xml-p41243p151573.bz2
# 与本地短名 articles2-p41243p151573.bz2（下载时去掉了 latest-pages 与 .xml）
_PART_RE = re.compile(r"articles(\d+)(?:\.xml)?[-.]")


def format_doc(title: str, text: str) -> str:
    """英文维基条目训练文档格式。"""
    return f"Wikipedia article: {title}\n\n{text}"


def partition_no(name: str):
    """从 dump 文件名提取分区号；无分区号（如全量单文件）返回 None。"""
    m = _PART_RE.search(name)
    return int(m.group(1)) if m else None


def select_partition_files(names: list[str]) -> list[str]:
    """给定 raw 目录下的文件名，选出可入训练的分区 dump（按分区号升序）。

    - 只认 articles 分区（enwiki-latest-pages-articlesN.xml-*.bz2）；
    - **强制排除分区 1**（探针隔离）；
    - 未知分区号的全量文件按无分区号处理（排在分区文件之后，保守不排除
      仅当文件名不是分区 1）。
    """
    picked = []
    for n in names:
        no = partition_no(n)
        if no is None:
            continue
        if no == PROBE_PARTITION:
            continue
        picked.append((no, n))
    picked.sort()
    return [n for _no, n in picked]


def upsert_manifest(sid: str, url: str, files: list[str], docs: int,
                    tokens: int, license_: str, domain: str, lang: str,
                    note: str = ""):
    """manifest upsert（fetch_zhwiki 版 + url 字段）。"""
    rows = []
    if MANIFEST.exists():
        rows = [json.loads(l) for l in
                MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("source") != sid]
    rows.append({
        "source": sid,
        "url": url,
        "ingested_at": time.strftime("%Y-%m-%d"),
        "tier": "public",
        "license": license_,
        "domain": domain,
        "lang": lang,
        "docs": docs,
        "est_tokens": tokens,
        "files": files,
        "notes": note,
    })
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")


def count_tokens_texts(texts: list[str]) -> int:
    """对内存中的文本列表批量计数（Qwen tokenizer, CPU）。"""
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(
        "Qwen/Qwen3-0.6B-Base", cache_dir=str(ROOT / ".cache" / "huggingface"))
    total = 0
    for i in range(0, len(texts), 1000):
        batch = texts[i:i + 1000]
        total += sum(len(x) for x in
                     tok(batch, add_special_tokens=False)["input_ids"])
    return total


def main():
    ap = argparse.ArgumentParser(description="enwiki 分区 → C1 en 回放语料")
    ap.add_argument("--count", action="store_true",
                    help="用 Qwen tokenizer 统计 token 数（CPU）")
    ap.add_argument("--parts", default=None,
                    help="逗号分隔分区号白名单（默认处理全部已下载分区）")
    args = ap.parse_args()

    all_names = [p.name for p in RAW_EN.glob("enwiki-articles*.bz2")]
    names = select_partition_files(all_names)
    if args.parts:
        want = {int(x) for x in args.parts.split(",")}
        names = [n for n in names if partition_no(n) in want]
    if not names:
        raise SystemExit(
            f"raw/enwiki 下没有可用的训练分区 dump（分区 1 已被探针占用，"
            f"强制排除）。先下载，例如：\n"
            f"curl -L -o {RAW_EN / 'enwiki-articles2-p41243p151573.bz2'} "
            f"{_DUMPS_URL}enwiki-latest-pages-articles2.xml-p41243p151573.bz2")
    skipped_probe = [n for n in all_names
                     if partition_no(n) == PROBE_PARTITION]
    if skipped_probe:
        print(f"[探针隔离] 已排除分区 1（{', '.join(skipped_probe)}）",
              flush=True)
    print(f"待处理分区：{', '.join(names)}", flush=True)

    t0 = time.time()
    docs = []
    n_pages = n_kept = 0
    per_part = []
    tokens = 0
    for name in names:
        p = RAW_EN / name
        p_pages = p_kept = 0
        p_start = len(docs)
        for title, wt in iter_pages(p):
            n_pages += 1
            p_pages += 1
            if n_pages % 50000 == 0:
                print(f"  ... {n_pages} pages, kept={n_kept}, "
                      f"{time.time()-t0:.0f}s", flush=True)
            t = wikitext_to_text(wt)
            if len(t) < MIN_CHARS:
                continue
            n_kept += 1
            p_kept += 1
            docs.append(format_doc(title, t))
        p_tok = 0
        if args.count:
            print(f"  [token 计数] {name} ({p_kept} docs)...", flush=True)
            p_tok = count_tokens_texts(docs[p_start:])
            tokens += p_tok
            print(f"  {name}: {p_tok:,} tokens", flush=True)
        per_part.append((name, p_pages, p_kept, p_tok))
        print(f"[分区完成] {name}: pages={p_pages} kept={p_kept} "
              f"tokens={p_tok:,} ({time.time()-t0:.0f}s)", flush=True)

    n_docs = write_docs(OUT_PATH, docs)
    print(f"总 pages={n_pages} kept={n_kept} -> {n_docs} docs "
          f"(md5 去重后)，耗时 {time.time()-t0:.0f}s", flush=True)

    if args.count and tokens == 0:
        # 逐分区计数已在内联完成；此分支仅当无分区时兜底
        print("token 计数（Qwen tokenizer, CPU）...", flush=True)
        tokens = count_tokens(OUT_PATH)
    if args.count:
        print(f"tokens: {tokens:,}", flush=True)

    note = ("英文维基百科内容，CC-BY-SA 4.0：模型发布时需署名并以相同方式"
            "共享（M5/D3 评审项）；纯通用回放层，不做安全域拆分；"
            "分区 1 被 data/probes 探针占用，永不入训练（来源隔离）")
    urls = _DUMPS_URL + ", ".join(names)
    upsert_manifest("enwiki-gen", urls, [str(OUT_PATH.relative_to(ROOT))],
                    n_docs, tokens, "CC-BY-SA 4.0", "general", "en", note)
    print("manifest updated", flush=True)
    for name, pp, pk, pt in per_part:
        print(f"  {name}: {pp} pages -> {pk} docs -> {pt:,} tokens", flush=True)


if __name__ == "__main__":
    main()
