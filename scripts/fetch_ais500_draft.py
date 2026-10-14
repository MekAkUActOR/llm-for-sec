"""ais 探针扩容草稿：最新 cs.AI 摘要 500 条 → data/probes/ais-500-draft/。

M1 出口遗留项（193→500）。**草稿目录**，父代理审后晋升；不动 v0.1.1。

排除集（防探针-训练污染，含三类）：
1. C1 cs.CR 全历史 52,384 id（raw/arxiv-cscr-full + raw/arxiv-cscr）
2. C2 arXiv AI-safety 层全部 id（raw/arxiv-aisafety/，非 cs.CR 的
   cs.AI/cs.CL/cs.LG 安全文献——已是训练数据）
3. v0.1/v0.1.1 既有 ais 探针条目（按规范化标题，避免重复；v0.1.1 的
   193 条是最新窗口，与本次抓取自然重叠大）

通路：curl 子进程（TLS 指纹 WAF）+ 8s 间隔 + 退避（复用通路工程）。
抓取：cs.AI 按 submittedDate 降序分页，直到攒满 500 条排除后的条目。

输出：data/probes/ais-500-draft/ais.jsonl（格式与 v0.1.1 ais 相同：
"arXiv cs.AI paper: {title}\n\n{summary}"，ensure_ascii=True）
用法：python scripts/fetch_ais500_draft.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_arxiv_full import fetch_page, norm_title, parse_atom  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_C1A = ROOT / "data" / "corpora" / "raw" / "arxiv-cscr-full"
RAW_C1B = ROOT / "data" / "corpora" / "raw" / "arxiv-cscr"
RAW_C2 = ROOT / "data" / "corpora" / "raw" / "arxiv-aisafety"
OUT_DIR = ROOT / "data" / "probes" / "ais-500-draft"
OUT = OUT_DIR / "ais.jsonl"

PAGE = 50
TARGET = 500
URL = ("https://export.arxiv.org/api/query?search_query=cat:cs.AI"
       "&sortBy=submittedDate&sortOrder=descending&start={start}"
       "&max_results=50")


def train_ids() -> set[str]:
    ids: set[str] = set()
    for base in (RAW_C1A, RAW_C1B):
        for p in list(base.glob("page*.xml")) + list(base.glob("y*/page*.xml")):
            for aid, _t, _s in parse_atom(p.read_text(encoding="utf-8")):
                ids.add(aid)
    for qdir in RAW_C2.iterdir():
        if not qdir.is_dir():
            continue
        for p in list(qdir.glob("page*.xml")) + list(qdir.glob("y*/page*.xml")):
            for aid, _t, _s in parse_atom(p.read_text(encoding="utf-8")):
                ids.add(aid)
    return ids


def existing_probe_titles() -> set[str]:
    """v0.1 + v0.1.1 的 ais 标题（规范化）——避免与既有探针重复。"""
    titles: set[str] = set()
    for v in ("v0.1", "v0.1.1"):
        p = ROOT / "data" / "probes" / v / "ais.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            text = json.loads(line)["text"]
            if text.startswith("arXiv cs.AI paper: "):
                t = text[len("arXiv cs.AI paper: "):].split("\n", 1)[0]
                titles.add(norm_title(t))
    return titles


def main():
    exclude = train_ids()
    old_titles = existing_probe_titles()
    print(f"排除集：{len(exclude)} 训练 id + {len(old_titles)} 既有探针标题",
          flush=True)

    docs: list[str] = []
    seen: set[str] = set()
    start = 0
    while len(docs) < TARGET and start < 3000:
        atom = fetch_page(URL.format(start=start))
        entries = parse_atom(atom)
        if not entries:
            break
        for aid, title, summ in entries:
            if aid in exclude or aid in seen:
                continue
            if norm_title(title) in old_titles:
                continue
            seen.add(aid)
            docs.append(f"arXiv cs.AI paper: {title}\n\n{summ}")
            if len(docs) >= TARGET:
                break
        print(f"  start={start}: +{len(entries)} 原始，累计 {len(docs)}/{TARGET}",
              flush=True)
        start += PAGE
        time.sleep(8)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")
    print(f"输出 {OUT}: {len(docs)} docs（草稿，待父代理审后晋升）", flush=True)


if __name__ == "__main__":
    main()
