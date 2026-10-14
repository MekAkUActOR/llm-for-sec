r"""T6 采购清洗（M2.5 备料）：Devign / Devign-lines / CVEfixes → C 层 clean。

上游（scripts/fetch_t6_datasets.ps1 已落 raw，provenance 见
data/corpora/raw/t6/provenance.json）：
  raw/t6/devign/   epicosy/devign tarball（Devign 论文数据镜像，MIT）
                   data/raw/dataset.json：27,318 函数级样本（FFmpeg/qemu）
  raw/t6/devign-lines/  DetectVul/devign parquet（行级漏洞标注衍生，
                   FGCS 2024 DetectVul 论文；上游 Devign MIT）
  raw/t6/cvefixes/ hitoshura25/cvefixes parquet（CVEfixes v1.0.8 commit 级
                   提取；canonical Zenodo DOI 10.5281/zenodo.13118970 CC-BY-4.0）

输出（data/corpora/clean/，t6_ 前缀）：
  t6_devign.jsonl        函数级全量（label=vulnerable/clean）
  t6_devign_lines.jsonl  行级标注（target=1 且 vul_lines 非空；>> 前缀标记）
  t6_cvefixes.jsonl      CVE→修复 commit→diff（过滤空 diff 与 >256KB 噪声
                         diff；单 diff 截断 24KB）

纪律：评估/探针路径零引用（源码断言）；行级 line_no 已抽样验证映射
raw func 行（1-based，324/324 命中）；est_tokens 用 Qwen2.5-1.5B 分词器
1,000 样本外推；全部输出过生产断言（JSON 合法/非空/docs 计数/探针路径
零引用）。污染 8-gram 检查独立跑 scripts/check_t6_contamination.py。

用法：.venv\\Scripts\\python.exe scripts\\build_t6_clean.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path

_CTRL_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff]")


def sanitize(s: str) -> str:
    """剔除控制字符与孤代理（实测 CVEfixes diff 含 NUL；\t\n\r 保留）。"""
    return _CTRL_RE.sub("", s)

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyarrow.parquet as pq  # noqa: E402

RAW = ROOT / "data" / "corpora" / "raw" / "t6"
CLEAN = ROOT / "data" / "corpora" / "clean"
RNG_SEED = 20260928
DIFF_MAX_TOTAL = 256 * 1024   # 超过即整行丢弃（vendored churn 噪声）
DIFF_CAP = 24 * 1024          # 保留部分的截断上限
DESC_CAP = 1500
MSG_CAP = 400
FUNC_CAP = 20 * 1024          # devign-lines 超长函数截断
SAMPLE_N = 1000               # est_tokens 抽样数

# —— 生产断言 0：评估/探针路径零引用（红线）——
FORBIDDEN_PATHS = ("data/probes", "data/heldout")
_src = Path(__file__).read_text(encoding="utf-8")
for _fp in FORBIDDEN_PATHS:
    # 本脚本只允许以常量形式出现（断言本身），不允许引用其文件内容
    assert _src.count(_fp) <= 2, f"eval path referenced: {_fp}"


def write_jsonl(path: Path, docs: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            f.write(json.dumps({"text": t}, ensure_ascii=False) + "\n")


def assert_clean(path: Path, docs: list[str]) -> None:
    """生产断言：逐行 JSON 合法、text 非空、无 NUL/孤代理。"""
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            j = json.loads(line)
            t = j["text"]
            assert isinstance(t, str) and t.strip(), f"{path}:{n} empty text"
            assert "\x00" not in t, f"{path}:{n} NUL byte"
            t.encode("utf-8")  # 孤代理会在此抛错
            n += 1
    assert n == len(docs), f"{path}: {n} lines != {len(docs)} docs"


def load_exclusions() -> dict[str, set[str]]:
    """读污染检查报告的 flagged_hashes（内容 sha256）——沿 §5 教训用
    哈希清单而非枚举序，防 doc_index 耦合。报告不存在 → 空集（首轮）。"""
    rep_path = ROOT / "reports" / "t6-contamination-check.json"
    out: dict[str, set[str]] = {}
    if rep_path.exists():
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        for name, t in rep.get("targets", {}).items():
            out[name] = set(t.get("flagged_hashes") or [])
    return out


def apply_exclusions(name: str, docs: list[str]) -> tuple[list[str], int]:
    excl = load_exclusions().get(name, set())
    if not excl:
        return docs, 0
    kept = [d for d in docs
            if hashlib.sha256(d.encode("utf-8")).hexdigest() not in excl]
    return kept, len(docs) - len(kept)


def est_tokens(docs: list[str]) -> int:
    """Qwen2.5-1.5B 分词器抽样外推（确定性 seed）。"""
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(
        "Qwen/Qwen2.5-1.5B", trust_remote_code=False)
    rng = random.Random(RNG_SEED)
    sample = rng.sample(docs, min(SAMPLE_N, len(docs)))
    total = sum(len(tok(t, add_special_tokens=False)["input_ids"])
                for t in sample)
    return round(total / len(sample) * len(docs))


# ================================================================ Devign ===
def build_devign() -> tuple[list[str], dict]:
    src = (RAW / "devign" / "devign-master" / "data" / "raw" / "dataset.json")
    data = json.load(open(src, encoding="utf-8"))
    docs, n_vul = [], 0
    for i, x in enumerate(data, 1):
        label = "vulnerable" if x["target"] == 1 else "clean"
        n_vul += x["target"] == 1
        docs.append(
            f"Devign function-level sample {i} (project: {x['project']}; "
            f"commit: {x['commit_id']}; target label: {label}).\n\n"
            f"{x['func']}")
    stats = {"rows": len(data), "vulnerable": n_vul,
             "projects": sorted({x["project"] for x in data})}
    return docs, stats


# ========================================================= Devign 行级 ===
def build_devign_lines() -> tuple[list[str], dict]:
    docs = []
    per_split = {}
    for split in ("train", "validation", "test"):
        t = pq.read_table(RAW / "devign-lines" / f"{split}.parquet")
        n_rows = n_annot = 0
        for i in range(t.num_rows):
            if not t.column("target")[i].as_py():
                continue
            n_rows += 1
            vl = t.column("vul_lines")[i].as_py() or {}
            nos = [n for n in (vl.get("line_no") or []) if n]
            if not nos:
                continue
            func = t.column("func")[i].as_py()
            lines = func.split("\n")
            if max(nos) > len(lines):     # 行号越界 → 跳过（防脏标注）
                continue
            n_annot += 1
            flagged = set(nos)
            out = []
            for ln, text in enumerate(lines, 1):
                out.append((">> " if ln in flagged else "") + text)
            body = "\n".join(out)
            if len(body) > FUNC_CAP:
                body = body[:FUNC_CAP] + "\n[function truncated]"
            docs.append(
                f"Devign line-annotated vulnerable function (project: "
                f"{t.column('project')[i].as_py()}; commit: "
                f"{t.column('commit_id')[i].as_py()}; split: {split}): "
                f"{len(flagged)} vulnerable lines flagged with '>>' "
                f"prefix.\n\n{body}")
        per_split[split] = {"target_true": n_rows, "annotated": n_annot}
    return docs, {"per_split": per_split}


# =============================================================== CVEfixes ===
def _desc_en(v) -> str:
    """cve_description 实测为 list<struct> 的 str() repr（单引号 dict 列表
    字符串），需 ast 还原后取 en 值；兼容原生 list。"""
    import ast
    if isinstance(v, str) and v.strip().startswith("["):
        try:
            v = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    if isinstance(v, list):
        for it in v:
            if isinstance(it, dict) and it.get("lang") == "en":
                return str(it.get("value") or "")
        if v and isinstance(v[0], dict):
            return str(v[0].get("value") or "")
    return str(v or "")


def build_cvefixes() -> tuple[list[str], dict]:
    docs = []
    seen: set = set()
    n_dupe = n_nodiff = n_giant = 0
    langs: dict[str, int] = {}
    for f in sorted((RAW / "cvefixes").glob("*.parquet")):
        t = pq.read_table(f)
        for i in range(t.num_rows):
            g = {c: t.column(c)[i].as_py() for c in t.column_names}
            cve, chash = g["cve_id"], g["hash"]
            key = (cve, chash, json.dumps(g.get("file_paths") or []))
            if key in seen:
                n_dupe += 1
                continue
            seen.add(key)
            diff = sanitize(g.get("diff_with_context") or "")
            if not diff.strip():
                n_nodiff += 1
                continue
            if len(diff) > DIFF_MAX_TOTAL:
                n_giant += 1
                continue
            lang = g.get("language") or "Unknown"
            langs[lang] = langs.get(lang, 0) + 1
            sev = g.get("severity")
            sev_s = str(sev).strip() if sev and str(sev) != "nan" else ""
            sev_txt = f", severity {sev_s}" if sev_s else ""
            pub = str(g.get("published_date") or "")[:10]
            pub_txt = f", published {pub}" if pub else ""
            desc = sanitize(_desc_en(g.get("cve_description")))[:DESC_CAP].strip()
            msg = sanitize(str(g.get("commit_message") or "")).strip()[:MSG_CAP]
            files = g.get("file_paths") or []
            files_txt = "\n".join(f"- {p}" for p in files[:10])
            if len(files) > 10:
                files_txt += f"\n- (+{len(files) - 10} more files)"
            if len(diff) > DIFF_CAP:
                diff = diff[:DIFF_CAP] + "\n[diff truncated]"
            cwe = sanitize(str(g.get("cwe_id") or "")).strip()
            # 注意：不内联 cwe_name——官方 CWE 名称（如 CWE-22 "Improper
            # Limitation of a Pathname..."）与 sec 探针（GHSL 通告）共享
            # 标准文本，8-gram 匹配器 v3 曾因此报 2,248 例样板级命中
            # （LCS 61-99 字符 == CWE 名称长度；报告
            # reports/t6-contamination-check.json）。CWE 名可由本项目
            # c0_cwe.jsonl（969 条）按 cwe_id 恢复，clean 侧只留编号。
            cwe_txt = cwe if cwe else "CWE not assigned"
            parts = [
                f"CVEfixes record {cve} ({cwe_txt}{sev_txt}{pub_txt}): fix "
                f"commit {chash} in {g.get('repo_url') or 'unknown repo'} "
                f"(language: {lang}).",
                f"Description: {desc}" if desc else "",
                f"Commit message: {msg}" if msg else "",
                f"Files changed:\n{files_txt}" if files_txt else "",
                f"Fix diff:\n{diff}",
            ]
            docs.append("\n".join(p for p in parts if p))
    stats = {"kept": len(docs), "dupes_dropped": n_dupe,
             "empty_diff_dropped": n_nodiff, "giant_diff_dropped": n_giant,
             "top_langs": sorted(langs.items(), key=lambda kv: -kv[1])[:8]}
    return docs, stats


# ==================================================================== main ===
def main() -> int:
    out = {}

    docs, st = build_devign()
    docs, n_ex = apply_exclusions("t6_devign", docs)
    write_jsonl(CLEAN / "t6_devign.jsonl", docs)
    assert_clean(CLEAN / "t6_devign.jsonl", docs)
    st["contam_excluded"] = n_ex
    st["est_tokens"] = est_tokens(docs)
    st["total_chars"] = sum(len(d) for d in docs)
    out["t6_devign"] = st
    print(f"t6_devign: {len(docs)} docs (excl {n_ex}), "
          f"est_tokens {st['est_tokens']:,}")

    docs, st = build_devign_lines()
    docs, n_ex = apply_exclusions("t6_devign_lines", docs)
    write_jsonl(CLEAN / "t6_devign_lines.jsonl", docs)
    assert_clean(CLEAN / "t6_devign_lines.jsonl", docs)
    st["contam_excluded"] = n_ex
    st["est_tokens"] = est_tokens(docs)
    st["total_chars"] = sum(len(d) for d in docs)
    out["t6_devign_lines"] = st
    print(f"t6_devign_lines: {len(docs)} docs (excl {n_ex}), "
          f"est_tokens {st['est_tokens']:,}")

    docs, st = build_cvefixes()
    docs, n_ex = apply_exclusions("t6_cvefixes", docs)
    write_jsonl(CLEAN / "t6_cvefixes.jsonl", docs)
    assert_clean(CLEAN / "t6_cvefixes.jsonl", docs)
    st["contam_excluded"] = n_ex
    st["est_tokens"] = est_tokens(docs)
    st["total_chars"] = sum(len(d) for d in docs)
    out["t6_cvefixes"] = st
    print(f"t6_cvefixes: {len(docs)} docs "
          f"(drop dupes {st['dupes_dropped']}, no-diff {st['empty_diff_dropped']}, "
          f"giant {st['giant_diff_dropped']}, contam-excl {n_ex}), "
          f"est_tokens {st['est_tokens']:,}")

    (RAW / "clean-stats.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("stats -> data/corpora/raw/t6/clean-stats.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
