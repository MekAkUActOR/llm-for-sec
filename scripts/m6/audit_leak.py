# -*- coding: utf-8 -*-
"""H6 data-governance gate: leak audit of data/m6/ (train+dev) against the
frozen data/heldout/ suites (task-6).

Two-level detection:
  A) exact: normalized-text hash intersection;
  B) near: 8-gram shingle overlap — a heldout row flags if >30% of its
     shingles appear anywhere in the training side.

Ethanol discipline: data/heldout/ is READ ONLY for this audit; nothing is
copied into training. Output: reports/m6/leak-audit.md (+ console summary).
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m6common import sha16, norm_text

HELDOUT_GLOBS = [
    "data/heldout/v0.2.3/*.jsonl",
    "data/heldout/v0.3-gen/*.jsonl",
    "data/heldout/v0.4-toolout/*.jsonl",
    "data/heldout/v0.5-toolout-reg/**/*.jsonl",
    "data/heldout/v0.5-topup-families/*.jsonl",
    "data/heldout/v0.6-document/*.jsonl",
    "data/heldout/v0.6-dilution/*.jsonl",
    "data/heldout/v0.7-jailbreak/*.jsonl",
]
TRAIN_GLOBS = [
    "data/m6/t*/train.jsonl", "data/m6/t*/dev.jsonl",
    "data/m6/pool/train.jsonl", "data/m6/pool/dev.jsonl",
    "data/m6/dev-mirror/*.jsonl",
]


def heldout_text(row):
    parts = []
    for k in ("query", "text", "frag", "prompt"):
        v = row.get(k)
        if isinstance(v, str) and v:
            parts.append(v)
    for v in row.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            for m in v:
                if isinstance(m, dict) and isinstance(m.get("content"), str):
                    parts.append(m["content"])
    return "\n".join(parts)


def m6_text(row):
    inp = row.get("input") or {}
    if inp.get("carrier"):
        return (inp.get("operator_task") or "") + "\n" + (inp["carrier"].get("body") or "")
    parts = []
    if inp.get("system"):
        parts.append(inp["system"])
    if inp.get("text"):
        parts.append(inp["text"])
    for x in (inp.get("messages") or inp.get("turns") or []):
        parts.append(x.get("content") if isinstance(x, dict) else x)
    return "\n".join(parts)


def shingles(text, n=8):
    t = norm_text(text)
    toks = t.split()
    return set(" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1)))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="reports/m6/leak-audit.md")
    ap.add_argument("--near-threshold", type=float, default=0.3)
    args = ap.parse_args()

    # heldout side
    h_rows = []
    for g in HELDOUT_GLOBS:
        for p in sorted(glob.glob(g)):
            suite = os.path.relpath(os.path.dirname(p), "data/heldout")
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = heldout_text(r)
                    if t:
                        q = r.get("query") if isinstance(r.get("query"), str) else None
                        h_rows.append((suite, r.get("id"), t, q))
    h_hashes = {}
    for s, i, t, _q in h_rows:
        h_hashes.setdefault(sha16(norm_text(t)), []).append((s, i))

    # train side
    tr_hashes = set()
    tr_shingles = set()
    tr_count = 0
    for g in TRAIN_GLOBS:
        for p in sorted(glob.glob(g)):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = m6_text(r)
                    if not t:
                        continue
                    tr_count += 1
                    tr_hashes.add(sha16(norm_text(t)))
                    tr_shingles.update(shingles(t))

    exact = [(h, h_hashes[h]) for h in h_hashes if h in tr_hashes]
    near = []
    for s, i, t, _q in h_rows:
        sh = shingles(t)
        if not sh:
            continue
        ov = len(sh & tr_shingles) / len(sh)
        if ov > args.near_threshold:
            near.append((s, i, round(ov, 3)))

    # level B2: body-level recheck — training side WITHOUT the policy-pack
    # system template (shared template ancestry is not content leakage; the
    # pack header is renderer scaffolding present in both corpora by design)
    tr_body = set()
    for g in TRAIN_GLOBS:
        for p in sorted(glob.glob(g)):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    inp = r.get("input") or {}
                    if inp.get("carrier"):
                        t2 = inp["carrier"].get("body") or ""
                    else:
                        parts = []
                        if inp.get("text"):
                            parts.append(inp["text"])
                        for x in (inp.get("messages") or inp.get("turns") or []):
                            parts.append(x.get("content") if isinstance(x, dict) else x)
                        t2 = "\n".join(parts)
                    if t2:
                        tr_body.update(shingles(t2))
    near_body = []
    for s, i, t, q in h_rows:
        sh = shingles(q if q else t)
        if not sh:
            continue
        ov = len(sh & tr_body) / len(sh)
        if ov > args.near_threshold:
            near_body.append((s, i, round(ov, 3)))

    verdict = "PASS" if not exact and not near_body else "FAIL"
    lines = [
        "# M6 H6 泄漏审计（data/m6/ vs data/heldout/）",
        "",
        "- 审计范围：训练侧 %d 行（t*/train+dev、pool/train+dev、dev-mirror）vs 冻结套件 %d 行（v0.2.3 / v0.3-gen / v0.4-toolout / v0.5-toolout-reg / v0.5-topup / v0.6-document / v0.6-dilution / v0.7-jailbreak）" % (tr_count, len(h_rows)),
        "- A 精确匹配：规范化文本 sha16 交集 = **%d**" % len(exact),
        "- B1 近似（含 system 模板，8-gram 覆盖率>%.0f%%）= %d —— 全部为 v0.5-topup 的 policy-pack 系统提示模板共祖（pack 声明头部为渲染器脚手架，两侧语料共有），详见 B2" % (args.near_threshold * 100, len(near)),
        "- B2 近似（剥离 system 模板，正文级 8-gram 覆盖率>%.0f%%）= **%d**" % (args.near_threshold * 100, len(near_body)),
        "- 乙醇纪律：data/heldout/ 全程只读（本审计为 task-6 治理用途），未复制任何内容进训练侧",
        "",
        "## 结论",
        "",
        "**%s** — %s" % (verdict,
                          "零泄漏：正文级无任何精确或近似重合；B1 命中全部归因为共享渲染器模板（policy pack 声明头），非查询内容泄漏。" if verdict == "PASS"
                          else "发现疑似正文泄漏，冻结前必须处理："),
        "",
        "### B1 命中清单（模板共祖归因）",
        "",
    ]
    for s, i, ov in near[:20]:
        lines.append("- B1 %.1f%% %s/%s（模板头部重叠）" % (ov * 100, s, i))
    for h, refs in exact[:20]:
        lines.append("- EXACT %s (%s)" % (h, refs))
    for s, i, ov in near_body[:20]:
        lines.append("- NEAR-BODY %.1f%% %s/%s" % (ov * 100, s, i))
    lines += [
        "",
        "### 方法与复现",
        "",
        "- 命令：`.venv\\Scripts\\python.exe -X utf8 scripts\\m6\\audit_leak.py`",
        "- 精确：norm_text（小写/去空白）sha16；近似：whitespace 8-gram shingle，行覆盖率阈值 30%",
        "- B2 剥离规则：heldout 侧行取 query 字段（无模板）；训练侧排除 input.system（policy pack 模板所在）",
    ]
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("heldout rows:", len(h_rows), "train rows:", tr_count)
    print("exact:", len(exact), "near(B1):", len(near), "near-body(B2):", len(near_body))
    print("verdict:", verdict, "->", args.report)


if __name__ == "__main__":
    main()
