"""M0 工具：tokenizer fertility 测量（docs/01 §2.2；协议见 docs/02 §2）。

用法：
    # 1) 生成合成语料组（或使用真实语料目录）
    python -m secfm.audit.corpora --out data/fertility --size 65536

    # 2) 测量
    python -m secfm.audit.fertility --tokenizer Qwen/Qwen2.5-1.5B \
        --corpora-dir data/fertility --baseline data/fertility/baseline_mix.txt \
        --json-out reports/fertility-qwen2.5.json

判据（docs/01 §2.2）：重度语料 bytes/token 相对自然文本基线
通胀比 < 1.5 为通过；超标进入词表扩展 vs 上下文门控决策。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def measure(texts, encode) -> dict:
    b = sum(len(t.encode("utf-8")) for t in texts)
    n = sum(len(encode(t)) for t in texts)
    return {"texts": len(texts), "bytes": b, "tokens": n,
            "bytes_per_token": (b / n) if n else None}


def fertility_report(corpora, baseline, encode, threshold=1.5) -> dict:
    base = measure(baseline, encode)
    rows = {}
    for name, texts in corpora.items():
        m = measure(texts, encode)
        if base["bytes_per_token"] and m["bytes_per_token"]:
            ratio = m["bytes_per_token"] / base["bytes_per_token"]
        else:
            ratio = None
        rows[name] = {**m, "ratio_vs_baseline": ratio,
                      "pass": (ratio is not None and ratio < threshold)}
    measured = [r["pass"] for r in rows.values() if r["ratio_vs_baseline"] is not None]
    return {"baseline": base, "threshold": threshold, "corpora": rows,
            "overall_pass": all(measured) if measured else None}


def _load_encode(name):
    try:
        from transformers import AutoTokenizer
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "需要 transformers 才能加载 tokenizer："
            "在项目 .venv 中运行，或 pip install transformers") from e
    tok = AutoTokenizer.from_pretrained(name)
    return lambda t: tok(t, add_special_tokens=False)["input_ids"]


def _split_paragraphs(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return paras or [text]


def main(argv=None):
    ap = argparse.ArgumentParser(description="tokenizer fertility 测量")
    ap.add_argument("--tokenizer", required=True, help="HF tokenizer id 或本地路径")
    ap.add_argument("--corpora-dir", required=True,
                    help="目录下每个 *.txt 为一个语料组（baseline 文件自动排除）")
    ap.add_argument("--baseline", required=True, help="自然文本基线 *.txt")
    ap.add_argument("--threshold", type=float, default=1.5)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    encode = _load_encode(args.tokenizer)
    corpora_dir = Path(args.corpora_dir)
    baseline_path = Path(args.baseline).resolve()
    corpora = {p.stem: _split_paragraphs(p)
               for p in sorted(corpora_dir.glob("*.txt"))
               if p.resolve() != baseline_path}
    if not corpora:
        raise SystemExit(f"corpora-dir 中没有可用语料组: {corpora_dir}")
    baseline = _split_paragraphs(Path(args.baseline))
    report = fertility_report(corpora, baseline, encode, threshold=args.threshold)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"report -> {out}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
