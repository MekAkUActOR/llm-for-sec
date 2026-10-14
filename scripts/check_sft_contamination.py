"""SFT 物料污染检查(docs/research/m2-sft-sources.md §4 方案,父会话 2026-09-26 指令)。

纪律:data/probes/v0.1.1(1,663 条)与 data/heldout/v0.2(153 条)**严禁入训练**,
含间接污染(数据集含同源条目)。本脚本对每个已采购 SFT 物料源跑三重检查:

  1. 精确子串:探针文档规范化后首 200 字符在候选文本中的出现(re.search
     交替正则,C 速度;抓整段逐字复制);
  2. 标题键:ais 探针(arXiv cs.AI 摘要)的标题匹配(抓摘要复制);
  3. 8-gram 两段式:预筛(单个探针与候选共享 ≥40 个**去重** 8-gram)+
     最长连续公共子串验证(≥60 规范化字符才判真;抓中段部分复制——
     prefix 检查只抓"探针开头 200 字"的复制,中段嵌入由本项兜住,
     功能词短语碰撞被 LCS 验证滤除);
  附:heldout v0.2 查询全文子串(153 条,查询被拷进候选即命中)。

输出:reports/sft-contamination-check-{sid}.json(沿 probe-ais-overlap 惯例):
  docs_scanned / 各法命中数 / flagged_docs(含索引与摘录)/ 建议(生成器侧剔除)。

用法:python scripts/check_sft_contamination.py [--sources sid,...] [--probe-dir ...]
"""
from __future__ import annotations

import argparse
import csv
import difflib
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE_DIR = ROOT / "data" / "probes" / "v0.1.1"
# 2026-09-30：新增 v0.3-gen（未见载体留出集，46 条）——它喂给
# gen_sft_exclusion_hashes.py 的排除正则；不收进来，采购期就不会排除这些 query，
# 留出集会被污染（reports/review-2026-09-30.md §4.4 的同类事故）。
# 2026-10-07：新增 v0.6-dilution（P0.6 稀释仪器载荷池，96 条风险载荷；
# reports/p0.6-dilution-instrument-design.md §11.4 接线要求）。
# 2026-10-14：新增 v0.7-jailbreak（P0.7 对话式越狱仪器，150 条；
# 隔离接线要求见 reports/p0.7-jailbreak-instrument-design.md §11.2）。
HELDOUT_DIRS = [ROOT / "data" / "heldout" / v
                for v in ("v0.2", "v0.2.1", "v0.3-gen", "v0.6-dilution",
                          "v0.7-jailbreak")]
RAW_M2 = ROOT / "data" / "corpora" / "raw" / "m2"
RAW_REF = ROOT / "data" / "corpora" / "raw" / "m2-reference"
OUT_DIR = ROOT / "reports"

NGRAM_N = 8
# 两段式 v3(2026-09-26 定稿;三代实现教训见 doc_probe_hits):
#   预筛:连续成员游程 ≥50 gram(≈57 字符文档侧连续;纯功能词噪声
#         游程经验 <40 gram);
#   验证:difflib 最长连续公共子串 ≥60 规范化字符(确认探针侧也连续;
#         通过 = 真共享子串,即句级以上复制)。
NGRAM_PREFILTER = 50
LCS_MIN_CHARS = 60
PREFIX_LEN = 200

_WS = re.compile(r"\s+")
_SEP_RUN = re.compile(r"([-_=*#~+.])\1{2,}")
_AIS_TITLE = re.compile(r"arXiv cs\.AI paper: (.+?)(?:\n\n|\. )")


# ---------------------------------------------------------------- 纯函数核心 --
def normalize(text: str) -> str:
    t = _WS.sub(" ", text).strip().lower()
    # 折叠 3+ 连续分隔符字符(ASCII 横线规则等):hh-rlhf 对话的
    # "----------" 分隔条与 GHSA 通告的横线规则曾造成 60-80 字符的
    # 样板级伪命中(2026-09-26 实测 11 条全属此类),折叠后消除。
    return _SEP_RUN.sub(r"\1", t)


def ngrams(text: str, n: int = NGRAM_N, stride: int = 1) -> list[str]:
    if len(text) < n:
        return []
    return [text[i: i + n] for i in range(0, len(text) - n + 1, stride)]


def build_ngram_index(probes: dict[str, str],
                      n: int = NGRAM_N) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for pid, text in probes.items():
        for g in set(ngrams(normalize(text), n)):
            idx.setdefault(g, []).append(pid)
    return idx


def doc_probe_hits(doc_text: str, ngram_index: dict[str, list[str]],
                   threshold: int = NGRAM_PREFILTER,
                   n: int = NGRAM_N) -> dict[str, tuple]:
    """连续成员游程:文档中**连续出现**且每个 gram 均属于同一探针 gram 集的最长游程。

    返回 {pid: (run_grams, run_end_pos)}(游程长度 ≥ threshold 的探针;
    run_end_pos = 游程最后一个 gram 的起始位置,用于验证窗口)。

    2026-09-26 教训(三代实现):
      v1 重复 gram 计数 → 阈值 60 仍全量虚报(" of the " 重复数十次);
      v2 去重计数 + 逐对 difflib LCS 验证 → 散点碰撞让多数文档进验证,
         LCS O(n*m) 病态慢(hh-rlhf 单源预估 3+ 小时);
      v3(本版)连续成员游程:O(doc_len × 平均成员数),游程 ≥ 阈值的
         探针再走窗口有界 difflib 确认真连续(探针侧也连续)。
    纯功能词噪声游程经验上 < 40 gram;真嵌入复制游程 ≥ 60 gram。
    """
    t = normalize(doc_text)
    grams = ngrams(t, n, 1)
    active: dict[str, int] = {}
    best: dict[str, tuple] = {}
    for pos, g in enumerate(grams):
        pids = ngram_index.get(g)
        if not pids:
            if active:
                active = {}
            continue
        pids = set(pids)
        new_active = {}
        for pid, ln in active.items():
            if pid in pids:
                ln += 1
                new_active[pid] = ln
                if ln > best.get(pid, (0, 0))[0]:
                    best[pid] = (ln, pos)
        for pid in pids:
            if pid not in new_active and pid not in active:
                new_active[pid] = 1
                if 1 > best.get(pid, (0, 0))[0]:
                    best[pid] = (1, pos)
        active = new_active
    return {pid: v for pid, v in best.items() if v[0] >= threshold}


def verify_shared_substring(doc_text: str, probe_text: str,
                            min_chars: int = LCS_MIN_CHARS,
                            window: tuple | None = None) -> int:
    """验证:候选与探针的最长连续公共子串长度(规范化后;≥min_chars 判真)。

    window=(run_grams, run_end_pos) 时仅取游程窗口(±100 字符边距)做
    difflib——真共享子串必然落在其游程窗口内(游程覆盖一切 ≥60 字符
    共享),窗口验证与全文验证等价但代价 O(window×probe) 有界。
    """
    a, b = normalize(doc_text), normalize(probe_text)
    if window is not None:
        run_grams, run_end = window
        # 游程文本 = chars [run_end - run_grams + 1, run_end + NGRAM_N)
        lo = max(0, run_end - run_grams + 1 - 100)
        hi = min(len(a), run_end + NGRAM_N + 100)
        a = a[lo:hi]
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    match = m.find_longest_match(0, len(a), 0, len(b))
    return match.size


def compile_alt_regex(strings: list[str]) -> re.Pattern:
    """转义交替正则(空列表 → 永不匹配)。"""
    if not strings:
        return re.compile(r"(?!x)x")  # never-match
    return re.compile("|".join(re.escape(s) for s in strings))


def extract_ais_title(text: str) -> str | None:
    m = _AIS_TITLE.match(text)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------- 基线构建 --
def load_probes() -> tuple[dict[str, str], dict[str, str], list[str]]:
    """→ (probes{id,text}, ais_titles{title:id}, heldout_queries)。"""
    probes, ais_titles = {}, {}
    for f in sorted(PROBE_DIR.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            j = json.loads(line)
            text = j.get("text") or ""
            pid = f"{f.stem}:{j.get('id', len(probes))}"
            probes[pid] = text
            if f.stem == "ais":
                t = extract_ais_title(text)
                if t:
                    ais_titles[t] = pid
    heldout = []
    for d in HELDOUT_DIRS:                      # 2026-09-30：v0.2 / v0.2.1 / v0.3-gen
        if not d.exists():
            continue
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    j = json.loads(line)
                    if j.get("query"):
                        heldout.append(normalize(j["query"]))
    return probes, ais_titles, heldout


# ---------------------------------------------------------------- 各源文档流 --
def _jsonl_gz_docs(p: Path):
    with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                j = json.loads(line)
                yield f"{j.get('chosen','')}\n{j.get('rejected','')}"


def _csv_docs(p: Path, cols: list[str]):
    with open(p, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            yield "\n".join(str(row.get(c, "")) for c in cols)


def docs_for(sid: str):
    """→ (doc 流, 每源说明)。物理读取 procured raw。"""
    if sid == "hh-rlhf-harmlessness":
        yield from _jsonl_gz_docs(RAW_M2 / "hh-rlhf" / "harmless-base" / "train.jsonl.gz")
        yield from _jsonl_gz_docs(RAW_M2 / "hh-rlhf" / "harmless-base" / "test.jsonl.gz")
    elif sid == "safety-prompts":
        for f in ["typical_safety_scenarios.json",
                  "instruction_attack_scenarios.json"]:
            j = json.loads((RAW_M2 / "safety-prompts" / f).read_text(encoding="utf-8"))
            for items in j.values():
                for it in items:
                    yield f"{it.get('prompt','')}\n{it.get('response','')}"
    elif sid == "safemtdata":
        for f in ["Attack_600.json", "SafeMTData_1K.json"]:
            j = json.loads((RAW_M2 / "safemtdata" / f).read_text(encoding="utf-8"))
            for it in j:
                parts = [it.get("plain_query", ""),
                         it.get("relationship", "")]
                parts += [str(q) for q in (it.get("multi_turn_queries") or [])]
                for c in it.get("conversations") or []:
                    parts.append(c.get("value", ""))
                yield "\n".join(parts)
    elif sid == "advbench":
        yield from _csv_docs(RAW_M2 / "advbench" / "harmful_behaviors.csv", ["goal"])
        yield from _csv_docs(RAW_M2 / "advbench" / "harmful_strings.csv", ["target"])
    elif sid == "harmbench":
        yield from _csv_docs(RAW_M2 / "harmbench" / "harmbench_behaviors_text_test.csv",
                             ["Behavior", "ContextString"])
    elif sid == "strongreject":
        yield from _csv_docs(RAW_M2 / "strongreject" / "strongreject_dataset.csv",
                             ["forbidden_prompt"])
    elif sid == "maliciousinstruct":
        import pyarrow.parquet as pq
        t = pq.read_table(RAW_M2 / "maliciousinstruct" /
                          "train-00000-of-00001.parquet")
        col = t.column("prompt").to_pylist()
        yield from col
    elif sid == "xstest":
        yield from _csv_docs(RAW_M2 / "xstest" / "xstest_prompts.csv", ["prompt"])
    elif sid == "or-bench":
        for f in sorted((RAW_M2 / "or-bench").glob("*.csv")):
            yield from _csv_docs(f, ["prompt"])
    elif sid == "trustllm-safety":
        for p in sorted((RAW_M2 / "trustllm" / "dataset").rglob("*.json")):
            for it in json.loads(p.read_text(encoding="utf-8")):
                yield "\n".join(str(v) for v in it.values() if isinstance(v, str))
    elif sid == "cvalues":
        for f in sorted((RAW_M2 / "cvalues").glob("*.json")):
            j = json.loads(f.read_text(encoding="utf-8"))
            for r in j:
                yield "\n".join(str(v) for v in r.values() if isinstance(v, str))
    elif sid == "tc260":
        import pyarrow.parquet as pq
        for f in sorted((RAW_REF / "tc260" / "public").glob("*.parquet")):
            t = pq.read_table(f, columns=["query"])
            yield from t.column("query").to_pylist()
    elif sid == "pku-saferlhf":
        for p in sorted((RAW_M2 / "pku-saferlhf" / "data").rglob("*.jsonl")):
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        j = json.loads(line)
                        yield "\n".join(str(j.get(k, "")) for k in
                                        ("prompt", "response_0", "response_1"))
    elif sid == "beavertails":
        import gzip as _gz
        import lzma
        for p in sorted((RAW_M2 / "beavertails").rglob("*.jsonl.gz")):
            with _gz.open(p, "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        j = json.loads(line)
                        yield f"{j.get('prompt','')}\n{j.get('response','')}"
        for p in sorted((RAW_M2 / "beavertails").rglob("*.jsonl.xz")):
            with lzma.open(p, "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        j = json.loads(line)
                        yield f"{j.get('prompt','')}\n{j.get('response','')}"
    elif sid == "wildjailbreak":
        for p in sorted((RAW_M2 / "wildjailbreak").rglob("*.tsv")):
            with open(p, encoding="utf-8", errors="replace", newline="") as f:
                rd = csv.reader(f, delimiter="\t")
                header = next(rd, None)
                if not header:
                    continue
                for row in rd:
                    if len(row) == len(header):
                        yield "\n".join(row)
    elif sid == "wildguardmix":
        import pyarrow.parquet as pq
        for p in sorted((RAW_M2 / "wildguardmix").rglob("*.parquet")):
            t = pq.read_table(p)
            cols = [c for c in ("prompt", "adversarial", "response")
                    if c in t.column_names]
            for row in t.select(cols).to_pylist():
                yield "\n".join(str(v) for v in row.values())
    else:
        raise KeyError(sid)


ALL_SOURCES = ["hh-rlhf-harmlessness", "safety-prompts", "safemtdata",
               "advbench", "harmbench", "strongreject", "maliciousinstruct",
               "xstest", "or-bench", "trustllm-safety", "cvalues", "tc260",
               "pku-saferlhf", "beavertails", "wildjailbreak", "wildguardmix"]


# ---------------------------------------------------------------- 主流程 --
def check_source(sid: str, probes: dict[str, str], ngram_index: dict,
                 prefix_re: re.Pattern, title_re: re.Pattern,
                 heldout_re: re.Pattern) -> dict:
    scanned = flagged = 0
    method_hits = {"prefix": 0, "title": 0, "ngram": 0, "heldout": 0}
    flagged_docs = []
    for i, doc in enumerate(docs_for(sid)):
        scanned += 1
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
        if heldout_re.search(t):
            methods.append("heldout")
            method_hits["heldout"] += 1
        hits = doc_probe_hits(doc, ngram_index)  # 连续成员游程预筛
        if hits:
            verified = {}
            for pid, win in hits.items():
                lcs = verify_shared_substring(doc, probes[pid], window=win)
                if lcs >= LCS_MIN_CHARS:
                    verified[pid] = {"membership_run_grams": win[0],
                                     "lcs_chars": lcs}
            if verified:
                methods.append("ngram")
                method_hits["ngram"] += 1
                detail["probe_overlap_verified"] = verified
        if methods:
            flagged += 1
            if len(flagged_docs) < 50:
                flagged_docs.append({
                    "doc_index": i, "methods": methods,
                    "excerpt": doc[:120].replace("\n", " ")[:120], **detail})
    return {"source": sid, "docs_scanned": scanned, "docs_flagged": flagged,
            "method_hits": method_hits, "flagged_docs": flagged_docs,
            "action": ("clean - no probe/heldout overlap"
                       if flagged == 0 else
                       f"exclude {flagged} flagged docs at generator side "
                       f"(indices in flagged_docs; verify before exclusion)")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="SFT contamination check vs probes/heldout")
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    args = ap.parse_args(argv)

    probes, ais_titles, heldout = load_probes()
    print(f"probes: {len(probes)}, ais titles: {len(ais_titles)}, "
          f"heldout queries: {len(heldout)}", flush=True)
    ngram_index = build_ngram_index(probes)
    print(f"ngram index: {len(ngram_index):,} keys", flush=True)
    prefix_re = compile_alt_regex(
        [normalize(t)[:PREFIX_LEN] for t in probes.values() if len(normalize(t)) >= PREFIX_LEN])
    title_re = compile_alt_regex(
        [normalize(t) for t in ais_titles if len(t) >= 16])
    heldout_re = compile_alt_regex([q for q in heldout if len(q) >= 12])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for sid in [s.strip() for s in args.sources.split(",") if s.strip()]:
        res = check_source(sid, probes, ngram_index, prefix_re, title_re, heldout_re)
        out = OUT_DIR / f"sft-contamination-check-{sid}.json"
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"  {sid:24s} scanned={res['docs_scanned']:>7,} "
              f"flagged={res['docs_flagged']:>3} "
              f"{res['method_hits']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
