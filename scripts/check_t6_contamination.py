r"""T6 clean 语料污染检查（M2.5 备料纪律：输出过 8-gram 匹配器 v3）。

复用 scripts/check_sft_contamination.py 的匹配器 v3（连续成员游程 ≥50 gram
预筛 + difflib LCS ≥60 规范化字符验证 + prefix 200 + 标题键 + 查询全文子串），
基线扩展为**全量**（父指令 2026-09-28：对照 data/probes/ 与 data/heldout/
全量排除）：
  probes：v0.1 / v0.1.1 / v0.3 / ais-500-draft 全部 *.jsonl 的 text 字段
          （+ *-index.jsonl 的 query 字段作额外精确子串基线）
  heldout：v0.1 / v0.2 / v0.2.1 全部 *.jsonl 的 query 字段

对象：data/corpora/clean/{t6_devign,t6_devign_lines,t6_cvefixes}.jsonl
输出：reports/t6-contamination-check.json；任何 docs_flagged>0 → 退出码 1
（生产断言：clean 侧剔除后重建，重跑至 0）。

用法：.venv\\Scripts\\python.exe scripts/check_t6_contamination.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_sft_contamination import (  # noqa: E402  匹配器 v3 复用
    PREFIX_LEN, build_ngram_index, compile_alt_regex, doc_probe_hits,
    extract_ais_title, normalize, verify_shared_substring)

PROBE_DIRS = [ROOT / "data" / "probes" / v
              for v in ("v0.1", "v0.1.1", "v0.3", "ais-500-draft")]
HELDOUT_DIRS = [ROOT / "data" / "heldout" / v
                for v in ("v0.1", "v0.2", "v0.2.1", "v0.3-gen")]
TARGETS = ["t6_devign", "t6_devign_lines", "t6_cvefixes"]
OUT = ROOT / "reports" / "t6-contamination-check.json"


def load_baseline() -> tuple[dict, dict, list[str]]:
    """全量基线：probes{text}（跨版本按规范化文本去重）、ais 标题、heldout
    + index 查询串。"""
    probes, ais_titles = {}, {}
    index_queries = []
    seen_texts = set()
    for d in PROBE_DIRS:
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                j = json.loads(line)
                text = j.get("text") or ""
                if text:
                    key = normalize(text)
                    if key not in seen_texts:      # 跨版本同文去重
                        seen_texts.add(key)
                        pid = f"{d.name}/{f.stem}:{j.get('id', len(probes))}"
                        probes[pid] = text
                        if f.stem == "ais":
                            t = extract_ais_title(text)
                            if t:
                                ais_titles.setdefault(normalize(t), pid)
                q = j.get("query")
                if q and isinstance(q, str):
                    index_queries.append(normalize(q))
    heldout = set()
    for d in HELDOUT_DIRS:
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    j = json.loads(line)
                    if j.get("query"):
                        heldout.add(normalize(j["query"]))
    return probes, ais_titles, sorted(heldout) + index_queries


def main() -> int:
    probes, ais_titles, queries = load_baseline()
    print(f"probes(unique texts): {len(probes)}, ais titles: "
          f"{len(ais_titles)}, exact-substring queries: {len(queries)}",
          flush=True)
    ngram_index = build_ngram_index(probes)
    print(f"ngram index: {len(ngram_index):,} keys", flush=True)
    prefix_re = compile_alt_regex(
        [normalize(t)[:PREFIX_LEN] for t in probes.values()
         if len(normalize(t)) >= PREFIX_LEN])
    title_re = compile_alt_regex([t for t in ais_titles if len(t) >= 16])
    query_re = compile_alt_regex([q for q in queries if len(q) >= 12])

    report = {"probes_unique": len(probes), "ais_titles": len(ais_titles),
              "exact_queries": len(queries), "ngram_index_keys":
              len(ngram_index), "targets": {}}
    any_flagged = 0
    for name in TARGETS:
        path = ROOT / "data" / "corpora" / "clean" / f"{name}.jsonl"
        scanned = flagged = 0
        method_hits = {"prefix": 0, "title": 0, "ngram": 0, "query": 0}
        flagged_docs = []
        flagged_indices = []          # 全量索引（excerpts 截 50，索引不截）
        flagged_hashes = []           # 内容 sha256（哈希过滤防枚举序耦合）
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                scanned += 1
                doc = json.loads(line)["text"]
                t = normalize(doc)
                if not t:
                    continue
                methods, detail = [], {}
                if prefix_re.search(t):
                    methods.append("prefix")
                    method_hits["prefix"] += 1
                if title_re.search(t):
                    methods.append("title")
                    method_hits["title"] += 1
                if query_re.search(t):
                    methods.append("query")
                    method_hits["query"] += 1
                hits = doc_probe_hits(doc, ngram_index)
                if hits:
                    verified = {}
                    for pid, win in hits.items():
                        lcs = verify_shared_substring(doc, probes[pid],
                                                      window=win)
                        if lcs >= 60:
                            verified[pid] = {"membership_run_grams": win[0],
                                             "lcs_chars": lcs}
                    if verified:
                        methods.append("ngram")
                        method_hits["ngram"] += 1
                        detail["probe_overlap_verified"] = verified
                if methods:
                    flagged += 1
                    flagged_indices.append(i)
                    flagged_hashes.append(hashlib.sha256(
                        doc.encode("utf-8")).hexdigest())
                    if len(flagged_docs) < 50:
                        flagged_docs.append({
                            "doc_index": i, "methods": methods,
                            "excerpt": doc[:120].replace("\n", " ")[:120],
                            **detail})
        report["targets"][name] = {
            "docs_scanned": scanned, "docs_flagged": flagged,
            "method_hits": method_hits, "flagged_docs": flagged_docs,
            "flagged_indices": flagged_indices,
            "flagged_hashes": flagged_hashes}
        any_flagged += flagged
        print(f"  {name:18s} scanned={scanned:>6,} flagged={flagged:>3} "
              f"{method_hits}", flush=True)

    report["verdict"] = ("clean - full probes/heldout baseline, zero overlap"
                         if any_flagged == 0 else
                         f"CONTAMINATED: {any_flagged} docs flagged - "
                         f"exclude at clean side and rebuild")
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"-> {OUT}  verdict: {report['verdict']}")
    return 1 if any_flagged else 0


if __name__ == "__main__":
    sys.exit(main())
