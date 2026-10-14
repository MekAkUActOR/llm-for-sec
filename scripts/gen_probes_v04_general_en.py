# -*- coding: utf-8 -*-
"""探针 v0.4 — general_en 严格互补重建。

背景（docs/research/probe-contamination-audit.md）：v0.1.1/v0.3 的 general_en
297 篇取自 enwiki dump，而 C1-full 的 enwiki 回放是按标题哈希子采样 74%
（md5("c1mix:"+title) % 10000 < 7400，见 scripts/build_c1_mix.py），当时未按
探针标题排除 → 探针文章大概率在训，"general_en 改善幅度"读数虚高。

v0.4 做法：从**同一池**（data/corpora/clean/c1_enwiki_gen.jsonl）取哈希**补集**
h >= 7400 的 26% 篇目——按构造必然不在 C1-full 训练集内；再叠加
(a) 标题级零重复断言（与训练侧 74% 无交集，构造保证）；
(b) 8-gram 复核 vs sft_m25.jsonl（SFT 侧）；
(c) 抽样 8-gram 复核 vs sec_c1_full.jsonl（PT 侧）——三重独立证据。

选取：补集内按 md5("v04gen:"+title) 排序取前 N（确定性、跨哈希空间均匀、
不做人工挑选），要求正文 >= MIN_CHARS（PPL 稳定性）。

用法：python scripts/gen_probes_v04_general_en.py [--n 300] [--verify-only]
输出：data/probes/v0.4/general_en.jsonl（单字段 {"text": ...}）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
POOL = ROOT / "data" / "corpora" / "clean" / "c1_enwiki_gen.jsonl"
OUT = ROOT / "data" / "probes" / "v0.4" / "general_en.jsonl"
C1_MIX_KEEP = 7400          # 与 build_c1_mix.py 默认一致
MIN_CHARS = 1200


def title_of(text: str) -> str | None:
    if not text.startswith("Wikipedia article: "):
        return None
    return text.split("\n", 1)[0][len("Wikipedia article: "):]


def trained(title: str) -> bool:
    h = int(hashlib.md5(("c1mix:" + title).encode("utf-8")).hexdigest()[:8], 16)
    return h % 10000 < C1_MIX_KEEP


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--oversample", type=int, default=600)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    if args.verify_only:
        return verify(args.n)

    cands = []
    n_rows = n_comp = n_short = 0
    with POOL.open(encoding="utf-8") as f:
        for line in f:
            n_rows += 1
            try:
                text = json.loads(line)["text"]
            except Exception:  # noqa: BLE001
                continue
            t = title_of(text)
            if not t or trained(t):
                continue
            n_comp += 1
            if len(text) < MIN_CHARS:
                n_short += 1
                continue
            cands.append((int(hashlib.md5(("v04gen:" + t).encode()).hexdigest()[:8], 16),
                          t, text))
    cands.sort(key=lambda x: x[0])
    pool = cands[:args.oversample]
    print(json.dumps({"pool_rows": n_rows, "complement_rows": n_comp,
                      "complement_short": n_short,
                      "complement_usable": len(cands),
                      "oversampled": len(pool)}, ensure_ascii=False))

    # 训练侧 8-gram 扫描（SFT 全量 + PT 抽样）→ 剔除命中者，再取干净前 N
    from check_sft_contamination import (build_ngram_index, doc_probe_hits,
                                         verify_shared_substring)
    index = {f"c{i}": c[2] for i, c in enumerate(pool)}
    idx = build_ngram_index(index)
    dirty: set[str] = set()
    scans = []
    for label, path, limit in (
            ("sft_m25", ROOT / "data" / "lf" / "sft_m25.jsonl", 0),
            ("sec_c1_full(sample)", ROOT / "data" / "lf" / "sec_c1_full.jsonl",
             60000)):
        hits = n = 0
        if not path.exists():
            scans.append({label: "MISSING"})
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                if limit and n >= limit:
                    break
                try:
                    j = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                doc = (j.get("text") if isinstance(j.get("text"), str) else
                       "\n".join(m.get("content", "") for m in j.get("messages", [])))
                n += 1
                if not doc:
                    continue
                for pid, win in doc_probe_hits(doc, idx).items():
                    if verify_shared_substring(doc, index[pid], window=win) >= 60:
                        if pid not in dirty:
                            dirty.add(pid)
                            hits += 1
        scans.append({label: {"docs": n, "new_dirty": hits,
                              "total_dirty": len(dirty)}})
        print(json.dumps(scans[-1], ensure_ascii=False))
    clean = [c for i, c in enumerate(pool) if f"c{i}" not in dirty]
    picked = clean[:args.n]
    if len(picked) < args.n:
        raise SystemExit(f"干净候选不足：{len(picked)} < {args.n}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for _, _, text in picked:
            f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
    print(json.dumps({"dirty_dropped": len(dirty), "wrote": len(picked),
                      "out": str(OUT)}, ensure_ascii=False))
    return verify(args.n)


def verify(n: int) -> int:
    """三重证据复核。"""
    rows = [json.loads(l) for l in OUT.open(encoding="utf-8")]
    titles = [title_of(r["text"]) for r in rows]
    assert all(titles), "存在非 Wikipedia article 前缀行"
    assert len(set(titles)) == len(titles), "标题重复"
    bad = [t for t in titles if trained(t)]
    assert not bad, f"{len(bad)} 篇落在训练侧 74%：{bad[:3]}"
    lens = sorted(len(r["text"]) for r in rows)
    print(json.dumps({"probe_rows": len(rows),
                      "chars_min_med_max": [lens[0], lens[len(lens) // 2], lens[-1]],
                      "trained_side_overlap": 0}, ensure_ascii=False))

    # 8-gram 复核 vs sft_m25（SFT 侧）与 sec_c1_full 抽样（PT 侧）
    from check_sft_contamination import (build_ngram_index, doc_probe_hits,
                                         verify_shared_substring)
    probes = {f"v04gen:{t}": r["text"] for t, r in zip(titles, rows)}
    idx = build_ngram_index(probes)
    print(f"ngram_index_keys={len(idx)}")
    for label, path, limit in (("sft_m25", ROOT / "data" / "lf" / "sft_m25.jsonl", 0),
                               ("sec_c1_full(sample)", ROOT / "data" / "lf" / "sec_c1_full.jsonl",
                                60000)):
        hits = 0
        checked = 0
        with path.open(encoding="utf-8") as f:
            for line in f:
                if limit and checked >= limit:
                    break
                try:
                    j = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                doc = (j.get("text") if isinstance(j.get("text"), str) else
                       "\n".join(m.get("content", "") for m in j.get("messages", [])))
                checked += 1
                if not doc:
                    continue
                for pid, win in doc_probe_hits(doc, idx).items():
                    if verify_shared_substring(doc, probes[pid], window=win) >= 60:
                        hits += 1
                        break
        print(json.dumps({f"ngram_hits_vs_{label}": hits, "docs_checked": checked},
                         ensure_ascii=False))
        if hits:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
