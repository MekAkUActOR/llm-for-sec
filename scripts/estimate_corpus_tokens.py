"""语料 token 估算工具（抽样 + 外推，固定随机种子，全程只读）。

用途
----
`data/corpora/manifest.jsonl` 里有一批 `status="procured"`、`est_tokens=0` 的行
（2026-09-30 对账共 16 行，盘上原始体量 1,166.5 MB）。本工具**不改任何数据文件**，
只按固定随机种子对盘上原始文件抽样，用 Qwen tokenizer 实测样本 token 数，
再按"样本均值 × 全量记录数"外推该源的真实 token 量级，并给出不确定性。

方法（可复算）
--------------
1. **口径**：对每个源目录递归枚举文件；按扩展名判定格式：
   - 行式（`.jsonl/.jsonl.gz/.jsonl.xz/.csv/.tsv`）：单遍流式读，**蓄水池抽样**
     （reservoir sampling，无放回）取 `--per-file-sample` 条记录，同时得到总记录数 N；
   - 整文件 JSON（`.json`）：`json.load` 后按 list 元素或 dict 值取记录，得到 N；
   - Parquet（`.parquet`）：`pyarrow` 读行数 N，按行组顺序取前若干行组内的记录做样本；
   - 其它扩展名：跳过并登记（不猜测）。
2. **记录 → 文本**：一行/一条记录里的**全部字符串叶子**用 `\n` 连接
   （行式文件取整行所有字段；JSON 取递归后的字符串值）。这是本工具唯一的、
   写死在 `record_text()` 里的口径——换口径必须改版本号。
3. **token 计数**：Qwen3-0.6B-Base 的 `tokenizer.json`（默认从
   `.cache/huggingface/hub/models--Qwen--Qwen3-0.6B-Base/snapshots/*/tokenizer.json`
   自动查找），`add_special_tokens=False`。不加载模型权重，纯 CPU。
4. **外推**：`T_hat = N * mean(tokens_per_record)`；
   标准误 `SE = s / sqrt(k)`（k = 样本量），无放回有限总体校正
   `sqrt((N-k)/(N-1))`（N>k 时；N=k 即全量口径 ⇒ SE=0、CI 退化为点），
   95% CI = `T_hat ± 1.96 * SE * N`。
   不确定性同时以 `ci95` 与 `rel_ci95` 输出（每文件），
   **只覆盖"同一文件内记录间"的抽样方差**，不含字段口径与格式解析误差。
5. **确定性**：同一 `--seed` + 同一盘上文件 ⇒ 同一抽样 ⇒ 同一数字。
6. **重复副本**：`--hash-duplicates` 会对每个被测文件算 sha256 并登记**字节级重复副本组**
   （用于回答"盘上体积里有多少是重复副本"）。

用法
----
    # manifest 里全部 status=procured 且 est_tokens=0 的行（默认）
    python scripts/estimate_corpus_tokens.py --out reports/corpus-token-estimate.json

    # 只测指定 id
    python scripts/estimate_corpus_tokens.py --ids wildjailbreak,pku-saferlhf

    # 只测显式目录（不读 manifest）
    python scripts/estimate_corpus_tokens.py --dirs data/corpora/raw/m2/xstest

    # 调抽样量 / 种子 + 登记重复副本
    python scripts/estimate_corpus_tokens.py --per-file-sample 500 --seed 20260930 --hash-duplicates

纪律
----
- 只读：本脚本不写 `data/` 下任何路径；`--out` 是唯一的写出口，默认不写（打 stdout）。
- 不触碰 `data/probes/**` 与 `data/heldout/**`（两者在 `--dirs` 与 manifest 解析路径上都会被拒绝）。
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import lzma
import math
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
TOOL_VERSION = "1.0-2026-09-30"
CONVENTION = "join_all_string_leaves_with_newline"
FORBIDDEN_PREFIXES = ("data/probes", "data/heldout")

LINE_EXTS = {".jsonl", ".csv", ".tsv"}
GZ_EXTS = {".gz"}
XZ_EXTS = {".xz"}
#: 允许的复合扩展名（先看最长的后缀组合）
KNOWN_SUFFIXES = (
    ".jsonl.gz", ".jsonl.xz", ".json.gz", ".csv.gz", ".tsv.gz", ".tsv.xz",
    ".jsonl", ".json", ".csv", ".tsv", ".parquet", ".txt", ".md",
)


# ----------------------------------------------------------------- tokenizer
def find_tokenizer(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        raise SystemExit(f"tokenizer not found: {p}")
    hits = sorted((ROOT / ".cache/huggingface/hub").glob(
        "models--Qwen--Qwen3-0.6B-Base/snapshots/*/tokenizer.json"))
    if not hits:
        raise SystemExit(
            "找不到 Qwen3-0.6B-Base tokenizer.json，请用 --tokenizer 显式指定")
    return hits[0]


class Tok:
    """薄封装：优先 tokenizers.Tokenizer.from_file，退化到 transformers。"""

    def __init__(self, path: Path):
        self.path = path
        self.backend = None
        try:
            from tokenizers import Tokenizer  # type: ignore
            self._enc = Tokenizer.from_file(str(path))
            self.backend = "tokenizers"
        except Exception:  # noqa: BLE001
            from transformers import AutoTokenizer  # type: ignore
            self._enc = AutoTokenizer.from_pretrained(
                str(path.parent), use_fast=True)
            self.backend = "transformers"

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self.backend == "tokenizers":
            return len(self._enc.encode(text, add_special_tokens=False).ids)
        return len(self._enc(text, add_special_tokens=False)["input_ids"])


# ----------------------------------------------------------------- extraction
def record_text(obj) -> str:
    """口径：把一条记录里所有字符串叶子用 \\n 连接（写死，换口径要改版本号）。"""
    out: list[str] = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        # 数字/布尔/None 不计入（不产生 token 语义）

    walk(obj)
    return "\n".join(out)


def row_text(row) -> str:
    """行式文件的整行文本：所有字段用 \\n 连接。"""
    return record_text(list(row))


# ----------------------------------------------------------------- readers
def suffix_of(name: str) -> str:
    low = name.lower()
    for s in KNOWN_SUFFIXES:
        if low.endswith(s):
            return s
    return Path(low).suffix


def open_text(path: Path, suffix: str):
    if suffix.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    if suffix.endswith(".xz"):
        return lzma.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "rt", encoding="utf-8", errors="replace", newline="")


def sample_line_file(path: Path, suffix: str, k: int, rng: random.Random,
                     tok: Tok) -> dict:
    """单遍流式 + 蓄水池抽样。返回 records/total/样本 token 列表。"""
    is_csv = suffix.startswith(".csv") or suffix.startswith(".tsv")
    delim = "\t" if ".tsv" in suffix else ","
    reservoir: list[str] = []
    tokens: list[int] = []
    total = 0
    reservoir_texts: list[str] = []
    with open_text(path, suffix) as fh:
        if is_csv:
            reader = csv.reader(fh, delimiter=delim)
            stream = (row_text(r) for r in reader)
        else:
            stream = (record_text(_safe_json(line)) for line in fh)
        for text in stream:
            if text is None:
                continue
            total += 1
            if len(reservoir) < k:
                reservoir.append(text)
            else:
                j = rng.randrange(total)
                if j < k:
                    reservoir[j] = text
    reservoir_texts = reservoir
    tokens = [tok.count(t) for t in reservoir_texts]
    return {"records": total, "sample_n": len(tokens), "sample_tokens": tokens}


def _safe_json(line: str):
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return line  # 退化：把整行当文本（并会在 notes 里体现为空文本行比例）


def sample_whole_json(path: Path, k: int, rng: random.Random, tok: Tok) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if isinstance(obj, list):
        records = [record_text(x) for x in obj]
    elif isinstance(obj, dict):
        # 顶层 dict：若是 {id: payload} 形态，按值取记录
        vals = list(obj.values())
        if vals and all(isinstance(v, (dict, list, str)) for v in vals):
            records = [record_text(v) for v in vals]
        else:
            records = [record_text(obj)]
    else:
        records = [record_text(obj)]
    n = len(records)
    idx = list(range(n))
    if n > k:
        idx = rng.sample(idx, k)
    texts = [records[i] for i in idx]
    return {"records": n, "sample_n": len(texts),
            "sample_tokens": [tok.count(t) for t in texts]}


def sample_parquet(path: Path, k: int, rng: random.Random, tok: Tok) -> dict:
    import pyarrow.parquet as pq  # 局部导入：缺少 pyarrow 时其它源仍可用
    pf = pq.ParquetFile(path)
    n = pf.metadata.num_rows
    # 顺序读前若干行组直到凑够 k 行（确定性，不依赖随机 IO）
    texts: list[str] = []
    for batch in pf.iter_batches(batch_size=max(k, 64)):
        for row in batch.to_pylist():
            texts.append(record_text(row))
            if len(texts) >= k:
                break
        if len(texts) >= k:
            break
    if len(texts) > k:
        texts = texts[:k]
    return {"records": n, "sample_n": len(texts),
            "sample_tokens": [tok.count(t) for t in texts]}


def collect_files(root: Path) -> tuple[list[Path], dict]:
    """递归枚举可读文件；返回 (可测文件, 跳过登记)。"""
    files, skipped = [], {}
    if root.is_file():
        cand = [root]
    else:
        cand = sorted(p for p in root.rglob("*") if p.is_file())
    for p in cand:
        s = suffix_of(p.name)
        if s in (".parquet",) or any(p.name.lower().endswith(x)
                                     for x in (".jsonl", ".json", ".csv", ".tsv",
                                               ".jsonl.gz", ".jsonl.xz", ".txt", ".md")) \
                or p.name.lower().endswith((".csv.gz", ".tsv.gz", ".tsv.xz", ".json.gz")):
            files.append(p)
        else:
            skipped.setdefault(s or "<none>", 0)
            skipped[s or "<none>"] += 1
    return files, skipped


# ----------------------------------------------------------------- statistics
def extrapolate(total_n: int, toks: list[int]) -> dict:
    k = len(toks)
    if k == 0 or total_n == 0:
        return {"total_tokens": 0, "mean_tokens_per_record": None,
                "sd": None, "se": None, "ci95": [0, 0], "rel_ci95": None,
                "sample_is_census": False}
    mean = sum(toks) / k
    if k > 1:
        var = sum((x - mean) ** 2 for x in toks) / (k - 1)
        sd = math.sqrt(var)
        se = sd / math.sqrt(k)
        if total_n > k:
            se *= math.sqrt((total_n - k) / (total_n - 1))
        else:
            se = 0.0          # 全量口径（census）：无抽样方差
    else:
        sd = se = None
    total = mean * total_n
    if se is None:
        ci = [total, total]
        rel = None
    elif se == 0.0:
        ci = [total, total]
        rel = 0.0
    else:
        half = 1.96 * se * total_n
        ci = [max(0.0, total - half), total + half]
        rel = (half / total) if total else None
    return {
        "total_tokens": int(round(total)),
        "mean_tokens_per_record": round(mean, 3),
        "sd": round(sd, 3) if sd is not None else None,
        "se": round(se, 4) if se is not None else None,
        "ci95": [int(round(ci[0])), int(round(ci[1]))],
        "rel_ci95": round(rel, 4) if rel is not None else None,
        "sample_is_census": total_n <= k,
    }


# ----------------------------------------------------------------- manifest
def procured_zero_rows(manifest: Path, ids: list[str] | None) -> list[dict]:
    rows = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("status") != "procured" or int(d.get("est_tokens") or 0) != 0:
            continue
        if ids and d["id"] not in ids:
            continue
        rows.append(d)
    return rows


def dir_of(row: dict) -> Path | None:
    for f in row.get("files") or []:
        p = (ROOT / f.replace("\\", "/")).resolve()
        if p.exists():
            return p
    return None


# ----------------------------------------------------------------- driver
def measure_dir(root: Path, tok: Tok, k: int, seed: int, verbose: bool,
                hash_dupes: bool = False) -> dict:
    rng = random.Random(seed)
    files, skipped = collect_files(root)
    per_file, all_tokens, total_records = [], [], 0
    notes: list[str] = []
    digests: dict[str, list[str]] = {}
    for p in files:
        s = suffix_of(p.name)
        try:
            if s == ".parquet":
                r = sample_parquet(p, k, rng, tok)
            elif s.endswith((".jsonl", ".csv", ".tsv")) or s.endswith((".gz", ".xz")):
                r = sample_line_file(p, s, k, rng, tok)
            elif s == ".json":
                r = sample_whole_json(p, k, rng, tok)
            else:
                r = sample_line_file(p, s, k, rng, tok)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{p.name}: 读取失败 {type(exc).__name__}: {exc}")
            continue
        if r["records"] == 0:
            notes.append(f"{p.name}: 0 条记录")
            continue
        ex = extrapolate(r["records"], r["sample_tokens"])
        entry = {
            "file": p.name, "bytes": p.stat().st_size,
            "format": s, "records": r["records"], "sample_n": r["sample_n"],
            "mean_tokens_per_record": ex["mean_tokens_per_record"],
            "census": ex["sample_is_census"],
            "rel_ci95": ex["rel_ci95"], "est_tokens": ex["total_tokens"],
        }
        if hash_dupes:
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            entry["sha256"] = h.hexdigest()
            digests.setdefault(h.hexdigest(), []).append(
                str(p.relative_to(ROOT)).replace("\\", "/"))
        per_file.append(entry)
        all_tokens.append((r["records"], ex["total_tokens"],
                           sum(r["sample_tokens"]), r["sample_n"]))
        total_records += r["records"]
        if verbose:
            print(f"    {p.name}: {r['records']:,} rec × "
                  f"{ex['mean_tokens_per_record']} tok = {ex['total_tokens']:,}",
                  file=sys.stderr)
    bytes_total = sum(f["bytes"] for f in per_file)
    tok_total = sum(t[1] for t in all_tokens)
    sample_tok = sum(t[2] for t in all_tokens)
    sample_n = sum(t[3] for t in all_tokens)
    if skipped:
        notes.append("跳过（非文本口径）: " +
                     ", ".join(f"{e}×{n}" for e, n in sorted(skipped.items())))
    n_census = sum(1 for f in per_file if f["census"])
    if n_census:
        notes.append(f"{n_census}/{len(per_file)} 个文件为全量口径（census，"
                     f"无抽样外推）；这些文件的 est_tokens 是精确值")
    dupes = {h: v for h, v in digests.items() if len(v) > 1}
    if dupes:
        notes.append("字节级重复副本（sha256 相同，est_tokens 存在重复计入）: " +
                     " | ".join(" == ".join(v) for v in dupes.values()))
    return {
        "path": str(root.relative_to(ROOT)).replace("\\", "/"),
        "files_measured": len(per_file),
        "files_census": n_census,
        "duplicate_groups": [v for v in dupes.values()],
        "bytes_on_disk_measured": bytes_total,
        "records": total_records,
        "sample_records": sample_n,
        "sample_tokens": sample_tok,
        "mean_tokens_per_record_pooled": (round(sample_tok / sample_n, 3)
                                          if sample_n else None),
        "bytes_per_token": (round(bytes_total / tok_total, 2)
                            if tok_total else None),
        "est_tokens": tok_total,
        "per_file": per_file,
        "notes": notes,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="语料 token 估算（抽样 + 外推，只读）")
    ap.add_argument("--manifest", default="data/corpora/manifest.jsonl")
    ap.add_argument("--ids", default=None,
                    help="逗号分隔的 manifest id 子集（默认=全部 procured&est_tokens=0）")
    ap.add_argument("--dirs", default=None,
                    help="逗号分隔的显式目录（相对仓库根）；给了就不读 manifest")
    ap.add_argument("--per-file-sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--tokenizer", default=None)
    ap.add_argument("--out", default=None,
                    help="JSON 输出路径（默认 stdout）")
    ap.add_argument("--hash-duplicates", action="store_true",
                    help="额外计算每个文件的 sha256，登记字节级重复副本")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    tok = Tok(find_tokenizer(args.tokenizer))
    ids = [s.strip() for s in args.ids.split(",")] if args.ids else None

    targets: list[tuple[str, Path]] = []          # (label, dir)
    rows_meta: dict[str, dict] = {}
    if args.dirs:
        for d in [s.strip() for s in args.dirs.split(",") if s.strip()]:
            rel = d.replace("\\", "/").rstrip("/")
            if rel.startswith(FORBIDDEN_PREFIXES):
                raise SystemExit(f"拒绝：{rel} 属禁用前缀（{FORBIDDEN_PREFIXES}）")
            targets.append((Path(rel).name, (ROOT / rel).resolve()))
    else:
        for d in procured_zero_rows(ROOT / args.manifest, ids):
            p = dir_of(d)
            if p is None:
                rows_meta[d["id"]] = {"error": "manifest files 路径在盘上不存在"}
                continue
            targets.append((d["id"], p))
            rows_meta[d["id"]] = {
                "declared_license": d.get("license"),
                "declared_domain": d.get("domain"),
                "declared_lang": d.get("lang"),
                "declared_docs": d.get("docs"),
                "declared_tier": d.get("tier"),
                "manifest_est_tokens": d.get("est_tokens"),
            }

    results = []
    grand = 0
    for label, path in targets:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith(FORBIDDEN_PREFIXES):
            raise SystemExit(f"拒绝：{rel} 属禁用前缀")
        if not args.quiet:
            print(f"[estimate] {label} <- {rel}", file=sys.stderr)
        m = measure_dir(path, tok, args.per_file_sample, args.seed,
                        verbose=not args.quiet, hash_dupes=args.hash_duplicates)
        m["id"] = label
        m.update(rows_meta.get(label, {}))
        # 与 manifest 声明的 docs 数对比（记录量纲核对）
        if rows_meta.get(label, {}).get("declared_docs"):
            m["records_vs_declared_docs"] = (
                m["records"] - int(rows_meta[label]["declared_docs"]))
        results.append(m)
        grand += m["est_tokens"]

    report = {
        "tool": "scripts/estimate_corpus_tokens.py",
        "tool_version": TOOL_VERSION,
        "text_convention": CONVENTION,
        "seed": args.seed,
        "per_file_sample": args.per_file_sample,
        "hash_duplicates": bool(args.hash_duplicates),
        "tokenizer": str(tok.path.relative_to(ROOT)).replace("\\", "/"),
        "tokenizer_backend": tok.backend,
        "method": {
            "sampling": "reservoir sampling (no replacement) for line files; "
                        "deterministic head rows for parquet; seeded index "
                        "sample for whole-file JSON",
            "extrapolation": "T_hat = N_records * mean(tokens_per_record); "
                             "95% CI = T_hat ± 1.96 * (s/sqrt(k)) * N "
                             "(with finite-population correction when N>k)",
            "uncertainty_note": "CI 只覆盖「同一文件内记录间」的抽样方差，"
                                "不含口径（字段选择）与格式解析误差",
        },
        "targets": results,
        "grand_total_est_tokens": grand,
        "grand_total_bytes_on_disk": sum(t["bytes_on_disk_measured"]
                                         for t in results),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"[estimate] wrote {out}", file=sys.stderr)
        print(f"[estimate] grand total est_tokens = {grand:,}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
