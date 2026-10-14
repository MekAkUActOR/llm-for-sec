"""C1-full 训练集组装（方案 B：~1.09B，安全域 ×2 epoch）。

用户决策（2026-09-25）：方案 B——沿用 stage1-202m 已验证的 ~36-40% 安全配比，
安全域 217.2M 唯一文本写两遍（等效 2 epoch），回放 ~650M，总 ~1.09B，1 epoch。

组成（manifest est_tokens 为准）：
- 安全域（×2）：
  C0 九源（不含 c0_all.jsonl 汇总与 c0_arxiv-cscr.jsonl——后者是
  c1_arxiv_full 的子集，用它会造成该 2000 篇 3 倍重复）
  + P1 七源（redhat/debian/msrc/sans/cisco/oracle/ghsl/p0）
  + c1_arxiv_full + c1_zhwiki_sec
- 回放（×1）：
  c1_zhwiki_gen（15% 采样现成文件，124.3M——绝对量与 stage1-202m 相同，
  general_zh 保持有实证）
  c1_enwiki_gen 确定性子采样 ~74%（标题 md5 阈值；对应 P2+P3+P4 体量，
  避免重解析分区）

输出：data/lf/sec_c1_full.jsonl（ensure_ascii 源文件直拼，不重写内容）
用法：python scripts/build_c1_mix.py [--enwiki-keep 7400]（万分比）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "corpora" / "clean"
OUT = ROOT / "data" / "lf" / "sec_c1_full.jsonl"

SECURITY = [
    # C0（除 arxiv-cscr：被 c1_arxiv_full 覆盖）
    "c0_capec.jsonl", "c0_cve.jsonl", "c0_cwe.jsonl", "c0_gdpr.jsonl",
    "c0_kev.jsonl", "c0_mitre-attack.jsonl", "c0_owasp-cs.jsonl",
    "c0_cn-laws.jsonl", "c0_cn-regs.jsonl",
    # P1 七源
    "c0_redhat-csaf.jsonl", "c0_debian-dsa.jsonl", "c0_msrc-cvrf.jsonl",
    "c0_sans-isc.jsonl", "c0_cisco-psirt.jsonl", "c0_oracle-cpu.jsonl",
    "c0_ghsl-advisories.jsonl", "c0_p0-0days.jsonl",
    # arXiv 全历史 + zh 安全
    "c1_arxiv_full.jsonl", "c1_zhwiki_sec.jsonl",
]


def enwiki_keep(line: str, keep: int) -> bool:
    """确定性子采样：标题 md5 万分比阈值（keep=7400 → 74%）。"""
    try:
        text = json.loads(line)["text"]
        title = text.split("\n", 1)[0][len("Wikipedia article: "):]
    except Exception:  # noqa: BLE001
        return False
    h = int(hashlib.md5(("c1mix:" + title).encode("utf-8")).hexdigest()[:8], 16)
    return h % 10000 < keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enwiki-keep", type=int, default=7400)
    args = ap.parse_args()

    # 前置检查：安全域文件全在
    missing = [f for f in SECURITY if not (CLEAN / f).exists()]
    if missing:
        raise SystemExit(f"missing security files: {missing}")
    for f in ("c1_zhwiki_gen.jsonl", "c1_enwiki_gen.jsonl"):
        if not (CLEAN / f).exists():
            raise SystemExit(f"missing replay file: {f}")

    n_sec_docs = n_rep_docs = n_enwiki_kept = n_enwiki_total = 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as out:
        # 1) 安全域第一遍
        for f in SECURITY:
            with open(CLEAN / f, encoding="utf-8") as g:
                for line in g:
                    out.write(line)
                    n_sec_docs += 1
        # 2) zh 回放
        with open(CLEAN / "c1_zhwiki_gen.jsonl", encoding="utf-8") as g:
            for line in g:
                out.write(line)
                n_rep_docs += 1
        # 3) en 回放（确定性子采样）
        with open(CLEAN / "c1_enwiki_gen.jsonl", encoding="utf-8") as g:
            for line in g:
                n_enwiki_total += 1
                if enwiki_keep(line, args.enwiki_keep):
                    out.write(line)
                    n_rep_docs += 1
                    n_enwiki_kept += 1
        # 4) 安全域第二遍
        for f in SECURITY:
            with open(CLEAN / f, encoding="utf-8") as g:
                for line in g:
                    out.write(line)
                    n_sec_docs += 1

    size_mb = OUT.stat().st_size / 2**20
    ratio = n_enwiki_kept / max(n_enwiki_total, 1)
    print(f"security docs (x2): {n_sec_docs}")
    print(f"replay docs: {n_rep_docs} (enwiki kept {n_enwiki_kept}/{n_enwiki_total} = {ratio:.1%})")
    print(f"total lines: {n_sec_docs + n_rep_docs}")
    print(f"file size: {size_mb:.0f} MB")

    # pyarrow 校验 + manifest est_tokens 汇总
    import pyarrow.json as paj
    with open(OUT, "rb") as f:
        rows = paj.read_json(f).num_rows
    print(f"pyarrow rows: {rows}")
    man = {}
    for l in (ROOT / "data/corpora/manifest.jsonl").read_text(
            encoding="utf-8").splitlines():
        d = json.loads(l)
        man[d["name"]] = d.get("est_tokens", 0)
    # 文件名 → manifest name 映射：去 c0_/c1_ 前缀 + 两处特殊名
    def manifest_name(fname: str) -> str:
        stem = fname.rsplit(".", 1)[0]
        if stem.startswith(("c0_", "c1_")):
            stem = stem[3:]
        return {"arxiv_full": "arxiv-cscr-full",
                "zhwiki_sec": "zhwiki-sec"}.get(stem, stem)

    sec_tok = sum(man.get(manifest_name(f), 0) for f in SECURITY)
    print(f"security est_tokens (unique): {sec_tok:,}  x2 = {2 * sec_tok:,}")
    print(f"zh replay est: {man.get('zhwiki-gen', 0):,}")
    print(f"en replay est (x{ratio:.3f}): {int(man.get('enwiki-gen', 0) * ratio):,}")
    total = 2 * sec_tok + man.get("zhwiki-gen", 0) + int(
        man.get("enwiki-gen", 0) * ratio)
    print(f"TOTAL est_tokens: {total:,}  (~{total / 1e6:.0f}M)")


if __name__ == "__main__":
    main()
