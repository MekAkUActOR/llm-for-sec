# -*- coding: utf-8 -*-
"""v0.4 全探针集 vs sft_m25 合并复核（留档）。

逐域构建时已各自复核过；这里是**全目录一次性**记录：8 域 2,655 单元 ×
137,670 行 SFT，8-gram 共享 ≥60 字符即命中。期望 0 命中（六域历史已验证、
general_en/privacy 重建后已复核）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check_sft_contamination import (build_ngram_index, doc_probe_hits,  # noqa: E402
                                     verify_shared_substring)

probes: dict[str, str] = {}
domains: dict[str, int] = {}
for p in sorted((ROOT / "data" / "probes" / "v0.4").glob("*.jsonl")):
    if p.name.endswith("-index.jsonl"):
        continue
    n = 0
    for i, line in enumerate(p.open(encoding="utf-8")):
        if not line.strip():
            continue
        probes[f"{p.stem}:{i}"] = json.loads(line)["text"]
        n += 1
    domains[p.stem] = n
idx = build_ngram_index(probes)
print(json.dumps({"domains": domains, "units": len(probes),
                  "ngram_keys": len(idx)}, ensure_ascii=False))

hits: dict[str, int] = {}
n_rows = 0
with (ROOT / "data" / "lf" / "sft_m25.jsonl").open(encoding="utf-8") as f:
    for line in f:
        j = json.loads(line)
        n_rows += 1
        doc = (j.get("text") if isinstance(j.get("text"), str) else
               "\n".join(m.get("content", "") for m in j.get("messages", [])))
        if not doc:
            continue
        for pid, win in doc_probe_hits(doc, idx).items():
            if verify_shared_substring(doc, probes[pid], window=win) >= 60:
                hits[pid] = hits.get(pid, 0) + 1

by_domain: dict[str, int] = {}
for pid in hits:
    d = pid.split(":")[0]
    by_domain[d] = by_domain.get(d, 0) + 1
out = {"probe_units": len(probes), "domains": domains,
       "sft_rows_scanned": n_rows, "hit_units": len(hits),
       "hit_domains": by_domain, "samples": dict(list(hits.items())[:10])}
(ROOT / "reports" / "probes-v04-vs-sft.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
