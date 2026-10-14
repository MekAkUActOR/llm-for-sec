"""中文维基百科 dump → C1 训练语料（安全域子集 + 通用回放子采样）。

前置：data/corpora/raw/zhwiki/zhwiki-latest-pages-articles.xml.bz2
（curl https://dumps.wikimedia.org/zhwiki/latest/zhwiki-latest-pages-articles.xml.bz2）

输出（data/corpora/clean/）：
- c1_zhwiki_sec.jsonl  安全/隐私相关条目（分类树 + 标题关键词，domain=security, lang=zh）
- c1_zhwiki_gen.jsonl  其余条目确定性子采样（通用 zh 回放，--gen-sample 控制比例）

设计要点（与 fetch_c0.py 一致）：
- 转换器为纯函数（wikitext_to_text / is_security），可单测；
- ensure_ascii=True 输出（pyarrow JSON 兼容，见 docs/02 §0.1 #4）；
- md5 去重、最短长度过滤；
- manifest 登记（许可 CC-BY-SA 4.0，发布需署名+相同方式共享）。

用法：
    python scripts/fetch_zhwiki.py [--gen-sample 0.15] [--count sec|all|none]
"""
from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

if hasattr(sys.stdout, "reencode"):
    pass
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "corpora" / "raw" / "zhwiki"
CLEAN = ROOT / "data" / "corpora" / "clean"
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"

DUMP = RAW / "zhwiki-latest-pages-articles.xml.bz2"

MIN_CHARS = 500          # 清洗后最短正文（过短条目多为存根/消歧义）
GEN_SAMPLE_DEFAULT = 0.15  # 通用子集默认采样率

# ---------------------------------------------------------------- 清洗 --

_REF_SELF = re.compile(r"(?i)<ref[^>]*?/>")
_REF_PAIR = re.compile(r"(?is)<ref[^>]*?>.*?</ref>")
_COMMENT = re.compile(r"(?s)<!--.*?-->")
_TABLE = re.compile(r"(?is)\{\|.*?\|\}")
_LINK = re.compile(r"\[\[(?:[^\[\]|]*\|)?([^\[\]|]+)\]\]")
_EXTURL = re.compile(r"\[https?://\S+\s+([^\]]+)\]")
_EXTURL_BARE = re.compile(r"\[https?://\S+\]")
_HEADING = re.compile(r"(?m)^=+\s*(.*?)\s*=+\s*$")
_QUOTE = re.compile(r"'{2,}")
_TAG = re.compile(r"(?is)<[^>]+>")
_LISTMARK = re.compile(r"(?m)^[*:;#]+")
_WS = re.compile(r"[ \t]+")
_NL = re.compile(r"\n{3,}")
# 模板/引用剥离后常在中文之间残留空格 → 折叠（两侧均为 CJK/全角才折叠，
# 中英混排的有意空格不受影响）
_CJK_GAP = re.compile(r"(?<=[\u3000-\u9fff\uff00-\uffef]) +(?=[\u3000-\u9fff\uff00-\uffef])")

_CAT = re.compile(r"\[\[(?:Category|分类):([^\]]+)\]\]")

# 分类树关键词（条目所属分类命中即视为安全域）
_SEC_CATS = (
    "计算机安全", "网络安全", "信息安全", "密码学", "加密", "恶意软件",
    "计算机病毒", "特洛伊木马", "勒索软件", "黑客", "漏洞", "入侵",
    "钓鱼", "社会工程学", "防火墙", "隐私", "数据保护", "身份认证",
    "访问控制", "安全漏洞", "渗透测试", "拒绝服务攻击",
)
# 标题关键词（次级判据，比"安全"二字更收紧，避免混入交通安全/食品安全等 safety 域）
_SEC_TITLE = (
    "信息安全", "网络安全", "计算机安全", "漏洞", "恶意软件", "木马",
    "计算机病毒", "勒索软件", "密码学", "加密", "黑客", "钓鱼", "隐私",
    "勒索病毒", "后门", "零日攻击", "渗透测试", "拒绝服务", "SQL注入",
    "跨站脚本", "漏洞利用",
)


def wikitext_to_text(wt: str) -> str:
    """MediaWiki 源码 → 纯文本（模板/引用/表格/链接/标记剥离）。"""
    wt = _COMMENT.sub(" ", wt)
    wt = _REF_SELF.sub(" ", wt)
    wt = _REF_PAIR.sub(" ", wt)
    wt = _TABLE.sub(" ", wt)
    # 嵌套模板 {{...{{...}}...}}：迭代剥离至不动点
    prev = None
    while prev != wt:
        prev = wt
        wt = re.sub(r"\{\{[^{}]*\}\}", " ", wt)
    # 内链保留锚文本；外链保留描述
    wt = _LINK.sub(r"\1", wt)
    wt = _EXTURL.sub(r"\1", wt)
    wt = _EXTURL_BARE.sub(" ", wt)
    wt = _HEADING.sub(r"\n\1\n", wt)
    wt = _QUOTE.sub("", wt)
    wt = _TAG.sub(" ", wt)
    wt = _LISTMARK.sub(" ", wt)
    wt = _CJK_GAP.sub("", wt)
    wt = _WS.sub(" ", wt)
    wt = _NL.sub("\n\n", wt)
    return wt.strip()


def is_security(title: str, wikitext: str) -> bool:
    """安全/隐私域判据：分类树命中（主）或标题关键词命中（次）。"""
    cats = _CAT.findall(wikitext)
    if any(any(k in c for k in _SEC_CATS) for c in cats):
        return True
    return any(k in title for k in _SEC_TITLE)


# ---------------------------------------------------------------- 解析 --

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def iter_pages(path: Path):
    """流式遍历 dump 中的 <page> 元素（ns=0 且非重定向）。"""
    with bz2.open(path, "rb") as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if _local(elem.tag) != "page":
                continue
            title = ns = text = None
            for child in elem:
                lt = _local(child.tag)
                if lt == "title":
                    title = (child.text or "").strip()
                elif lt == "ns":
                    ns = (child.text or "0").strip()
                elif lt == "revision":
                    for rc in child:
                        if _local(rc.tag) == "text":
                            text = rc.text or ""
            elem.clear()
            if ns != "0" or title is None or text is None:
                continue
            if text.lstrip().upper().startswith("#REDIRECT"):
                continue
            yield title, text


def sampled(title: str, rate: float) -> bool:
    """确定性采样（哈希阈值），重跑结果稳定。"""
    if rate >= 1.0:
        return True
    h = int(hashlib.md5(title.encode("utf-8")).hexdigest()[:8], 16)
    return (h % 10000) < int(rate * 10000)


# ---------------------------------------------------------------- 主流程 --

def write_docs(path: Path, docs: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    n = 0
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            h = hashlib.md5(t.encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            # ensure_ascii=True：pyarrow JSON 兼容（docs/02 §0.1 #4）
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")
            n += 1
    return n


def upsert_manifest(sid: str, files: list[str], docs: int, tokens: int,
                    license_: str, domain: str, lang: str, note: str = ""):
    rows = []
    if MANIFEST.exists():
        rows = [json.loads(l) for l in
                MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("source") != sid]
    rows.append({
        "source": sid,
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


def count_tokens(path: Path) -> int:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(
        "Qwen/Qwen3-0.6B-Base", cache_dir=str(ROOT / ".cache" / "huggingface"))
    total, batch = 0, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            batch.append(json.loads(line)["text"])
            if len(batch) >= 1000:
                total += sum(len(x) for x in tok(batch, add_special_tokens=False)["input_ids"])
                batch = []
    if batch:
        total += sum(len(x) for x in tok(batch, add_special_tokens=False)["input_ids"])
    return total


def main():
    ap = argparse.ArgumentParser(description="zhwiki dump → C1 语料")
    ap.add_argument("--gen-sample", type=float, default=GEN_SAMPLE_DEFAULT)
    ap.add_argument("--count", choices=["sec", "all", "none"], default="sec",
                    help="token 计数范围（sec 仅安全子集，all 含通用采样）")
    args = ap.parse_args()

    if not DUMP.exists():
        raise SystemExit(f"dump 不存在：{DUMP}\n先运行：\n"
                         "curl -L -o <dump> https://dumps.wikimedia.org/zhwiki/"
                         "latest/zhwiki-latest-pages-articles.xml.bz2")

    t0 = time.time()
    sec_docs, gen_docs = [], []
    n_pages = n_kept = 0
    for title, wt in iter_pages(DUMP):
        n_pages += 1
        if n_pages % 100000 == 0:
            print(f"  ... {n_pages} pages, sec={len(sec_docs)}, "
                  f"gen={len(gen_docs)}, {time.time()-t0:.0f}s", flush=True)
        t = wikitext_to_text(wt)
        if len(t) < MIN_CHARS:
            continue
        n_kept += 1
        if is_security(title, wt):
            sec_docs.append(f"维基百科条目：{title}\n\n{t}")
        elif sampled(title, args.gen_sample):
            gen_docs.append(f"维基百科条目：{title}\n\n{t}")

    sec_path = CLEAN / "c1_zhwiki_sec.jsonl"
    gen_path = CLEAN / "c1_zhwiki_gen.jsonl"
    n_sec = write_docs(sec_path, sec_docs)
    n_gen = write_docs(gen_path, gen_docs)
    print(f"pages={n_pages} kept={n_kept} -> sec={n_sec} gen={n_gen} "
          f"(采样率 {args.gen_sample})，耗时 {time.time()-t0:.0f}s", flush=True)

    sec_tok = gen_tok = 0
    if args.count in ("sec", "all"):
        sec_tok = count_tokens(sec_path)
        print(f"sec tokens: {sec_tok:,}", flush=True)
    if args.count == "all":
        gen_tok = count_tokens(gen_path)
        print(f"gen tokens: {gen_tok:,}", flush=True)

    note = ("维基百科内容，CC-BY-SA 4.0：模型发布时需署名并以相同方式共享（M5/D3 评审项）；"
            "安全域判据=分类树+标题关键词，见 scripts/fetch_zhwiki.py")
    upsert_manifest("zhwiki-sec", [str(sec_path.relative_to(ROOT))], n_sec, sec_tok,
                    "CC-BY-SA 4.0", "security", "zh", note)
    upsert_manifest("zhwiki-gen", [str(gen_path.relative_to(ROOT))], n_gen, gen_tok,
                    "CC-BY-SA 4.0", "general", "zh", note)
    print("manifest updated", flush=True)


if __name__ == "__main__":
    main()
