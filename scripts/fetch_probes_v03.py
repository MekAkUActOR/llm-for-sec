r"""探针集 v0.3：三新域（aisafety/malware/content）+ ais-500 晋升 + 组装。

**设计文档（fetch 等 C2 b 变体终态后再执行；排除逻辑先行锁定）**

## 为什么需要三新域

M1.5 知识注入效果测量：C2 语料（c2_aisafety_arxiv 等，b 变体）把对齐/LLM
安全、恶意代码分析、内容审核研究文献注入训练后，需要**同域但 id 隔离**的
留出文本来观测 PPL 变化——现有五域探针（v0.1.1）没有这三个域的对应物。

## 三层隔离设计（缺一不可，v0.1.1 事故的教训）

训练侧（排除集）来源 = 任何已入库/计划入库的 arXiv 语料：
  c0_arxiv-cscr / c1_arxiv_full（cs.CR 全历史 50,384）/ c2_aisafety_arxiv /
  c2_privacy_arxiv（及后续 b 变体新增 *_arxiv）。

1. **id 层**：raw Atom 页（raw/arxiv-*/…，逐页 parse_atom——干净的
   (id,title,summary) 三元组）+ 清洗文件头部内嵌 id 兜底
   （`arXiv … paper (\d{4}\.\d{4,5}):`）；
2. **标题层**：norm_title（小写+压缩空白）精确匹配——v0.1.1 曾靠它发现
   7 条双列目污染（id 层当时形同虚设）；
3. **探针内去重**：与 v0.1.1/ais-500 既有探针条目及新域之间互斥。

## 查询设计（存活率 × 域相关性）

训练抓取（b 变体）CATS = cs.AI|cs.CL|cs.CR|cs.LG（privacy 侧 cs.CR|cs.DB），
按表达式取全历史——**表达式子集查询会被排除层清空**。探针取**同表达式 ×
互补类目**轴：cs.CY（社会与计算）/cs.SE/cs.PL/soc.SI 不在训练 CATS 内，
天然存活；表达式维持域相关性；跨列目（如 cs.CY×cs.CR 双列）由排除层兜底。
每查询存活统计打印（kept/excluded）——存活率即设计有效性的实证。

## 子命令

- ``fetch --only aisafety,malware,content --per-domain 400``
  抓取三新域 → data/probes/v0.3/<域>.jsonl（含 -index.jsonl 审计索引：
  id/title/排除判定）。b 变体终态后执行。
- ``verify-ais500 [--promote]``
  ais-500-draft 重验零污染（id+标题层 vs 当前语料态；语料哈希入标记文件）。
  --promote 零污染时复制为 v0.3/ais.jsonl 并写 .ais500-verified.json。
- ``assemble``
  v0.3 定稿 = v0.1.1 五域（字节相同复制）+ ais-500 已验证版 + 三新域 +
  README 统计。前置检查：三新域存在、ais 标记有效（语料哈希未漂移）。

探针纪律同 data/heldout：**永不入训练**、版本化、审计 README。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_arxiv_full import fetch_page, norm_title, parse_atom  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "corpora" / "clean"
RAW = ROOT / "data" / "corpora" / "raw"
V011 = ROOT / "data" / "probes" / "v0.1.1"
AIS500 = ROOT / "data" / "probes" / "ais-500-draft"
V03 = ROOT / "data" / "probes" / "v0.3"
PAGE_SIZE = 200
MIN_CHARS = 200

# 训练侧类目（b 变体 CATS）——新域查询的互补性断言依据
TRAIN_CATS = {"cs.AI", "cs.CL", "cs.CR", "cs.LG", "cs.DB"}

# ---------------------------------------------------------------- 查询表 --

DOMAINS: dict[str, dict] = {
    "aisafety": {
        "label": "AI safety",   # 与 c2 训练语料头部同风格
        "queries": [
            ('abs:"prompt injection" OR abs:jailbreak OR abs:"AI safety"',
             "(cat:cs.CY)"),
            ('abs:"red team" OR abs:red-teaming OR abs:guardrail',
             "(cat:cs.CY)"),
            ('abs:"safety alignment" OR abs:"adversarial attack"',
             "(cat:cs.CY)"),
        ],
    },
    "malware": {
        "label": "malware analysis",
        "queries": [
            ("abs:malware OR abs:ransomware",
             "(cat:cs.SE OR cat:cs.PL OR cat:cs.CY)"),
            ('abs:"code obfuscation" OR abs:deobfuscation OR abs:packer',
             "(cat:cs.SE OR cat:cs.PL OR cat:cs.CY)"),
            ('abs:"static analysis" AND abs:malicious',
             "(cat:cs.SE OR cat:cs.PL)"),
        ],
    },
    "content": {
        "label": "content moderation",
        "queries": [
            ('abs:"content moderation" OR abs:"hate speech" OR abs:toxicity',
             "(cat:cs.CY OR cat:soc.SI)"),
            ('abs:"harmful content" OR abs:"trust and safety" '
             'OR abs:"content policy"',
             "(cat:cs.CY OR cat:soc.SI)"),
        ],
    },
}


def check_query_disjointness() -> list[str]:
    """设计自检：每个查询的类目集合与训练 CATS 交集必须为空（互补轴）。"""
    problems = []
    for dom, spec in DOMAINS.items():
        for expr, cats in spec["queries"]:
            used = set(re.findall(r"cat:([A-Za-z.]+)", cats))
            overlap = used & TRAIN_CATS
            if overlap:
                problems.append(f"{dom}: 查询类目 {overlap} 与训练 CATS 重叠")
    return problems


def _enc(expr: str) -> str:
    return (expr.replace(" ", "+")
                .replace('"', "%22")
                .replace("(", "%28")
                .replace(")", "%29"))


def query_url(expr: str, cats: str, start: int, mr: int = PAGE_SIZE) -> str:
    q = f"({expr}) AND {cats}"
    return (f"https://export.arxiv.org/api/query?search_query={_enc(q)}"
            f"&sortBy=submittedDate&sortOrder=descending&start={start}"
            f"&max_results={mr}")


# ---------------------------------------------------------------- 排除集 --

def _clean_arxiv_corpora() -> list[Path]:
    """已入库 + 当前态的 arXiv 清洗语料（排除集的文件清单）。"""
    paths = []
    for pat in ("c0_arxiv*.jsonl", "c1_arxiv*.jsonl", "c2_*_arxiv*.jsonl"):
        paths.extend(sorted(CLEAN.glob(pat)))
    return [p for p in paths if p.is_file()]


def corpus_state(paths: list[Path]) -> dict:
    """语料态指纹（sha256+行数）——验证标记的漂移检测。"""
    state = {}
    for p in paths:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        with open(p, "rb") as f:
            n = sum(1 for _ in f)
        try:
            key = str(p.relative_to(ROOT))
        except ValueError:  # 测试注入的临时目录
            key = p.name
        state[key] = {"sha256": h.hexdigest()[:16], "docs": n}
    return state


def build_exclusion(skip_probe_dirs: tuple = ()) -> dict:
    """三层排除集：ids / titles / 既有探针标题。

    id+标题层主源 = raw Atom 页（parse_atom 干净三元组）；
    兜底 = 清洗文件头部内嵌 id（`arXiv … paper <id>:`）。
    skip_probe_dirs：验证某探针自身时跳过其目录（否则自比对全量误报）。
    """
    ids: set[str] = set()
    titles: set[str] = set()
    raw_roots = sorted(RAW.glob("arxiv-*"))
    xml_pages = []
    for r in raw_roots:
        xml_pages.extend(sorted(r.rglob("*.xml")))
    for p in xml_pages:
        try:
            for aid, title, _s in parse_atom(p.read_text(encoding="utf-8")):
                ids.add(aid)
                titles.add(norm_title(title))
        except Exception as e:  # noqa: BLE001
            print(f"    WARN: raw 页解析失败 {p.name}: {e}", flush=True)
    hdr_id = re.compile(r"paper (\d{4}\.\d{4,5}):")
    for p in _clean_arxiv_corpora():
        with open(p, encoding="utf-8") as f:
            for line in f:
                m = hdr_id.search(line)
                if m:
                    ids.add(m.group(1))
    # 既有探针标题（探针内互斥：新抓不得与既有探针重复）
    probe_titles: set[str] = set()
    for d in (V011, AIS500):
        if d in skip_probe_dirs:
            continue
        p = d / "ais.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line:
                    t = json.loads(line)["text"].split("\n", 1)[0]
                    t = t.split("paper: ", 1)[-1] if "paper: " in t else t
                    probe_titles.add(norm_title(t))
    return {"ids": ids, "titles": titles, "probe_titles": probe_titles,
            "raw_pages": len(xml_pages)}


def excluded(aid: str, title: str, excl: dict) -> str:
    """排除判定：返回原因（空串=保留）。"""
    if aid in excl["ids"]:
        return "id-in-train"
    if norm_title(title) in excl["titles"]:
        return "title-in-train"
    if norm_title(title) in excl["probe_titles"]:
        return "title-in-existing-probe"
    return ""


# ---------------------------------------------------------------- 抓取 --

def fetch_domain(domain: str, per_domain: int, excl: dict) -> list[dict]:
    """同域互补类目抓取：逐查询分页，攒满 per_domain 即停。

    返回 [{"id", "title", "text", "query"}]；-index.jsonl 审计同源。
    已写域的标题实时并入 probe_titles——跨域同论文不双入。
    """
    spec = DOMAINS[domain]
    out: list[dict] = []
    seen: set[str] = set()
    stats = {}
    for expr, cats in spec["queries"]:
        qname = expr[:40]
        kept = excl_n = 0
        for page in range(8):  # 每查询至多 8×200 条候选
            url = query_url(expr, cats, page * PAGE_SIZE)
            try:
                atom = fetch_page(url)
            except Exception as e:  # noqa: BLE001
                print(f"    [{domain}] 抓取失败（稍后 --only {domain} 重试）：{e}",
                      flush=True)
                break
            entries = parse_atom(atom)
            if not entries:
                break
            for aid, title, summ in entries:
                if aid in seen:
                    continue
                seen.add(aid)
                why = excluded(aid, title, excl)
                if why:
                    excl_n += 1
                    continue
                text = (f"arXiv {spec['label']} research paper {aid}: "
                        f"{title}. {summ}")
                if len(text.strip()) < MIN_CHARS:
                    continue
                out.append({"id": aid, "title": title, "text": text,
                            "query": qname})
                excl["probe_titles"].add(norm_title(title))  # 跨域互斥
                kept += 1
                if len(out) >= per_domain:
                    break
            time.sleep(3)  # arXiv API 限流礼貌间隔
            if len(out) >= per_domain or len(entries) < PAGE_SIZE:
                break
        stats[qname] = {"kept": kept, "excluded": excl_n}
        if len(out) >= per_domain:
            break
    print(f"  [{domain}] 查询存活统计: {json.dumps(stats, ensure_ascii=False)}",
          flush=True)
    return out


def write_domain(domain: str, docs: list[dict]) -> None:
    V03.mkdir(parents=True, exist_ok=True)
    with open(V03 / f"{domain}.jsonl", "w", encoding="utf-8",
              newline="\n") as f:
        for d in docs:
            f.write(json.dumps({"text": d["text"]}, ensure_ascii=True) + "\n")
    with open(V03 / f"{domain}-index.jsonl", "w", encoding="utf-8",
              newline="\n") as f:
        for d in docs:
            f.write(json.dumps({"id": d["id"], "title": d["title"],
                                "query": d["query"]},
                               ensure_ascii=False) + "\n")


# -------------------------------------------------------- ais-500 晋升 --

def verify_ais500(state_paths: list[Path]) -> dict:
    """ais-500 草稿重验：标题层 vs 当前语料态（草稿不嵌 id）。

    返回 {"overlap": [...], "n": N, "state": {...}}——overlap 非空即不可晋升。
    skip 自身目录：排除集不读 ais-500（否则自比对全量误报）。
    """
    excl = build_exclusion(skip_probe_dirs=(AIS500,))
    overlap = []
    n = 0
    src = AIS500 / "ais.jsonl"
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        n += 1
        t = json.loads(line)["text"]
        header = t.split("\n", 1)[0]
        title = header.split("paper: ", 1)[-1] if "paper: " in header else header
        why = excluded("", title, excl)
        if why and why != "id-in-train":
            overlap.append({"title": title, "reason": why})
    return {"overlap": overlap, "n": n,
            "state": corpus_state(state_paths)}


def promote_ais500(verify: dict, prune: bool = False) -> bool:
    """晋升 ais-500 → v0.3/ais.jsonl。prune=True 时剪除污染条目（净版）。"""
    if verify["overlap"] and not prune:
        print(f"ais-500 验证失败：{len(verify['overlap'])} 条污染，不可晋升"
              f"（--prune 可剪除污染条目出净版，或 b 变体终态后重抓）")
        for o in verify["overlap"][:10]:
            print(f"  - {o['reason']}: {o['title'][:70]}")
        return False
    V03.mkdir(parents=True, exist_ok=True)
    if verify["overlap"]:
        # 剪除模式：重读草稿，逐条判排除，仅保留干净条目
        excl = build_exclusion(skip_probe_dirs=(AIS500,))
        dirty = {norm_title(o["title"]) for o in verify["overlap"]}
        kept_lines, pruned = [], 0
        for line in (AIS500 / "ais.jsonl").read_text(
                encoding="utf-8").splitlines():
            if not line:
                continue
            t = json.loads(line)["text"]
            header = t.split("\n", 1)[0]
            title = (header.split("paper: ", 1)[-1]
                     if "paper: " in header else header)
            if norm_title(title) in dirty or excluded("", title, excl):
                pruned += 1
                continue
            kept_lines.append(line)
        (V03 / "ais.jsonl").write_text("\n".join(kept_lines) + "\n",
                                       encoding="utf-8", newline="\n")
        verify = {**verify, "n": len(kept_lines), "pruned": pruned,
                  "overlap": []}
        print(f"ais-500 剪除晋升：{pruned} 条污染剪除，净版 {len(kept_lines)} 条"
              f" → {V03 / 'ais.jsonl'}")
    else:
        (V03 / "ais.jsonl").write_bytes((AIS500 / "ais.jsonl").read_bytes())
        print(f"ais-500 晋升：{verify['n']} 条零污染 → {V03 / 'ais.jsonl'}")
    (V03 / ".ais500-verified.json").write_text(
        json.dumps(verify, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


# ---------------------------------------------------------------- 组装 --

FIVE = ("sec", "privacy", "general_en", "general_zh")  # ais 单独走晋升


def assemble() -> int:
    problems = []
    for d in ("aisafety", "malware", "content"):
        if not (V03 / f"{d}.jsonl").exists():
            problems.append(f"缺新域 {d}.jsonl（先 fetch）")
    marker = V03 / ".ais500-verified.json"
    if not marker.exists():
        problems.append("ais-500 未验证/晋升（先 verify-ais500 --promote）")
    else:
        cur = corpus_state(_clean_arxiv_corpora())
        old = json.loads(marker.read_text(encoding="utf-8"))["state"]
        if cur != old:
            changed = [k for k in old if old.get(k) != cur.get(k)]
            problems.append(
                f"语料态在 ais-500 验证后漂移（{changed}）——重验后再组装")
    if problems:
        for p in problems:
            print("ASSEMBLE BLOCKED:", p)
        return 1
    for name in FIVE:
        src, dst = V011 / f"{name}.jsonl", V03 / f"{name}.jsonl"
        dst.write_bytes(src.read_bytes())  # 字节相同（纵向可比性）
    stats = {}
    for p in sorted(V03.glob("*.jsonl")):
        if p.name.endswith("-index.jsonl"):
            continue
        with p.open(encoding="utf-8") as f:
            stats[p.stem] = sum(1 for _ in f)
    readme = V03 / "README.md"
    readme.write_text(
        "# 探针集 v0.3\n\n来源隔离的固定文本样本（M1.5 知识注入观测）。"
        "**永不入训练语料**。\n\n## 构成\n\n"
        "| 域 | 条数 | 来源 |\n|---|---|---|\n"
        + "".join(
            f"| {k} | {v} | "
            + ("v0.1.1 字节复制（ais 为 ais-500 已验证版；其余四域纵向可比）"
               if k in (*FIVE, "ais") else
               "arXiv 同域互补类目（cs.CY/SE/PL/soc.SI），三层排除 vs 训练语料"
               "（详见 scripts/fetch_probes_v03.py 设计文档）")
            + " |\n"
            for k, v in stats.items())
        + f"\n组装时间：{time.strftime('%Y-%m-%d %H:%M')}\n"
          f"ais-500 验证态：{json.dumps(json.loads(marker.read_text(encoding='utf-8'))['state'], ensure_ascii=False)}\n",
        encoding="utf-8")
    print(f"v0.3 组装完成：{json.dumps(stats, ensure_ascii=False)}")
    print(f"README -> {readme}")
    return 0


# ---------------------------------------------------------------- CLI --

def main(argv=None):
    ap = argparse.ArgumentParser(description="探针集 v0.3（设计见模块 docstring）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap_f = sub.add_parser("fetch", help="抓取三新域（b 变体终态后执行）")
    ap_f.add_argument("--only", default="aisafety,malware,content")
    ap_f.add_argument("--per-domain", type=int, default=400)
    ap_f.add_argument("--dry-run", action="store_true",
                      help="只构建排除集并打印规模，不发请求")
    sub.add_parser("verify-ais500", help="重验 ais-500 草稿零污染")
    ap_p = sub.add_parser("verify-ais500-promote",
                          help="验证通过则晋升为 v0.3/ais.jsonl")
    ap_p.add_argument("--prune", action="store_true",
                      help="有污染时剪除污染条目出净版（而非拒绝晋升）")
    sub.add_parser("assemble", help="组装 v0.3（前置检查不通过则拒绝）")
    sub.add_parser("check-design", help="查询互补性自检（无网络）")
    args = ap.parse_args(argv)

    if args.cmd == "check-design":
        problems = check_query_disjointness()
        print("设计自检：", "PASS" if not problems else "\n".join(problems))
        return 0 if not problems else 1

    if args.cmd in ("verify-ais500", "verify-ais500-promote"):
        v = verify_ais500(_clean_arxiv_corpora())
        print(json.dumps({"n": v["n"], "overlap": len(v["overlap"])},
                         ensure_ascii=False))
        if args.cmd == "verify-ais500-promote":
            return 0 if promote_ais500(v, prune=getattr(args, "prune", False)) else 1
        return 0 if not v["overlap"] else 1

    if args.cmd == "assemble":
        return assemble()

    # fetch
    excl = build_exclusion()
    print(f"排除集：ids={len(excl['ids'])} titles={len(excl['titles'])} "
          f"probe_titles={len(excl['probe_titles'])} "
          f"(raw pages={excl['raw_pages']})", flush=True)
    if args.dry_run:
        return 0
    domains = [d.strip() for d in args.only.split(",") if d.strip()]
    for d in domains:
        if d not in DOMAINS:
            print(f"未知域：{d}（可选：{list(DOMAINS)}）")
            return 1
    for d in domains:
        docs = fetch_domain(d, args.per_domain, excl)
        if docs:
            write_domain(d, docs)
            print(f"  [{d}] 写入 {len(docs)} 条", flush=True)
        else:
            print(f"  [{d}] 零存活——检查查询/排除集", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
