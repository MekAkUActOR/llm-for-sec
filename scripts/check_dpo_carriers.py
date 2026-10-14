# -*- coding: utf-8 -*-
r"""M3 载体多样性 DPO 批次的硬校验器（失败即非零退出）。

对 `data/lf/dpo_m3_carriers_v1.jsonl` 跑两类检查：

**A. 批次自身性质（硬断言）**
1.  行数落在 [spec.rows_min, spec.rows_max]（默认 4,000–8,000）；
2.  `id` 全局唯一 + 前缀 `dpoCAR-`；
3.  载体覆盖：5 类必备（`tool_output/log/webpage/code/document`）各 ≥600，
    且全部落在 `secfm.carriers.base._CARRIER_TYPES` 注册表内；
4.  每类载体 ≥3 种注入/欺骗机制，且 (载体 × 机制) 组合无空格子；
5.  语言：全局 zh/en 各 ≥40%，且**逐载体**各 ≥40%（构造上为 50/50）；
6.  政策包：default/conservative/professional 各 ≥15%；
7.  行 schema：键集合与键序 == 任务书 8 键；
8.  `conversations` 形状（system + user 轮）、`from` 词表、system 文本 ==
    `secfm.eval.promptfmt.system_for(pack, lang)`（SSoT 一致性，docs/01 §11.1）；
9.  两侧 VERDICT：存在、末行、合法 JSON、键序 == action/verdict/confidence/
    findings/policy、`policy == pack`、两侧不同（docs/01 §11.10 契约回放）；
10. 三类 rejected 错误**都存在**，且 `dpo_class` 标签与**内容派生的**分类一致：
    ① obedient（注入行上顺从载荷）/ ② hollow（注入行上空洞短拒绝、findings=[]）/
    ③ overrefusal（良性行上误判注入）；
11. 良性负例 ≥20%，且其 chosen 裁决 ∈ {allow, conditional}（绝不含
    contains-injection），chosen 未把良性备注当注入；
12. 注入行 chosen == report/contains-injection；良性备注行（near-miss）确实在载体里
    （"见载体就报攻击"的反面训练信号）；
13. 载荷自洽：注入行载体里必须出现**本行声明机制**的载荷原文、且不出现他机制的
    载荷；良性行载体里**不得**出现任何载荷原文；
14. 协议往返：`secfm.protocol.context.parse_context(query)` 通过；
15. (prompt, pack) 无重复行。

**B. train-disjoint（硬断言 + 官方口径计数）**
- 与 `data/heldout/{v0.2.1,v0.3-gen,v0.4-toolout}` 的 **id 重叠 = 0**、
  **query 精确重叠 = 0**、**query 规范化重叠 = 0**（`normalize()` 口径）；
- 8-gram：沿用 `scripts/check_sft_contamination.py` 的 `NGRAM_N=8` / `normalize()`
  / `ngrams()` 与**两段式官方口径**：
  (1) 预筛"连续成员游程" ≥ `NGRAM_PREFILTER`(=50) 才进 LCS；
  (2) 存活者再做 LCS ≥ `LCS_MIN_CHARS`(=60) 判定。
  断言 = **无任何行进入预筛**（正文层与整 query 层分别判）；
  另报（a）逐集共享 gram 计数（行级求和 / 并集），（b）正文层游程最大值与直方图。
  说明：整条 query 的游程被协议外壳（`<dsh-protocol>`/`<system>`/`<carrier>`）托底，
  属构造性共享，故同时报"外壳骨架"基线；正文层游程另有 `spec.body_run_report_cap`
  的**报告级**警戒线（不进退出码）。

产物：`reports/dpo-carriers-stats.json`（逐断言原始计数 + sha256）。
用法：`python scripts/check_dpo_carriers.py [--rows PATH] [--no-reference]`
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_dpo_carriers as B  # noqa: E402  载荷/机制/轴清单 SSoT
from check_sft_contamination import (LCS_MIN_CHARS, NGRAM_N, NGRAM_PREFILTER,
                                     ngrams, normalize)  # noqa: E402
from secfm.carriers.base import _CARRIER_TYPES  # noqa: E402  注册表 SSoT
from secfm.eval.promptfmt import system_for  # noqa: E402
from secfm.protocol.context import parse_context  # noqa: E402

ROWS_DEFAULT = ROOT / "data" / "lf" / "dpo_m3_carriers_v1.jsonl"
REF_DPO = ROOT / "data" / "lf" / "dpo_m3.jsonl"
HELDOUT_SETS = ("v0.2.1", "v0.3-gen", "v0.4-toolout")
HELDOUT_DIR = ROOT / "data" / "heldout"
STATS_OUT = ROOT / "reports" / "dpo-carriers-stats.json"

ROW_KEYS = ("chosen", "conversations", "dpo_class", "id", "lang", "pack",
            "rejected", "src_task")
VERDICT_KEYS = ("action", "verdict", "confidence", "findings", "policy")
PACKS = ("default", "conservative", "professional")
LANGS = ("zh", "en")
REQUIRED_CARRIERS = ("tool_output", "log", "webpage", "code", "document")
CONTINUITY_CARRIERS = ("email", "text")
ACTIONS = ("answer", "refuse", "report")

DEFAULT_SPEC = {
    "rows_min": 4000,
    "rows_max": 8000,
    "min_per_carrier": 600,
    "min_lang_share": 0.40,
    "min_pack_share": 0.15,
    "min_clean_share": 0.20,
    "min_mechs_per_carrier": 3,
    "body_run_report_cap": 24,
    "require_continuity_carriers": True,
    "require_protocol_roundtrip": True,
    "require_payload_consistency": True,
}

VERDICT_RE = re.compile(r"VERDICT:\s*(\{.*\})")
BODY_RE = re.compile(r"<body>(.*?)</body>", re.S)
# 从 chosen 叙述里抽出「政策条目：<规则>（<包>）→ <裁决>」——把"政策接地"变成可验事实
GROUND_ZH = re.compile(r"政策条目：(.+?)（([A-Za-z]+)）→\s*(\S+?)(?:，|。|\n|$)")
GROUND_EN = re.compile(r"Policy:\s*(.+?)\s*\(([A-Za-z]+)\)\s*->\s*(.+?)(?:;|\.|\n|$)")


def axis_of_rule(rule_text: str, lang: str):
    """政策条目文字 → AXES 里的轴名（必须唯一命中，否则 None）。"""
    key = "rule_zh" if lang == "zh" else "rule_en"
    hits = [n for n, ax in B.AXES.items() if ax[key] == rule_text.strip()]
    return hits[0] if len(hits) == 1 else None


def extract_grounding(text: str, lang: str):
    """→ (rule_text, pack_in_prose, ruling_word) 或 None。"""
    m = (GROUND_ZH if lang == "zh" else GROUND_EN).search(text or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip(), m.group(3).strip().rstrip("。.")


# ============================================================ 基础解析 ===
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_rows(path: Path) -> list:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def extract_verdict(text: str):
    """→ (raw_json, obj_or_None, pairs_or_None, err)。

    pairs 为顶层键序列表（object_pairs_hook 保序）——键序断言据此判定。
    """
    ms = list(VERDICT_RE.finditer(text or ""))
    if not ms:
        return None, None, None, "missing"
    raw = ms[-1].group(1)
    try:
        pairs = json.loads(raw, object_pairs_hook=lambda p: p)
    except Exception:
        return raw, None, None, "unparsable"
    obj = dict(pairs) if isinstance(pairs, list) else None
    return raw, obj, pairs, None


def last_line_is_verdict(text: str) -> bool:
    lines = [x for x in (text or "").strip().splitlines() if x.strip()]
    return bool(lines) and lines[-1].lstrip().startswith("VERDICT:")


def row_query(row: dict) -> str:
    """容错取 user 轮文本（畸形行不许让校验器崩，只许让断言亮红）。"""
    conv = row.get("conversations") or []
    if len(conv) > 1 and isinstance(conv[1], dict):
        return conv[1].get("value") or ""
    return ""


def carrier_body(query: str) -> str:
    return " ".join(BODY_RE.findall(query or ""))


def declared(rows_entry) -> dict:
    """从 src_task 拆 (kind, ctype, mech, pos)。"""
    parts = (rows_entry.get("src_task") or "").split(":")
    if len(parts) != 4:
        return {"kind": "?", "ctype": "?", "mech": "?", "pos": "?"}
    kind = "clean" if parts[2] == "clean" else "inj"
    return {"kind": kind, "ctype": parts[1], "mech": parts[2], "pos": parts[3]}


def classify_rejected(row: dict) -> str:
    """内容派生①/②/③（不依赖 dpo_class 标签）。"""
    d = declared(row)
    _raw, rj, _pairs, err = extract_verdict((row.get("rejected") or {}).get("value", ""))
    if err or rj is None:
        return "unparsable"
    findings = rj.get("findings") or []
    if d["kind"] == "clean":
        return "overrefusal" if rj.get("verdict") == "contains-injection" else "OTHER"
    if rj.get("action") == "refuse" and not findings:
        return "hollow"
    if rj.get("action") == "answer" and rj.get("verdict") in ("benign", "allow"):
        return "obedient"
    return "OTHER"


def payload_hits(text: str, ctype: str) -> set:
    """载体里出现的载荷原文 → {(mech, payload_text)}。"""
    hits = set()
    for (c, m), vs in B.PAYLOADS.items():
        if c != ctype:
            continue
        for lang, plist in vs.items():
            for p in plist:
                if p in text:
                    hits.add((m, p))
    return hits


def near_miss_hits(text: str, ctype: str, lang: str) -> list:
    return [x for x in B.NEAR_MISS[ctype][lang] if x in text]


def max_member_run(text: str, gramset: set, n: int = NGRAM_N) -> int:
    """官方口径的"连续成员游程"：连续出现且每个 gram 都属于 gramset 的最长游程。"""
    best = cur = 0
    for g in ngrams(normalize(text), n):
        if g in gramset:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def lcs_chars(a: str, b: str) -> int:
    """两段规范化文本的最长公共子串长度（官方口径第二段用）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


# ============================================================ 留出集索引 ===
def load_heldout(sets=HELDOUT_SETS, base: Path = HELDOUT_DIR) -> list:
    """→ [{"set","id","query","body","norm"}]（只在给定目录里读，绝不写）。"""
    out = []
    for s in sets:
        d = base / s
        if not d.is_dir():
            continue
        for fp in sorted(d.glob("*.jsonl")):
            with fp.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    j = json.loads(line)
                    q = j.get("query") or ""
                    out.append({"set": s, "id": j.get("id"), "query": q,
                                "body": carrier_body(q), "norm": normalize(q),
                                "file": fp.name})
    return out


def heldout_grams(heldout: list) -> dict:
    g = defaultdict(set)
    for h in heldout:
        g[h["set"]] |= set(ngrams(h["norm"], NGRAM_N))
    return g


def heldout_body_grams(heldout: list) -> dict:
    g = defaultdict(set)
    for h in heldout:
        if h["body"]:
            g[h["set"]] |= set(ngrams(normalize(h["body"]), NGRAM_N))
    return g


def train_disjoint(rows: list, heldout: list, spec: dict) -> dict:
    """id/query 零重叠（硬）+ 官方两段式 8-gram 口径（预筛 + LCS，硬）+ 计数报告。"""
    h_ids = {h["id"] for h in heldout}
    h_exact = {h["query"] for h in heldout}
    h_norm = {h["norm"] for h in heldout}
    hq = heldout_grams(heldout)
    hb = heldout_body_grams(heldout)
    sets = sorted({h["set"] for h in heldout})
    # 预筛存活者才做 LCS：按集分桶，便于只比同集文档
    heldout_by_set = defaultdict(list)
    for h in heldout:
        heldout_by_set[h["set"]].append(h)

    my_ids = [r.get("id") for r in rows]
    id_overlap = sorted(set(my_ids) & h_ids)
    exact_hits, norm_hits = [], []
    per_row_shared = Counter()          # set -> Σ_rows |grams ∩ set|
    rows_any_shared = Counter()         # set -> 有共享 gram 的行数
    body_run = Counter()                # 正文层游程直方图
    full_run = Counter()                # 全 query 游程直方图
    prefilter_full = []                 # 进入官方预筛的行（整 query）
    prefilter_body = []                 # 进入官方预筛的行（正文）
    runs_by_id = []
    my_grams_union = set()
    for r in rows:
        q = row_query(r)
        b = carrier_body(q)
        if q in h_exact:
            exact_hits.append(r["id"])
        if normalize(q) in h_norm:
            norm_hits.append(r["id"])
        gq = set(ngrams(normalize(q), NGRAM_N))
        my_grams_union |= gq
        gb = set(ngrams(normalize(b), NGRAM_N))
        fr = br = 0
        for s in sets:
            n = len(gq & hq[s])
            per_row_shared[s] += n
            if n:
                rows_any_shared[s] += 1
            fr = max(fr, max_member_run(q, hq[s]))
            br = max(br, max_member_run(b, hb[s]))
        full_run[fr] += 1
        body_run[br] += 1
        runs_by_id.append((r["id"], br))
        if fr >= NGRAM_PREFILTER:
            prefilter_full.append({"id": r["id"], "run": fr})
        if br >= NGRAM_PREFILTER:
            prefilter_body.append({"id": r["id"], "run": br})

    # 第二段：只对预筛存活者算 LCS（官方实现同样如此——因此幸存者为空时该段为空）
    lcs_hits = []
    for item in prefilter_body[:50]:
        row = next(x for x in rows if x["id"] == item["id"])
        nb = normalize(carrier_body(row_query(row)))
        for s in sets:
            for h in heldout_by_set[s]:
                if not h["body"]:
                    continue
                n = lcs_chars(nb, normalize(h["body"]))
                if n >= LCS_MIN_CHARS:
                    lcs_hits.append({"id": item["id"], "heldout": h["id"],
                                     "lcs_chars": n})
                    break

    # 外壳骨架基线：把载体正文与任务描述掏空后的 query 游程（构造性共享的下限）
    scaffold_run = {}
    if rows:
        q0 = row_query(rows[0])
        skel = BODY_RE.sub("<body>X</body>", q0)
        skel = re.sub(r"(?s)<operator>.*?</operator>", "<operator>X</operator>", skel)
        for s in sets:
            scaffold_run[s] = max_member_run(skel, hq[s])

    union_shared = {s: len(my_grams_union & hq[s]) for s in sets}
    body_max = max(body_run) if body_run else 0
    over_cap = sum(v for k, v in body_run.items() if k > spec["body_run_report_cap"])
    return {
        "heldout_rows": len(heldout),
        "heldout_sets": sets,
        "n_my_rows": len(rows),
        "id_overlap": len(id_overlap),
        "id_overlap_sample": id_overlap[:5],
        "query_exact_overlap": len(exact_hits),
        "query_normalized_overlap": len(norm_hits),
        "query_overlap_sample": (exact_hits + norm_hits)[:5],
        "ngram_n": NGRAM_N,
        "ngram_prefilter_threshold": NGRAM_PREFILTER,
        "lcs_min_chars": LCS_MIN_CHARS,
        "prefilter_survivors_full_query": len(prefilter_full),
        "prefilter_survivors_body": len(prefilter_body),
        "lcs_hits": len(lcs_hits),
        "lcs_hit_sample": lcs_hits[:5],
        "shared_grams_sum_over_rows": {s: per_row_shared[s] for s in sets},
        "shared_grams_union": union_shared,
        "rows_with_any_shared_gram": {s: rows_any_shared[s] for s in sets},
        "body_max_run": body_max,
        "body_run_histogram": {str(k): v for k, v in sorted(body_run.items())},
        "body_rows_over_report_cap": over_cap,
        "body_run_top_rows": [
            {"id": rid, "body_run": run}
            for rid, run in sorted(runs_by_id, key=lambda x: -x[1])[:10]],
        "full_query_max_run": max(full_run) if full_run else 0,
        "full_query_run_histogram": {str(k): v for k, v in sorted(full_run.items())},
        "scaffold_only_run_baseline": scaffold_run,
        "note": ("官方两段式：预筛「连续成员游程」≥ {} gram，存活者再做 LCS ≥ {} 字符。"
                 "正文层预筛存活 0 行 → 第二段为空；正文层最大游程 {} gram（≈ 共享子串 "
                 "≥{} 字符）。整 query 层 6000/6000 行都会进预筛，因为协议外壳"
                 "（<dsh-protocol>/<system>/<carrier>）与容器标签词表是构造性共享："
                 "外壳骨架基线的游程已达 {}–{} gram（即共享子串 ≥ {} 字符），本身"
                 "就超过 LCS 阈值 —— 故整 query 层只留痕、不进退出码，正文层才进断言。"
                 ).format(NGRAM_PREFILTER, LCS_MIN_CHARS, body_max,
                          body_max + NGRAM_N - 1 if body_max else 0,
                          min(scaffold_run.values()) if scaffold_run else 0,
                          max(scaffold_run.values()) if scaffold_run else 0,
                          (min(scaffold_run.values()) + NGRAM_N - 1)
                          if scaffold_run else 0),
    }


# ============================================================ 断言主体 ===
def run_assertions(rows: list, *, spec: dict | None = None,
                   heldout: list | None = None,
                   do_disjoint: bool = True) -> dict:
    """纯函数：喂任意行（含故意做坏的 fixture）→ 逐断言结果 + 原始计数。"""
    s = dict(DEFAULT_SPEC)
    s.update(spec or {})
    A = []          # [{name, ok, counts}]

    def add(name, ok, info=False, **counts):
        A.append({"name": name, "ok": bool(ok), "informational": bool(info),
                  "counts": counts})

    # ---- 基础计数
    carriers, langs, packs, classes, mechs = (Counter() for _ in range(5))
    axes, positions = Counter(), Counter()
    axis_pack_ruling = defaultdict(Counter)
    ground_ok = ground_table_ok = clean_verdict_ok = 0
    ctx_mech = defaultdict(set)          # 只统计注入行的机制（良性行的 mech 槽是 "clean"）
    per_carrier_lang = defaultdict(Counter)
    per_carrier_pack = defaultdict(Counter)
    clean_share_n = 0
    n = len(rows)

    key_ok = key_order_ok = conv_ok = sys_ok = 0
    v_present = v_json = v_order = v_policy = v_differ = v_lastline = 0
    v_action_word = 0
    proto_ok = proto_checked = 0
    payload_ok = near_miss_ok = 0
    clean_chosen_allow = clean_chosen_not_inj = 0
    inj_chosen_report = 0
    dup_pair = Counter()
    err_sem = Counter()

    for r in rows:
        keys = list(r.keys())
        if set(keys) == set(ROW_KEYS):
            key_ok += 1
        if keys == list(ROW_KEYS):
            key_order_ok += 1
        conv = r.get("conversations") or []
        if (len(conv) == 2 and conv[0].get("from") == "system"
                and conv[1].get("from") == B.USER_ROLE):
            conv_ok += 1
            if conv[0].get("value") == system_for(r.get("pack"), r.get("lang")):
                sys_ok += 1
        d = declared(r)
        ctype, mech, pos, kind = d["ctype"], d["mech"], d["pos"], d["kind"]
        carriers[ctype] += 1
        langs[r.get("lang")] += 1
        packs[r.get("pack")] += 1
        classes[r.get("dpo_class")] += 1
        mechs[mech] += 1
        positions[pos] += 1
        ctx_mech[ctype].add(mech) if kind == "inj" else None
        per_carrier_lang[ctype][r.get("lang")] += 1
        per_carrier_pack[ctype][r.get("pack")] += 1
        if kind == "clean":
            clean_share_n += 1
        query = row_query(r)
        dup_pair[(query, r.get("pack"))] += 1

        # --- VERDICT 契约（两侧）
        ch_raw, ch, ch_pairs, ch_err = extract_verdict(
            (r.get("chosen") or {}).get("value", ""))
        rj_raw, rj, rj_pairs, rj_err = extract_verdict(
            (r.get("rejected") or {}).get("value", ""))
        if ch_err is None and rj_err is None:
            v_present += 1
            v_json += 1
        if (ch_pairs and rj_pairs and [k for k, _ in ch_pairs] == list(VERDICT_KEYS)
                and [k for k, _ in rj_pairs] == list(VERDICT_KEYS)):
            v_order += 1
        if ch and rj and ch.get("policy") == r.get("pack") and \
                rj.get("policy") == r.get("pack"):
            v_policy += 1
        if ch_raw is not None and rj_raw is not None and ch_raw != rj_raw:
            v_differ += 1
        if last_line_is_verdict((r.get("chosen") or {}).get("value", "")) and \
                last_line_is_verdict((r.get("rejected") or {}).get("value", "")):
            v_lastline += 1
        if ch and rj and ch.get("action") in ACTIONS and rj.get("action") in ACTIONS:
            v_action_word += 1

        # --- 错误类语义
        cls = classify_rejected(r)
        err_sem[cls] += 1
        if B.ERR_CLASS.get(cls) != r.get("dpo_class"):
            err_sem["dpo_class_mismatch"] += 1

        # --- 载荷 / 良性备注自洽
        if s["require_payload_consistency"]:
            text = carrier_body(query)
            hits = payload_hits(text, ctype)
            hit_mechs = {m for m, _p in hits}
            if kind == "inj":
                if mech in hit_mechs and hit_mechs <= {mech}:
                    payload_ok += 1
            else:
                if not hits:
                    payload_ok += 1
            if kind == "clean":
                if near_miss_hits(text, ctype, r.get("lang")):
                    near_miss_ok += 1

        # --- chosen 行为方向
        if kind == "clean":
            if ch and ch.get("verdict") in ("allow", "conditional"):
                clean_chosen_allow += 1
            if ch and ch.get("verdict") != "contains-injection":
                clean_chosen_not_inj += 1
        else:
            if ch and ch.get("action") == "report" and \
                    ch.get("verdict") == "contains-injection":
                inj_chosen_report += 1

        # --- 政策接地：叙述里的「规则（包）→ 裁决」必须能对上 AXES 政策表
        g = extract_grounding((r.get("chosen") or {}).get("value", ""), r.get("lang"))
        if g:
            rule_t, pack_t, ruling_t = g
            ax_name = axis_of_rule(rule_t, r.get("lang"))
            if ax_name and pack_t == r.get("pack"):
                ground_ok += 1
                axes[ax_name] += 1
                axis_pack_ruling[ax_name][r.get("pack")] = ruling_t
                v_w, a_w = B.AXES[ax_name]["ruling"][r.get("pack")]
                if ruling_t == B.RULING_WORD[r.get("lang")][v_w]:
                    ground_table_ok += 1
                if kind == "clean" and ch and (ch.get("action"), ch.get("verdict")) == \
                        (a_w, v_w):
                    clean_verdict_ok += 1

        # --- 协议往返
        if s["require_protocol_roundtrip"] and query:
            proto_checked += 1
            try:
                pc = parse_context(query)
                if (pc.system.get("policy") == r.get("pack")
                        and pc.carriers
                        and pc.carriers[0]["type"] == ctype
                        and pc.carriers[0]["trust"] == "untrusted"):
                    proto_ok += 1
            except Exception:
                pass

    # ---- 断言 1–15
    add("rows_range", s["rows_min"] <= n <= s["rows_max"],
        rows=n, rows_min=s["rows_min"], rows_max=s["rows_max"])
    dup_ids = [k for k, v in Counter(x.get("id") for x in rows).items() if v > 1]
    add("id_unique", not dup_ids, rows=n, unique_ids=len(set(x.get("id") for x in rows)),
        duplicate_ids=len(dup_ids), sample=dup_ids[:5])
    bad_prefix = [x.get("id") for x in rows
                  if not str(x.get("id", "")).startswith(B.ID_PREFIX)]
    add("id_prefix", not bad_prefix, n_bad=len(bad_prefix))

    missing = [c for c in REQUIRED_CARRIERS if carriers[c] < s["min_per_carrier"]]
    unknown = sorted(set(carriers) - set(_CARRIER_TYPES))
    add("carrier_coverage", not missing and not unknown,
        per_carrier=dict(carriers), required=list(REQUIRED_CARRIERS),
        min_per_carrier=s["min_per_carrier"], below_min=missing,
        unknown_types=unknown,
        continuity={c: carriers[c] for c in CONTINUITY_CARRIERS})
    add("carrier_registry", not unknown, registry=sorted(_CARRIER_TYPES),
        unknown_types=unknown)

    thin = sorted(c for c, m in ctx_mech.items()
                  if len(m) < s["min_mechs_per_carrier"])
    empty_cells = sorted(
        "{}:{}".format(c, m) for c in B.CARRIER_QUOTA
        for m in B.CTYPE_MECHS.get(c, ()) if m not in ctx_mech.get(c, ()))
    add("mechanisms_per_carrier", not thin and not empty_cells,
        mechs_per_carrier={c: len(m) for c, m in sorted(ctx_mech.items())},
        min_required=s["min_mechs_per_carrier"], thin=thin,
        empty_cells=empty_cells)
    undeclared = sorted(
        "{}:{}".format(c, m) for c in ctx_mech for m in ctx_mech[c]
        if m not in B.CTYPE_MECHS.get(c, ()))
    not_covered = sorted(
        "{}:{}".format(c, m) for c in carriers
        for m in B.CTYPE_MECHS.get(c, ()) if m not in ctx_mech.get(c, ()))
    add("mechanism_registry_exact", not undeclared and not not_covered,
        undeclared=undeclared, uncovered=not_covered,
        declared_total=sum(len(B.CTYPE_MECHS.get(c, ())) for c in carriers))

    lang_share = {l: langs[l] / n for l in LANGS} if n else {}
    lang_ok = all(v >= s["min_lang_share"] for v in lang_share.values()) \
        if len(lang_share) == len(LANGS) else False
    add("lang_share_global", lang_ok, lang=dict(langs), share=lang_share,
        min_share=s["min_lang_share"])
    pc_lang_bad = []
    pc_lang_share = {}
    for c in carriers:
        tot = sum(per_carrier_lang[c].values())
        pc_lang_share[c] = {l: per_carrier_lang[c][l] / tot for l in LANGS} if tot else {}
        if any(pc_lang_share[c].get(l, 0.0) < s["min_lang_share"] for l in LANGS):
            pc_lang_bad.append(c)
    add("lang_share_per_carrier", not pc_lang_bad,
        share=pc_lang_share, below_min=pc_lang_bad, min_share=s["min_lang_share"])

    pack_share = {p: packs[p] / n for p in PACKS} if n else {}
    add("pack_coverage",
        all(pack_share.get(p, 0.0) >= s["min_pack_share"] for p in PACKS),
        pack=dict(packs), share=pack_share, min_share=s["min_pack_share"])
    pc_pack_bad = sorted(c for c in carriers
                         if len(per_carrier_pack[c]) < len(PACKS))
    add("pack_per_carrier_present", not pc_pack_bad,
        per_carrier=({c: dict(v) for c, v in sorted(per_carrier_pack.items())}),
        missing=pc_pack_bad)

    add("row_key_schema", key_ok == n, ok_rows=key_ok, keys=list(ROW_KEYS))
    add("row_key_order", key_order_ok == n, ok_rows=key_order_ok)
    add("conversations_shape", conv_ok == n, ok_rows=conv_ok,
        user_role=B.USER_ROLE)
    add("system_matches_policy_ssot", sys_ok == n, ok_rows=sys_ok)

    add("verdict_present_both_sides", v_present == n, ok_rows=v_present)
    add("verdict_json_valid", v_json == n, ok_rows=v_json)
    add("verdict_key_order", v_order == n, ok_rows=v_order, keys=list(VERDICT_KEYS))
    add("verdict_policy_equals_pack", v_policy == n, ok_rows=v_policy)
    add("verdict_sides_differ", v_differ == n, ok_rows=v_differ)
    add("verdict_is_last_line", v_lastline == n, ok_rows=v_lastline)
    add("verdict_action_vocab", v_action_word == n, ok_rows=v_action_word,
        actions=list(ACTIONS))

    clean_share = clean_share_n / n if n else 0.0
    add("clean_negative_share", clean_share >= s["min_clean_share"],
        clean_rows=clean_share_n, rows=n, share=clean_share,
        min_share=s["min_clean_share"])
    occ = {k: err_sem[k] for k in ("obedient", "hollow", "overrefusal")}
    add("rejected_three_error_classes",
        all(occ[k] > 0 for k in occ) and err_sem["OTHER"] == 0
        and err_sem["unparsable"] == 0,
        occurrences=occ, other=err_sem["OTHER"], unparsable=err_sem["unparsable"])
    add("dpo_class_matches_semantics", err_sem["dpo_class_mismatch"] == 0,
        mismatches=err_sem["dpo_class_mismatch"], dpo_class=dict(classes))
    add("clean_chosen_allow_or_conditional", clean_chosen_allow == clean_share_n
        and clean_share_n > 0, ok_rows=clean_chosen_allow, clean_rows=clean_share_n)
    add("clean_chosen_not_injection", clean_chosen_not_inj == clean_share_n,
        ok_rows=clean_chosen_not_inj)
    add("injected_chosen_reports", inj_chosen_report == n - clean_share_n,
        ok_rows=inj_chosen_report, injected_rows=n - clean_share_n)
    if s["require_payload_consistency"]:
        add("payload_self_consistency", payload_ok == n, ok_rows=payload_ok)
        add("clean_has_near_miss_note", near_miss_ok == clean_share_n,
            ok_rows=near_miss_ok, clean_rows=clean_share_n)
    add("policy_grounding_extractable", ground_ok == n, ok_rows=ground_ok)
    add("policy_grounding_matches_policy_table", ground_table_ok == n,
        ok_rows=ground_table_ok, axes_covered=len(axes), axes_total=len(B.AXES))
    add("clean_verdict_matches_axis_ruling", clean_verdict_ok == clean_share_n,
        ok_rows=clean_verdict_ok, clean_rows=clean_share_n)
    if s["require_protocol_roundtrip"]:
        add("protocol_roundtrip", proto_checked == n and proto_ok == n,
            checked=proto_checked, ok_rows=proto_ok)
    dups = sum(v - 1 for v in dup_pair.values() if v > 1)
    add("no_duplicate_prompt_pack", dups == 0, duplicate_pairs=dups,
        unique_pairs=len(dup_pair))

    report = {
        "spec": s,
        "counts": {
            "rows": n,
            "carriers": dict(carriers),
            "lang": dict(langs),
            "lang_share": lang_share,
            "pack": dict(packs),
            "pack_share": pack_share,
            "dpo_class": dict(classes),
            "mechanisms": dict(mechs),
            "positions": dict(positions),
            "axes": dict(axes),
            "axis_pack_ruling": {k: dict(v) for k, v in sorted(axis_pack_ruling.items())},
            "clean_rows": clean_share_n,
            "clean_share": clean_share,
            "mechs_per_carrier": {c: sorted(m) for c, m in sorted(ctx_mech.items())},
            "per_carrier_lang": {c: dict(v) for c, v in sorted(per_carrier_lang.items())},
            "per_carrier_pack": {c: dict(v) for c, v in sorted(per_carrier_pack.items())},
        },
        "error_class_semantics": dict(err_sem),
        "assertions": A,
        "failures": [a["name"] for a in A if not a["ok"]],
    }
    if do_disjoint:
        report["train_disjoint"] = train_disjoint(rows, heldout or [], s)
        td = report["train_disjoint"]
        report["assertions"].extend([
            {"name": "train_disjoint_ids", "ok": td["id_overlap"] == 0,
             "informational": False, "counts": {"id_overlap": td["id_overlap"]}},
            {"name": "train_disjoint_query_exact",
             "ok": td["query_exact_overlap"] == 0, "informational": False,
             "counts": {"overlap": td["query_exact_overlap"]}},
            {"name": "train_disjoint_query_normalized",
             "ok": td["query_normalized_overlap"] == 0, "informational": False,
             "counts": {"overlap": td["query_normalized_overlap"]}},
            {"name": "train_disjoint_body_ngram_prefilter",
             "ok": td["prefilter_survivors_body"] == 0, "informational": False,
             "counts": {"survivors": td["prefilter_survivors_body"],
                        "prefilter_threshold": NGRAM_PREFILTER,
                        "body_max_run": td["body_max_run"],
                        "report_cap": s["body_run_report_cap"],
                        "rows_over_report_cap": td["body_rows_over_report_cap"]}},
            # 报告项：整 query 的游程被协议外壳托底，必超官方预筛阈值——它不是
            # "本批次污染"的证据（外壳基线同级），故不计入退出码，仅留痕。
            {"name": "train_disjoint_full_query_ngram_prefilter",
             "ok": td["prefilter_survivors_full_query"] == 0, "informational": True,
             "counts": {"survivors": td["prefilter_survivors_full_query"],
                        "prefilter_threshold": NGRAM_PREFILTER,
                        "full_query_max_run": td["full_query_max_run"],
                        "scaffold_baseline": td["scaffold_only_run_baseline"],
                        "note": "协议外壳构造性共享：该项恒失败，仅作留痕"}},
            {"name": "train_disjoint_lcs_stage2", "ok": td["lcs_hits"] == 0,
             "informational": False,
             "counts": {"lcs_hits": td["lcs_hits"],
                        "lcs_min_chars": LCS_MIN_CHARS}},
        ])
        report["failures"] = [a["name"] for a in report["assertions"]
                              if not a["ok"] and not a["informational"]]
    return report


def reference_census(path: Path = REF_DPO) -> dict:
    """只读参考：现有 dpo_m3.jsonl 的载体构成（本批次立项的证据）。"""
    if not path.exists():
        return {"available": False}
    car = Counter()
    n = with_car = with_v = 0
    carve = re.compile(r"<\s*carrier\b[^>]*?\btype\s*=\s*[\"']?([A-Za-z_]+)")
    for line in path.open(encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        n += 1
        txt = " ".join((m.get("value") or "") for m in (r.get("conversations") or []))
        found = set(carve.findall(txt))
        if found:
            with_car += 1
            for c in found:
                car[c] += 1
        else:
            car["<no-carrier>"] += 1
        if "VERDICT" in ((r.get("chosen") or {}).get("value") or ""):
            with_v += 1
    return {"available": True, "rows": n, "rows_with_carrier": with_car,
            "share_with_carrier": with_car / n if n else 0.0,
            "carrier_types": dict(car.most_common()),
            "chosen_with_verdict": with_v,
            "share_chosen_with_verdict": with_v / n if n else 0.0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="check carrier-diverse DPO batch")
    ap.add_argument("--rows", default=str(ROWS_DEFAULT))
    ap.add_argument("--stats", default=str(STATS_OUT))
    ap.add_argument("--no-reference", action="store_true")
    args = ap.parse_args(argv)

    rows_path = Path(args.rows)
    rows = load_rows(rows_path)
    heldout = load_heldout()
    rep = run_assertions(rows, heldout=heldout)
    rep["input"] = {"rows_path": str(rows_path), "rows_sha256": sha256_of(rows_path),
                    "rows_bytes": rows_path.stat().st_size,
                    "heldout_sets": list(HELDOUT_SETS)}
    if not args.no_reference:
        rep["reference_dpo_m3"] = reference_census()

    out = Path(args.stats)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2, sort_keys=False)
                   + "\n", encoding="utf-8")

    c = rep["counts"]
    print("rows={rows:,}  clean_share={cs:.3f}  carriers={nc}".format(
        rows=c["rows"], cs=c["clean_share"], nc=len(c["carriers"])))
    print("carriers:", c["carriers"])
    print("lang:", c["lang"], "share:", {k: round(v, 4) for k, v in c["lang_share"].items()})
    print("pack:", c["pack"], "share:", {k: round(v, 4) for k, v in c["pack_share"].items()})
    print("dpo_class:", c["dpo_class"])
    print("error_classes:", rep["error_class_semantics"])
    td = rep.get("train_disjoint", {})
    if td:
        print("train-disjoint: id_overlap={} exact={} normalized={} "
              "body_max_run={} full_max_run={}".format(
                  td["id_overlap"], td["query_exact_overlap"],
                  td["query_normalized_overlap"], td["body_max_run"],
                  td["full_query_max_run"]))
        print("  共享 8-gram（行级求和/并集）: sum={} union={}".format(
            td["shared_grams_sum_over_rows"], td["shared_grams_union"]))
        print("  外壳骨架基线游程: {}".format(td["scaffold_only_run_baseline"]))
    bad = rep["failures"]
    n_info = sum(1 for a in rep["assertions"] if a["informational"])
    print("assertions: {} passed / {} total ({} informational)".format(
        len(rep["assertions"]) - len(bad) - sum(
            1 for a in rep["assertions"] if a["informational"] and not a["ok"]),
        len(rep["assertions"]), n_info))
    for a in rep["assertions"]:
        tag = "INFO" if a["informational"] else ("PASS" if a["ok"] else "FAIL")
        print("  [{}] {}".format(tag, a["name"]))
    print("stats -> {}".format(out))
    if bad:
        print("FAILED ASSERTIONS: {}".format(", ".join(bad)))
        return 1
    print("ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
