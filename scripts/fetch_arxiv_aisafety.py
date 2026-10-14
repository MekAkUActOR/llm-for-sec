"""arXiv AI-safety 研究文献 → C2 知识语料层（docs/01 §3.1 / docs/04 C2）。

多查询全历史抓取（cs.AI+cs.CL+cs.CR+cs.LG 四域），跨查询按 id 去重，
**排除 C1 已入库的 52,384 个 cs.CR id**（raw/arxiv-cscr-full 原始分页
提取，版本号剥离——避免与已训练文本重复）。

通路工程（复用 fetch_arxiv_full.py 2026-09-25 受控实验结论）：
- arXiv WAF 按 TLS 指纹拦 Python urllib → 请求经 curl.exe 子进程；
- API 深分页硬上限 start≥10000 一律 HTTP 500 → 单查询 totalResults
  ≥ SHARD_THRESHOLD 时按年分片（submittedDate 区间）；
- 限速 ToU（1 req/3s）→ 8s 间隔 + 6×60s 退避 + 连败 3 页止损 +
  分页文件落盘断点续传。

红线判断（docs/04 C2 / GHSL 同源红线）：研究论文**摘要**=攻击的
描述/分类/研究结论 → OK；摘要不含可运营的提示词载荷 → 全部放行。

查询清单（2026-09-25 总量探测，十查询共 12,669 原始命中）：
    prompt_injection 904 / jailbreak 1,721 / llm_security 2,990 /
    red_team 736 / guardrail 890 / content_moderation 498 /
    hate_speech_toxicity 2,427 / malware_ransomware 2,331 /
    code_obfuscation 65 / static_malware 107
    ai_safety_alignment 变体 b（父代理 2026-09-26 执行令）：17,423，
    经 --extra-query 追加 + 标题级纯度过滤（见 TITLE_FILTERED_QUERIES）。

用法：
    python scripts/fetch_arxiv_aisafety.py [--count] [--skip-fetch]
        [--extra-query NAME:EXPR ...]   # 追加查询（如 ai_safety_alignment）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_arxiv_full import (  # noqa: E402
    BACKOFF_S,
    SLEEP_S,
    fetch_page,
    format_doc,
    norm_title,
    parse_atom,
    strip_version,
)

ROOT = Path(__file__).resolve().parent.parent
RAW_C1 = ROOT / "data" / "corpora" / "raw" / "arxiv-cscr-full"
RAW_C1_OLD = ROOT / "data" / "corpora" / "raw" / "arxiv-cscr"
RAW = ROOT / "data" / "corpora" / "raw" / "arxiv-aisafety"
CLEAN = ROOT / "data" / "corpora" / "clean"
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"
OUT_PATH = CLEAN / "c2_aisafety_arxiv.jsonl"

PAGE_SIZE = 200
SHARD_THRESHOLD = 9000   # ≥ 此值启用年份分片（10k 硬上限之下留裕量）
CATS = '(cat:cs.AI OR cat:cs.CL OR cat:cs.CR OR cat:cs.LG)'

# (名, 查询表达式)——表达式已带最外层括号
QUERIES: list[tuple[str, str]] = [
    ("prompt_injection", '(abs:"prompt injection")'),
    ("jailbreak", "(abs:jailbreak)"),
    ("llm_security",
     '(abs:"LLM security" OR (abs:"large language model" AND abs:security))'),
    ("red_team", '(abs:"red team" OR abs:red-teaming)'),
    ("guardrail", "(abs:guardrail)"),
    ("content_moderation", '(abs:"content moderation")'),
    # 内容安全域（2026-09-25 范围扩充）
    ("hate_speech_toxicity", '(abs:"hate speech" OR abs:toxicity)'),
    # 恶意代码分析研究域（红线：分析/技术描述/家族行为学 OK，
    # 样本/构建器/武器化载荷 NO——摘要层不含载荷，放行）
    ("malware_ransomware", "(abs:malware OR abs:ransomware)"),
    ("code_obfuscation", '(abs:"code obfuscation")'),
    ("static_malware", '(abs:"static analysis" AND abs:malware)'),
]

_VER = re.compile(r"v\d+$")


def _enc(expr: str) -> str:
    """arXiv API 查询表达式的 URL 编码（空格→+，引号/括号→% 序列）。"""
    return (expr.replace(" ", "+")
                .replace('"', "%22")
                .replace("(", "%28")
                .replace(")", "%29"))


def q_url(qname_expr: str, start: int, mr: int = PAGE_SIZE,
          year: int | None = None) -> str:
    """构建查询 URL；year 非 None 时加 submittedDate 区间（分片模式）。"""
    expr = qname_expr
    q = f"{expr} AND {CATS}"
    if year is not None:
        q += (f" AND submittedDate:[{year}01010000 TO {year}12312359]")
    q = _enc(q).replace("[", "%5B").replace("]", "%5D")
    return (f"https://export.arxiv.org/api/query?search_query={q}"
            f"&sortBy=submittedDate&sortOrder=descending&start={start}"
            f"&max_results={mr}")


# ---- ai_safety_alignment 查询的标题级纯度过滤（父代理 2026-09-26 执行令）----
# 裸 alignment 吸进的对齐噪声词族；命中且题名无安全信号 → 弃。
_TITLE_EXCLUDE = re.compile(
    r"(?i)\b(vision|image|multimodal|cross-lingual|word alignment|"
    r"sequence alignment|sensor|registration|correspondence|point cloud)")
_TITLE_SAFETY = re.compile(
    r"(?i)\b(safety|safe|jailbreak|attack|adversar|robust|harm|"
    r"risk|guard|trust|rlhf|human feedback|misalign|decept|honest|"
    r"interpret|preference|steer|oversight|abuse|misuse|value)")
TITLE_FILTERED_QUERIES = {"ai_safety_alignment"}


def title_noise(title: str) -> bool:
    """排除词族命中且无安全信号 → True（弃）。

    注意：_TITLE_SAFETY 不含裸 align——"word/sequence alignment"
    噪声题名自带 alignment 字样，若 align 算安全信号会自救漏网。
    """
    return bool(_TITLE_EXCLUDE.search(title)) and \
        not bool(_TITLE_SAFETY.search(title))


def c1_ids() -> set[str]:
    """C1 已入库 id（52,384 全历史 + C0 2,000 冻结分页，版本号剥离）。"""
    ids: set[str] = set()
    for base in (RAW_C1, RAW_C1_OLD):
        for p in list(base.glob("page*.xml")) + list(base.glob("y*/page*.xml")):
            for aid, _t, _s in parse_atom(p.read_text(encoding="utf-8")):
                ids.add(aid)
    return ids


def _total_results(atom: str) -> int:
    m = re.search(r"totalResults>(\d+)<", atom)
    return int(m.group(1)) if m else 0


def fetch_query(name: str, expr: str, hard_fails: list[int]) -> None:
    """单查询全量抓取：先取 page0 判 totalResults，≥阈值转年份分片。"""
    qdir = RAW / name
    qdir.mkdir(parents=True, exist_ok=True)
    p0 = qdir / "page0000.xml"
    if not p0.exists():
        atom = _try_fetch(q_url(expr, 0), name, 0, hard_fails)
        p0.write_text(atom, encoding="utf-8")
    total = _total_results(p0.read_text(encoding="utf-8"))
    print(f"[{name}] totalResults={total}", flush=True)

    if total < SHARD_THRESHOLD:
        # 直通分页
        page = 1
        while page * PAGE_SIZE < total:
            p = qdir / f"page{page:04d}.xml"
            if not p.exists():
                p.write_text(_try_fetch(q_url(expr, page * PAGE_SIZE),
                                        name, page, hard_fails),
                             encoding="utf-8")
            page += 1
            if page % 10 == 0:
                print(f"[{name}] page{page}", flush=True)
            time.sleep(SLEEP_S)
        return

    # 年份分片（绕 10k 硬上限；复用 fetch_arxiv_full 验证过的方案）
    year_lo, year_hi = 1991, int(time.strftime("%Y"))
    for year in range(year_lo, year_hi + 1):
        ydir = qdir / f"y{year}"
        ydir.mkdir(exist_ok=True)
        page = 0
        while page < 60:
            p = ydir / f"page{page:04d}.xml"
            if p.exists():
                page += 1
                continue
            atom = _try_fetch(q_url(expr, page * PAGE_SIZE, year=year),
                              f"{name}/y{year}", page, hard_fails)
            n = len(parse_atom(atom))
            if n == 0:
                break
            p.write_text(atom, encoding="utf-8")
            if n < PAGE_SIZE:
                print(f"[{name}/y{year}] {page + 1} 页（尾页 {n} 条）",
                      flush=True)
                break
            page += 1
            time.sleep(SLEEP_S)


def _try_fetch(url: str, label: str, page: int,
               hard_fails: list[int]) -> str:
    """带止损的抓取（hard_fails 单元素列表模拟 C 指针语义）。"""
    try:
        return fetch_page(url)
    except Exception as e:  # noqa: BLE001
        hard_fails[0] += 1
        if hard_fails[0] >= 3:
            raise SystemExit(
                f"连续 {hard_fails[0]} 页硬失败：{e}\n重跑本脚本即可从 "
                f"{label}/page{page} 断点续传")
        print(f"    {label}/page{page} 硬失败（{hard_fails[0]}/3），继续",
              flush=True)
        time.sleep(120)
        return _try_fetch(url, label, page, hard_fails)


def upsert_manifest(sid: str, url: str, files: list[str], docs: int,
                    tokens: int, license_: str, domain: str, lang: str,
                    note: str = ""):
    rows = []
    if MANIFEST.exists():
        rows = [json.loads(l) for l in
                MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("id") != sid]
    rows.append({
        "id": sid, "name": sid, "url": url, "license": license_,
        "tier": "public", "domain": domain, "lang": lang,
        "est_tokens": tokens, "docs": docs, "status": "ingested",
        "ingested_at": time.strftime("%Y-%m-%d"), "files": files,
        "notes": note,
    })
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")


def main():
    ap = argparse.ArgumentParser(description="arXiv AI-safety → C2 知识层")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--extra-query", action="append", default=[],
                    metavar="NAME:EXPR",
                    help="追加查询，如 'ai_safety:(abs:\"AI safety\")'")
    args = ap.parse_args()

    queries = list(QUERIES)
    for eq in args.extra_query:
        n, _, e = eq.partition(":")
        queries.append((n.strip(), e.strip()))

    exclude = c1_ids()
    print(f"C1 排除集：{len(exclude)} ids", flush=True)

    if not args.skip_fetch:
        hard_fails = [0]
        for name, expr in queries:
            fetch_query(name, expr, hard_fails)

    # ---- 解析：跨查询去重 + C1 排除 + alignment 查询标题纯度过滤 ----
    seen: set[str] = set()
    docs: list[str] = []
    titles: dict[str, str] = {}
    audit_kept: list[tuple[str, str]] = []
    audit_dropped: list[tuple[str, str]] = []
    n_total = n_dup_c1 = n_noise = 0
    for qdir in sorted(RAW.iterdir()):
        if not qdir.is_dir():
            continue
        do_filter = qdir.name in TITLE_FILTERED_QUERIES
        pages = sorted(qdir.glob("page*.xml")) + sorted(qdir.glob("y*/page*.xml"))
        for p in pages:
            for aid, title, summ in parse_atom(p.read_text(encoding="utf-8")):
                n_total += 1
                if aid in exclude:
                    n_dup_c1 += 1
                    continue
                if do_filter and title_noise(title):
                    n_noise += 1
                    if len(audit_dropped) < 50:
                        audit_dropped.append((aid, title))
                    continue
                if aid in seen:
                    continue
                seen.add(aid)
                docs.append(format_doc_ais(aid, title, summ))
                if do_filter and len(audit_kept) < 50:
                    audit_kept.append((aid, title))
                titles.setdefault(norm_title(title), aid)
    print(f"解析 {n_total} 条：C1 已含 {n_dup_c1}（排除），标题噪声弃 "
          f"{n_noise}，跨查询去重后新增 {len(docs)}", flush=True)

    # 纯度自检存档（父代理 2026-09-26 执行令：50 保留/50 剔除样例）
    audit_path = ROOT / "reports" / "aisafety-alignment-purity-audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps({
        "query": "ai_safety_alignment (variant b)",
        "rule": "标题命中排除词族(vision|image|multimodal|cross-lingual|"
                "word alignment|sequence alignment|sensor|registration|"
                "correspondence|point cloud) 且无安全信号 → 弃",
        "dropped_count": n_noise,
        "samples_kept": [{"id": a, "title": t} for a, t in audit_kept],
        "samples_dropped": [{"id": a, "title": t} for a, t in audit_dropped],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"纯度自检 → {audit_path.name}（弃 {n_noise}，各 50 样例）",
          flush=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")
    print(f"输出 {OUT_PATH.name}: {len(docs)} docs", flush=True)

    tokens = 0
    if args.count:
        from fetch_zhwiki import count_tokens
        tokens = count_tokens(OUT_PATH)
        print(f"tokens: {tokens:,}", flush=True)

    note = ("arXiv API ToU：descriptive metadata 为 CC0 1.0（逐字引文见 "
            "arxiv-cscr-full 行）；多查询全历史（prompt injection/jailbreak/"
            "LLM security/red team/guardrail/content moderation/hate speech"
            "+toxicity/malware+ransomware/code obfuscation/static analysis"
            f"+malware{'+追加' if args.extra_query else ''}），"
            "cs.AI+CL+CR+LG 四域；与 C1 cs.CR 全历史 52,384 id 精确排除、"
            "跨查询按 id 去重；红线判断：研究摘要=攻击/恶意代码的描述/分类/"
            "结论=OK，不含可运营载荷或样本")
    upsert_manifest("arxiv-aisafety",
                    "https://export.arxiv.org/api/query (多查询, 见 raw 分目录)",
                    [str(OUT_PATH.relative_to(ROOT))], len(docs), tokens,
                    "CC0 1.0 (arXiv API ToU: descriptive metadata)",
                    "ai_safety", "en", note)
    print("manifest updated", flush=True)


def format_doc_ais(aid: str, title: str, summ: str) -> str:
    """C2 层文本格式（与 C1 cs.CR 层前缀区分，嵌入 id）。"""
    return f"arXiv AI safety research paper {aid}: {title}. {summ}"


if __name__ == "__main__":
    main()
