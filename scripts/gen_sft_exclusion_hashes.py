r"""污染/红线剔除索引 → 内容 sha256 哈希清单（组装管线前置件）。

背景（docs/research/m2-data-assembly-plan.md §5）：
- 原始检查报告的 flagged_docs 有 **50 条截断**——wildjailbreak 671 条命中
  只列了 50（cap_loss=621），计划的"767 条剔除"不可完整恢复自报告；
- doc_index 是检查器枚举序（sorted 文件序），直接按索引过滤会把生成器
  耦合到枚举序——按计划建议转**内容哈希清单**，消歧一劳永逸。

本工具是**检查器侧**（合法读 data/probes/v0.1.1 与 data/heldout/v0.2——
与 check_sft_contamination 同纪律）；组装器（assemble_sft_m2.py）只读
输出 reports/sft-exclusion-hashes.json 的 sha256 集——生成器源码零评估
路径引用，隔离红线不破。

哈希口径：sha256(check_sft_contamination.docs_for 文本) 逐字节一致——
组装器侧的镜像构造有单测桥接校验（防漂移）。

行为：
1. 污染：wildjailbreak 全量重跑（无上限）恢复 671 条；其余 14 个训练源
   报告完整（flagged == listed，已验证），按报告索引转换；
2. 交叉验证：重跑结果 ⊇ 已列 50 条且计数 == 671，否则硬失败；
3. 红线：m2-sft-redline-detail.json——hh 顶层 indices、batch23 四源
   indices、trustllm file+index（换算到全局枚举位）；
4. 输出：{"_meta": {...}, "<source>": {"n_contamination", "n_redline",
   "n_union", "sha256": [...]}}（tc260 是 reference-only，永不入训——不产清单）。

用法：python scripts/gen_sft_exclusion_hashes.py [--rerun-wj/--no-rerun-wj]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_sft_contamination as csc  # noqa: E402  检查器侧复用（枚举/正则/ngram 设施）

OUT = ROOT / "reports" / "sft-exclusion-hashes.json"
REDLINE = ROOT / "reports" / "m2-sft-redline-detail.json"

# 训练侧 15 源（tc260 = m2-reference，永不入训，无清单）
TRAIN_SOURCES = ["hh-rlhf-harmlessness", "safety-prompts", "safemtdata",
                 "advbench", "harmbench", "strongreject", "maliciousinstruct",
                 "xstest", "or-bench", "trustllm-safety", "cvalues",
                 "pku-saferlhf", "beavertails", "wildjailbreak", "wildguardmix"]


def _report(sid: str) -> dict:
    p = ROOT / "reports" / f"sft-contamination-check-{sid}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _rerun_flagged_full(sid: str, probes, ngram_index, prefix_re,
                        title_re, heldout_re) -> set:
    """无 50 条上限重跑（复用检查器判定逻辑，恢复截断条目）。"""
    flagged = set()
    for i, doc in enumerate(csc.docs_for(sid)):
        if not doc:
            continue
        t = csc.normalize(doc)
        if not t:
            continue
        hit = (prefix_re.search(t) or title_re.search(t)
               or heldout_re.search(t))
        if not hit:
            hits = csc.doc_probe_hits(doc, ngram_index)
            if hits:
                for pid, win in hits.items():
                    if csc.verify_shared_substring(
                            doc, probes[pid], window=win) >= csc.LCS_MIN_CHARS:
                        hit = True
                        break
        if hit:
            flagged.add(i)
    return flagged


def _redline_indices(sid: str, detail: dict, tl_offsets: dict | None) -> set:
    """红线索引（各源同 docs_for 枚举序；trustllm 为 file-local 需换算）。"""
    out = set()
    if sid == "hh-rlhf-harmlessness":
        out |= set(detail["hh-rlhf-harmlessness"]["indices"])
    elif sid in ("pku-saferlhf", "beavertails", "wildjailbreak",
                 "wildguardmix"):
        out |= set(detail["batch23_redline"][sid]["indices"])
    elif sid == "trustllm-safety" and tl_offsets:
        for e in detail["trustllm-safety"]["flagged"]:
            base = tl_offsets[e["file"]]
            out.add(base + e["index"])
    return out


def _trustllm_offsets() -> dict:
    """trustllm file-local 索引 → docs_for 全局枚举位（sorted rglob 序）。"""
    offsets, pos = {}, 0
    for p in sorted((csc.RAW_M2 / "trustllm" / "dataset").rglob("*.json")):
        n = len(json.loads(p.read_text(encoding="utf-8")))
        offsets[str(p.relative_to(csc.RAW_M2 / "trustllm" / "dataset"))
                .replace("\\", "/")] = pos
        pos += n
    return offsets


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun-wj", action="store_true", default=True)
    ap.add_argument("--no-rerun-wj", dest="rerun_wj", action="store_false")
    args = ap.parse_args(argv)

    detail = json.loads(REDLINE.read_text(encoding="utf-8"))

    # wj 全量重跑（恢复 621 条截断）——只此一次构建探针设施
    wj_full = None
    if args.rerun_wj:
        print("rebuilding probe baselines for wildjailbreak full re-run...",
              flush=True)
        probes, _ais, _hd = csc.load_probes()
        ngram_index = csc.build_ngram_index(probes)
        prefix_re = csc.compile_alt_regex(
            [csc.normalize(t)[:csc.PREFIX_LEN]
             for t in probes.values()
             if len(csc.normalize(t)) >= csc.PREFIX_LEN])
        title_re = csc.compile_alt_regex(
            [csc.normalize(t) for t in _ais if len(t) >= 16])
        heldout_re = csc.compile_alt_regex([q for q in _hd if len(q) >= 12])
        print("re-running wildjailbreak check (no cap)...", flush=True)
        wj_full = _rerun_flagged_full("wildjailbreak", probes, ngram_index,
                                      prefix_re, title_re, heldout_re)
        rep = _report("wildjailbreak")
        listed = {d["doc_index"] for d in rep["flagged_docs"]}
        assert len(wj_full) == rep["docs_flagged"], (
            f"wj re-run {len(wj_full)} != report {rep['docs_flagged']}")
        assert listed <= wj_full, "wj re-run missing documented indices"
        print(f"  wildjailbreak full re-run: {len(wj_full)} flagged "
              f"(report listed {len(listed)}, recovered "
              f"{len(wj_full) - len(listed)})", flush=True)

    tl_offsets = _trustllm_offsets()
    out = {"_meta": {
        "purpose": "exclusion content-hash lists for assemble_sft_m2",
        "doc_text_spec": "sha256 over check_sft_contamination.docs_for text",
        "contamination_reports": "reports/sft-contamination-check-*.json",
        "redline_report": "reports/m2-sft-redline-detail.json",
        "wildjailbreak_full_rerun": wj_full is not None,
        "notes": ("redline total 350 (plan says 351: safemtdata's 1 "
                  "weaponized entry ruled no-skip by detail note; its "
                  "responses are all [S] self-built so no raw text enters "
                  "training)"),
    }}
    for sid in TRAIN_SOURCES:
        rep = _report(sid)
        if sid == "wildjailbreak" and wj_full is not None:
            contam = wj_full
        else:
            assert rep["docs_flagged"] == len(rep["flagged_docs"]), (
                f"{sid}: report cap-truncated, needs full re-run")
            contam = {d["doc_index"] for d in rep["flagged_docs"]}
        redline = _redline_indices(sid, detail, tl_offsets)
        want = contam | redline
        hashes = []
        for i, doc in enumerate(csc.docs_for(sid)):
            if i in want:
                hashes.append(hashlib.sha256(
                    doc.encode("utf-8")).hexdigest())
        assert len(hashes) == len(want), (
            f"{sid}: hash count {len(hashes)} != want {len(want)} "
            "(enumeration drift?)")
        out[sid] = {"n_contamination": len(contam), "n_redline": len(redline),
                    "n_union": len(want), "sha256": sorted(hashes)}
        print(f"  {sid:24s} contam={len(contam):>4} redline={len(redline):>3} "
              f"union={len(want):>4}", flush=True)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    total = sum(v["n_union"] for k, v in out.items() if k != "_meta")
    print(f"-> {OUT} (sources={len(TRAIN_SOURCES)}, union docs={total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
