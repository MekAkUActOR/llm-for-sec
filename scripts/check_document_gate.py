# -*- coding: utf-8 -*-
r"""v0.6-document 门禁集检查器（fail-closed；末行 PASS/FAIL 机器可读）。

**输出纪律**：控制台只打**聚合**（每类错误 ≤3 条样例 + 计数 + 末尾错误种类表），
逐条明细写进 `--stats-out` 的 JSON。一个几万行的校验器不是仪器。

检查项（逐条对应交付要求）：

* (a) **schema / id / kind / 条数**：直接读盘上的 `data/heldout/v0.6-document/`
  （不信任构建器内存），逐行校验 9 键**顺序**与 v0.4-toolout 一致；再走
  `secfm.eval.heldout.load_dir + validate`（真实消费路径）；条数下限
  鲁棒性 ≥ 40、对齐 ≥ 20、未见机理分母 ≥ 34。
* (b) **未见机理（未见结构位点）机器可判**：训练侧结构位点清单（普查产物，
  按**全量**与**活谱系**双口径）vs 门禁侧位点清单，逐项对照打印；
  断言门禁位点集 ∩ 训练位点集 = ∅；并把每条对抗条的 `载荷片段` 与门禁机理的
  `value_res` 正则对上——证明载荷**真的**落在声明的位点上。
* (c) **与训练语料/既有留出集零重叠**（四路互相独立）：
  1. 与 `data/heldout/*/` 其余全部版本做 **id / query 全文 / 载体正文前 60 字**
     三重比对；
  2. 整语料**逐行 sha256** + 每个载体渲染文本 sha256；
  3. document 载体训练子集（6,400 行）的 **60 字节窗口**原始比对，
     逐条归因：schema 区 / 行首行尾短 token 共享 / 内容重叠 / 未归因；
  4. 短载荷片段（≥8 字节）在 document 子集里的**整串包含**测试；
  另校验 `_work/overlap-*.json` 的时效性（语料指纹 + 口径版本 + 非受限扫描）。
* (d) **可判性冒烟**：每条对抗条造两条假回复——`正确行为` 文本（必须判为
  防御：report_finding/refuse）与 `注入要求` 文本（必须判为 comply）；
  干净负例的 `正确行为` 文本必须**不**判为 refuse（不误拒）。
  `action_rule` 的 **selfreport 与 strict 两种口径都跑**。
* (e) **机器可读声明**：`manifest.claims` 逐项复算——特别是**按被评模型**的
  `unseen_carrier` 许可（M3 训了 1,000 条 document ⇒ 必须 false）。
* (f) **仪器卫生**：schema 行白名单**不得**匹配任何载荷位点行（行为断言，不是
  子串匹配）；位点键必须在训练位点清单里登记；两类 sha256 断言**分开**说明
  各自哈希的对象；构建器逐字节可复现。

用法：
    python scripts/check_document_gate.py                 # 全套
    python scripts/check_document_gate.py --rescan         # 现场重跑全量重叠扫描
    python scripts/check_document_gate.py --fast           # 跳过整语料逐行哈希
    python scripts/check_document_gate.py --require-unseen-carrier soup-a050
    python scripts/check_document_gate.py --stats-out reports/x.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import traceback
from collections import Counter, OrderedDict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_document_gate as B  # noqa: E402
from secfm.eval.heldout import load_dir as hv_load_dir  # noqa: E402
from secfm.eval.heldout import validate as hv_validate  # noqa: E402

GATE_DIR = ROOT / "data" / "heldout" / "v0.6-document"
GATE_FILE = GATE_DIR / B.FAMILY
MANIFEST = GATE_DIR / B.MANIFEST
PASS = "DOCUMENT-GATE-CHECK=PASS errors=0"
FAIL = "DOCUMENT-GATE-CHECK=FAIL"

#: 错误种类登记表：{类别: [计数, [样例…]]}（控制台只打前 EXAMPLE_MAX 条）
ERRORS: "OrderedDict[str, list]" = OrderedDict()
WARNS: "OrderedDict[str, list]" = OrderedDict()
NOTES: list = []
EXAMPLE_MAX = 3


def err(cat, msg):
    e = ERRORS.setdefault(cat, [0, []])
    e[0] += 1
    if len(e[1]) < EXAMPLE_MAX:
        e[1].append(str(msg))


def warn(cat, msg):
    e = WARNS.setdefault(cat, [0, []])
    e[0] += 1
    if len(e[1]) < EXAMPLE_MAX:
        e[1].append(str(msg))


def note(msg):
    NOTES.append(str(msg))
    print("       %s" % msg)


def head(msg):
    print("\n== %s" % msg)


def n_err():
    return sum(v[0] for v in ERRORS.values())


def sha256_bytes(b):
    if isinstance(b, str):
        b = b.encode("utf-8")
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------
def load_gate_rows(path=GATE_FILE):
    rows, raws = [], []
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
        raws.append(line)
    return rows, raws, text


def check_a_schema(items, manifest):
    head("(a) schema / id / kind / 条数")
    rows = items["rows"]
    bad = [i for i, r in enumerate(rows) if tuple(r.keys()) != B.KEY_ORDER]
    if bad:
        err("a.key_order", "键顺序/键集与 KEY_ORDER 不一致：%d 条，样例 %s"
            % (len(bad), list(rows[bad[0]].keys())))
    else:
        note("9 键顺序与 v0.4 参考一致：%s" % "|".join(B.KEY_ORDER))
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        err("a.dup_id", "重复 id：%s" % sorted(
            {x for x in ids if ids.count(x) > 1})[:5])
    pat = re.compile(r"^doc-(a|b|c)-\d{2}$")
    for r in rows:
        rid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(r, dict):
            err("a.row_type", "行不是对象：%r" % (r,))
            continue
        if not isinstance(rid, str) or not pat.match(rid):
            err("a.id_shape", "id 形态非法：%r" % (rid,))
            continue
        if not isinstance(r.get("query"), str) or not r["query"]:
            err("a.query", "%s: query 缺失/非字符串" % rid)
        exp = r.get("expected")
        if not isinstance(exp, dict):
            err("a.expected", "%s: expected 必须是对象（实际 %s）"
                % (rid, type(exp).__name__))
            exp = {}
        if r["kind"] not in ("robustness", "alignment"):
            err("a.kind", "%s: kind 非法 %r" % (rid, r["kind"]))
        if r["language"] not in ("zh", "en"):
            err("a.language", "%s: language 非法 %r" % (rid, r["language"]))
        if not r["policy_pack"]:
            err("a.pack", "%s: policy_pack 为空" % rid)
        if r["kind"] == "robustness" and exp.get("must_refuse") is not True:
            err("a.expected", "%s: robustness 必须 must_refuse=true" % rid)
        if r["kind"] == "alignment" and exp.get("must_refuse") is not False:
            err("a.expected", "%s: alignment 必须 must_refuse=false" % rid)
        if tuple(exp.keys()) != ("must_refuse",):
            err("a.expected", "%s: 只应有 expected.must_refuse" % rid)
    suite, problems = hv_load_dir(GATE_DIR)
    if problems:
        for p in problems[:EXAMPLE_MAX]:
            err("a.heldout_load", "heldout 加载问题：%s" % p)
    else:
        note("secfm.eval.heldout.load_dir：%d 条，0 问题" % len(suite.items))
    vp = hv_validate(suite.items)
    if vp:
        for p in vp[:EXAMPLE_MAX]:
            err("a.heldout_validate", "heldout.validate：%s" % p)
    else:
        note("secfm.eval.heldout.validate：0 问题（真实消费路径通过）")
    if len(suite.items) != len(rows):
        err("a.heldout_load", "load_dir 条数 %d != 文件行数 %d"
            % (len(suite.items), len(rows)))

    n_unseen = len(items["unseen"])
    n_cln = len(items["cln"])
    if n_unseen < B.MIN_ROBUSTNESS:
        err("a.count", "未见机理鲁棒性 %d < %d" % (n_unseen, B.MIN_ROBUSTNESS))
    if n_cln < B.MIN_ALIGNMENT:
        err("a.count", "对齐（误拒）%d < %d" % (n_cln, B.MIN_ALIGNMENT))
    if n_unseen < B.MIN_DENOMINATOR:
        err("a.count", "分母 %d < 本体下限 %d" % (n_unseen, B.MIN_DENOMINATOR))
    zh = sum(1 for r in items["unseen"] if r["language"] == "zh")
    if zh / max(1, n_unseen) < B.MIN_LANG_SHARE:
        err("a.balance", "未见机理 zh 占比 %d/%d < %.2f"
            % (zh, n_unseen, B.MIN_LANG_SHARE))
    czh = sum(1 for r in items["cln"] if r["language"] == "zh")
    if czh / max(1, n_cln) < B.MIN_LANG_SHARE:
        err("a.balance", "对齐 zh 占比 %d/%d < %.2f"
            % (czh, n_cln, B.MIN_LANG_SHARE))
    # manifest 计数：用**manifest 实际键名**对齐（曾因键名不一致误报）
    for key, val in (("n_items", len(rows)),
                     ("n_robustness", len(items["adv"])),
                     ("n_robustness_unseen_mechanism", n_unseen),
                     ("n_control_trained_site", len(items["ctl"])),
                     ("n_alignment", n_cln),
                     ("robustness_n", n_unseen),
                     ("control_n", len(items["ctl"]))):
        if manifest.get(key) != val:
            err("a.manifest_count", "manifest.%s=%r 与读盘复算 %r 不一致"
                % (key, manifest.get(key), val))
    if not ERRORS:
        note("条数：总 %d = 未见机理鲁棒 %d + 在训位点正对照 %d + 干净负例 %d"
             % (len(rows), n_unseen, len(items["ctl"]), n_cln))


# --------------------------------------------------------------------------
MECH_RE = re.compile(r"\[mech=([^;]+);\s*axis=([^;]+);\s*family=([^\];]+)")


def intent_of(row):
    m = MECH_RE.search(row["intent"])
    if not m:
        err("b.intent_head", "%s: intent 头缺失/格式非法" % row["id"])
        return (None, None, None)
    return (m.group(1), m.group(2), m.group(3))


def check_b_mechanism(items, census, manifest):
    head("(b) 未见机理（未见结构位点）：训练侧 vs 门禁侧 逐项对照")
    sites_all = census["train_structure_sites"]
    sites_live = census["train_structure_sites_live"]
    train_mechs = census["live_mechanisms"]
    print("  训练侧 document 载荷机理（活谱系 src_task，共 %d 类）：%s"
          % (len(train_mechs), "、".join(
              "%s×%d" % (k, v) for k, v in list(train_mechs.items())[:10])))
    print("  训练侧 document 载体结构位点行数（全量 %d 行 / 活谱系 %d 行）："
          % (census["document_rows"], census["live_document_rows"]))
    for k in B.TRAIN_SITES:
        a, l = sites_all.get(k, 0), sites_live.get(k, 0)
        tag = ""
        if any(k in m["site_keys"] for m in B.GATE_MECHS.values()):
            tag = "  ← 门禁留出（%s）" % ("✓0" if (a == 0 and l == 0) else "✗非0")
        print("    %-28s 全量=%-6d 活谱系=%-6d%s" % (k, a, l, tag))
    gate_keys = set()
    print("  门禁侧机理清单（%d 类未见机理 + 1 类在训位点对照）："
          % len(B.GATE_MECHS))
    mech_items = Counter(intent_of(r)[0] for r in items["unseen"])
    for m, cfg in B.GATE_MECHS.items():
        n = mech_items.get(m, 0)
        if n == 0:
            err("b.mech_empty", "门禁机理 %s 没有任何条目" % m)
        for k in cfg["site_keys"]:
            if k not in B.TRAIN_SITES:
                err("b.site_unregistered",
                    "门禁位点键 %s 未在训练位点清单登记" % k)
            if sites_all.get(k, 0) or sites_live.get(k, 0):
                err("b.site_in_train",
                    "门禁位点键 %s 在训练侧出现过（全量=%d 活谱系=%d）"
                    % (k, sites_all.get(k, 0), sites_live.get(k, 0)))
            gate_keys.add(k)
        print("    %-34s n=%-3d site_keys=%-38s 训练侧命中=%d"
              % (m, n, "+".join(cfg["site_keys"]),
                 sum(sites_all.get(k, 0) for k in cfg["site_keys"])))
    if len(B.GATE_MECHS) < B.MIN_MECHANISMS:
        err("b.mech_count", "门禁机理类数 %d < %d"
            % (len(B.GATE_MECHS), B.MIN_MECHANISMS))
    present = {k for k, v in sites_all.items() if v}
    if gate_keys & present:
        err("b.site_overlap", "门禁位点集 ∩ 训练位点集 非空：%s"
            % sorted(gate_keys & present))
    elif gate_keys <= present:
        err("b.site_overlap", "门禁位点集 ⊆ 训练位点集 ⇒ 不是未见机理")
    else:
        note("门禁位点集（%d 个）∩ 训练位点集（%d 个）= ∅，且 ⊄ ⇒ "
             "「未见机理（未见结构位点）」机器可判成立"
             % (len(gate_keys), len(present)))
    # 载荷真的落在声明位点上
    for r in items["unseen"]:
        m = intent_of(r)[0]
        if m not in B.GATE_MECHS:
            err("b.mech_unknown", "%s: 未知机理 %r" % (r["id"], m))
            continue
        frags = B.parse_frags(r["intent"])
        if not frags:
            err("b.frag_missing", "%s: intent 缺 载荷片段" % r["id"])
            continue
        captured = []
        for rx in B.GATE_MECHS[m]["value_res"]:
            captured += [g for g in re.findall(rx, r["query"])
                         if isinstance(g, str)]
        if not captured:
            err("b.site_not_rendered",
                "%s: 声明位点 %s 的 value_res 在 query 里没匹配上" % (r["id"], m))
            continue
        for f in frags:
            if f not in r["query"]:
                err("b.frag_truncated", "%s: 载荷片段未逐字出现在 query 里 %r"
                    % (r["id"], f[:40]))
            # 分片切分处的首尾空白不属载荷内容（序列化器在取值边界 strip），
            # 故比对前两侧 strip；片段非空白内容仍须整串落点于声明位点。
            elif not any(f.strip() in c for c in captured):
                err("b.frag_off_site", "%s: 载荷片段未落在声明位点 %s 的取值里"
                    % (r["id"], m))
    # 在训位点正对照
    for r in items["ctl"]:
        m = intent_of(r)[0]
        if m != B.CONTROL_MECH:
            err("b.ctl_mech", "%s: 对照条机理应为 %s，实为 %r"
                % (r["id"], B.CONTROL_MECH, m))
        if "训练侧机理=" not in r["intent"]:
            err("b.ctl_note", "%s: 对照条 intent 未标注训练侧机理" % r["id"])
        for k in B.CONTROL_SITE_KEYS:
            if not sites_live.get(k, 0):
                err("b.ctl_site", "对照位点键 %s 在活谱系没出现（对照前提不成立）"
                    % k)
    if Counter(intent_of(r)[0] for r in items["ctl"]).get(
            B.CONTROL_MECH, 0) != len(B.CONTROL_PLAN):
        err("b.ctl_count", "对照条数 != CONTROL_PLAN %d" % len(B.CONTROL_PLAN))
    if B.CONTROL_MECH in (manifest["claims"]["unseen_mechanism"] or []):
        err("b.ctl_in_claim", "claims.unseen_mechanism 含对照机理")
    if sorted(mech_items) != sorted(B.GATE_MECHS):
        err("b.claim_mech_set", "条目机理集 %s != 门禁机理集 %s"
            % (sorted(mech_items), sorted(B.GATE_MECHS)))
    if sorted(manifest["claims"]["unseen_mechanism"] or []) != \
            sorted(B.GATE_MECHS):
        err("b.claim_mech_set", "claims.unseen_mechanism=%r 与门禁机理集不一致"
            % manifest["claims"]["unseen_mechanism"])
    # 干净负例：每个门禁机理都要有阴性对照
    cln_sites = Counter(intent_of(r)[0] for r in items["cln"])
    for m in B.GATE_MECHS:
        if not cln_sites.get(m):
            err("b.no_clean_control",
                "门禁机理 %s 无干净负例（有 claim 但无阴性对照）" % m)
    for r in items["cln"]:
        m = intent_of(r)[0]
        if m in B.GATE_MECHS:
            if not any(re.search(rx, r["query"])
                       for rx in B.GATE_MECHS[m]["value_res"]):
                err("b.clean_site_absent",
                    "%s: 干净负例的位点 %s 在 query 里不存在" % (r["id"], m))
        carrier = r["query"][r["query"].find("<carrier"):
                             r["query"].find("</carrier>")]
        if B.DIRECTIVE_HINT.search(carrier):
            err("b.clean_directive", "%s: 干净负例载体含指令型文本" % r["id"])
    sem = census["semantics_coverage"]
    note("语义层覆盖：%d/%d 条语义要求在活谱系里出现过 ⇒ 本集只声明"
         "**结构位点层**未见性（claims.unseen_mechanism_scope=%r）"
         % (sum(1 for v in sem.values() if v), len(sem),
            manifest["claims"].get("unseen_mechanism_scope")))


# --------------------------------------------------------------------------
def check_c_overlap(items, manifest, fast=False, rescan=False):
    head("(c) 与训练语料 / 既有留出集零重叠")
    rows = items["rows"]
    ids = {r["id"] for r in rows}
    queries = {sha256_bytes(r["query"]) for r in rows}
    bodies = set()
    for r in rows:
        m = re.search(r"<body>\n(.*?)\n</body>", r["query"], re.S)
        if m:
            bodies.add(m.group(1)[:60])
    others = [d for d in sorted((ROOT / "data" / "heldout").iterdir())
              if d.is_dir() and d.name != GATE_DIR.name]
    n_other = 0
    for d in others:
        for p in sorted(d.glob("*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                n_other += 1
                if o.get("id") in ids:
                    err("c.heldout_id", "id 与 %s 冲突：%s"
                        % (p.relative_to(ROOT), o.get("id")))
                q = o.get("query") or ""
                if q and sha256_bytes(q) in queries:
                    err("c.heldout_query", "query 全文与 %s 冲突：%s"
                        % (p.relative_to(ROOT), o.get("id")))
                mb = re.search(r"<body>\n(.*?)\n</body>", q, re.S)
                if mb and mb.group(1)[:60] in bodies:
                    err("c.heldout_body", "正文前 60 字与 %s 冲突：%s"
                        % (p.relative_to(ROOT), o.get("id")))
    note("三重比对（id / query 全文 / 正文前 60 字）：%d 个既有留出集、%d 条，"
         "零冲突" % (len(others), n_other))
    # 整语料逐行 sha256
    if fast:
        warn("c.skipped", "--fast：跳过整语料逐行 sha256 复算")
    else:
        nbytes = nlines = ncarrier = 0
        for p in B.scan_paths("full"):
            with p.open("rb") as f:
                for raw in f:
                    nbytes += len(raw)
                    s = raw.strip()
                    if not s:
                        continue
                    nlines += 1
                    if sha256_bytes(s) in queries:
                        err("c.line_hash", "训练行与门禁 query 逐字节相同：%s"
                            % p.relative_to(ROOT))
                    if B.DOC_MARK not in raw and b"<carrier" not in raw:
                        continue
                    try:
                        obj = json.loads(s.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    for v in _texts_with(obj, "<carrier"):
                        ncarrier += 1
                        if sha256_bytes(v) in queries:
                            err("c.carrier_query",
                                "训练侧载体渲染文本与门禁 query 相同：%s"
                                % p.relative_to(ROOT))
        note("整语料逐行 sha256：%.2f GB / %d 行 / %d 个载体渲染文本，零命中"
             % (nbytes / 1e9, nlines, ncarrier))
    # document 子集 60 字节窗口独立复算 + 短片段包含
    adv_all = items["unseen"] + items["ctl"]
    raw_w, content_w = set(), set()
    frags = set()
    for r in adv_all + items["cln"]:
        raw_w |= B.raw_windows(r["query"])
        content_w |= B.content_windows(r["query"])
    for r in adv_all:
        for f in B.parse_frags(r["intent"]):
            if len(f.encode("utf-8")) >= B.SHORT_FRAG_MIN:
                frags.add(f)
    keys = B.windows_key_index(raw_w)
    g12 = {}
    gp = {}
    for r in items["rows"]:
        for w in B.content_residue(r["query"], B.CONTENT_MIN):
            g12.setdefault(w, []).append(r["id"])
        for w in B.prose_windows(r["query"], B.CONTENT_MIN):
            gp.setdefault(w, []).append(r["id"])
    nrows = 0
    schema_hits = sub_window = overlap_hits = 0
    sk_share = pr_share = 0
    sk_max = pr_max = 0
    frag_hits = prose_hits = residue_hits = 0
    for p in B.scan_paths("full"):
        with p.open("rb") as f:
            for raw in f:
                if B.DOC_MARK not in raw:
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                for q in B.extract_document_queries(obj):
                    nrows += 1
                    bq = q.encode("utf-8")
                    for fr in frags:
                        if fr.encode("utf-8") in bq:
                            frag_hits += 1
                            err("c.fragment", "载荷片段整串出现在训练 document"
                                " 行 %s：%r" % (p.name, fr[:40]))
                    for w in set(gp) & B.prose_windows(q, B.CONTENT_MIN):
                        prose_hits += 1
                        err("c.prose_share",
                            "散文层 %d 字节窗口命中训练 document 行 %s：%r"
                            "（门禁条目 %s）"
                            % (B.CONTENT_MIN, p.name,
                               w.decode("utf-8", "replace"), gp[w][:3]))
                    for w in set(g12) & B.content_residue(q, B.CONTENT_MIN):
                        residue_hits += 1
                    for _, off, w in B.scan_bytes(bq, keys, raw_w, src=p.name):
                        sk, pr = B.window_hit_kinds(q, off)
                        cb = sk + pr
                        if cb == 0:
                            schema_hits += 1
                        elif w in content_w:
                            overlap_hits += 1
                            err("c.content_window", "内容窗口命中训练 document 行"
                                " %s：%r" % (p.name,
                                             w.decode("utf-8", "replace")))
                        elif cb < B.CONTENT_MIN:
                            sub_window += 1
                        elif pr == 0:
                            sk_share += 1
                            sk_max = max(sk_max, cb)
                        else:
                            pr_share += 1
                            pr_max = max(pr_max, cb)
                            if pr_share <= EXAMPLE_MAX:
                                err("c.raw_prose_share",
                                    "原始 60 字节窗口含 >=%d 字节**散文**字节"
                                    "（%d 字节）命中 %s：%r"
                                    % (B.CONTENT_MIN, pr, p.name,
                                       w.decode("utf-8", "replace")))
    note("document 训练子集（%d 行）独立复算：原始 60 字节窗口命中 %d = schema 区 "
         "%d + 亚阈值(<%d 字节) %d + 内容重叠 %d + 长共享-骨架行 %d（最长 %d 字节）"
         " + 长共享-散文行 %d（最长 %d 字节，须为 0）"
         % (nrows, schema_hits + sub_window + overlap_hits + sk_share + pr_share,
            schema_hits, B.CONTENT_MIN, sub_window, overlap_hits, sk_share,
            sk_max, pr_share, pr_max))
    note("散文层 %d 字节窗口命中 %d（须为 0）；短片段(>=%d 字节)整串包含命中 %d；"
         "细粒度残渣诊断命中 %d（不设阈值）"
         % (B.CONTENT_MIN, prose_hits, B.SHORT_FRAG_MIN, frag_hits,
            residue_hits))
    # _work 产物时效性 / 读数
    art = manifest["artifacts"]["overlap_scan"]
    ap_ = GATE_DIR / art
    if rescan:
        rep = B.overlap_scan(scope=manifest["overlap"]["scope"],
                             use_cache=False, verbose=False)
    elif not ap_.exists():
        err("c.artifact", "缺重叠扫描产物 %s" % art)
        rep = None
    else:
        rep = json.loads(ap_.read_text(encoding="utf-8"))
        if rep.get("fingerprint") != B._file_fingerprint(
                B.scan_paths(rep["scope"])):
            err("c.artifact_stale", "重叠扫描产物语料指纹已失效")
        if rep.get("rev") != B.OVL_REV:
            err("c.artifact_rev", "重叠扫描口径版本 rev=%r != 当前 %d"
                % (rep.get("rev"), B.OVL_REV))
    if rep:
        if rep.get("limited_mb"):
            err("c.artifact_limited", "重叠扫描是受限扫描（limited_mb=%r）"
                % rep["limited_mb"])
        for k in ("raw_hits_content_overlap", "prose_share_hits",
                  "short_fragment_hits", "raw_hits_long_share_prose"):
            v = rep.get(k)
            if v is None:
                err("c.artifact_keys", "重叠扫描产物缺键 %s" % k)
            elif len(v) != 0:
                err("c.artifact_hits", "重叠扫描 %s=%d != 0" % (k, len(v)))
        if rep.get("prose_share_hits_count"):
            err("c.artifact_hits", "散文层窗口命中 %d != 0"
                % rep["prose_share_hits_count"])
        if rep.get("short_fragment_hits_count"):
            err("c.artifact_hits", "载荷片段整串包含命中 %d != 0"
                % rep["short_fragment_hits_count"])
        if rep.get("long_share_max_prose_bytes"):
            err("c.artifact_hits", "长共享散文字节上限 %r != 0"
                % rep["long_share_max_prose_bytes"])
        if rep.get("hits_content_vs_corpus_count", 0) != 0:
            err("c.artifact_hits", "全语料内容窗口命中 %r != 0"
                % rep.get("hits_content_vs_corpus_count"))
        note("全语料扫描产物（%.1f KB，盘上文件）：%.2f GB / %d 原始窗口 / %d 内容窗口；"
             "内容命中 %d；散文层判据 %d 字节窗口 %d 个"
             % ((ap_.stat().st_size if ap_.exists() else
                 (rep.get("artifact_bytes") or 0)) / 1024,
                rep["corpus_bytes"] / 1e9, rep["gate_windows_raw"],
                rep["gate_windows_content"],
                rep.get("hits_content_vs_corpus_count", 0),
                rep.get("content_min", B.CONTENT_MIN),
                rep.get("prose_gate_windows", 0)))
        note("60 字节原始窗口命中 %d 的归因：schema 区 %d + 亚阈值(<%d 字节) %d + "
             "内容重叠 %d + 长共享-骨架行 %d（最长 %r 字节，序列化器模板值）"
             " + 长共享-散文行 %d（最长 %r 字节，须为 0）"
             % (rep["raw_hits_total"], rep["raw_hits_schema_region"],
                rep.get("sub_window_criterion_bytes", B.CONTENT_MIN),
                rep.get("raw_hits_sub_window", 0),
                len(rep["raw_hits_content_overlap"]),
                rep.get("raw_hits_long_share_skeleton_count", 0),
                rep.get("long_share_max_skeleton_bytes"),
                rep.get("raw_hits_long_share_prose_count", 0),
                rep.get("long_share_max_prose_bytes")))
        note("细粒度残渣诊断（两侧剔除机械 token，%d 字节窗口）命中 %d："
             "不设阈值，构成=序列化器骨架词/机制名/通用短语（样例见 manifest）"
             % (rep.get("content_min", B.CONTENT_MIN),
                rep.get("residue_hits_count", 0)))
        if (rep.get("artifact_bytes") or 0) > 8 << 20:
            warn("c.artifact_size", "重叠扫描产物 %.1f MB 偏大（应只存计数/哈希）"
                 % (rep["artifact_bytes"] / (1 << 20)))
        for k, want in (("rev", B.OVL_REV),
                        ("content_hits_vs_corpus", 0),
                        ("prose_share_hits", 0),
                        ("short_fragment_hits", 0),
                        ("raw_hits_long_share_prose", 0),
                        ("long_share_max_prose_bytes", 0)):
            v = manifest["overlap"].get(k)
            if v != want:
                err("c.manifest_overlap", "manifest.overlap.%s=%r != %r"
                    % (k, v, want))


def _texts_with(obj, needle):
    out = []

    def walk(v):
        if isinstance(v, str):
            if needle in v:
                out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(obj)
    return out


# --------------------------------------------------------------------------
def check_d_smoke(items):
    head("(d) 可判性冒烟（score_heldout_v2，未改动；selfreport + strict 双口径）")
    try:
        from score_heldout_v2 import score_items
    except ImportError as e:  # pragma: no cover
        err("d.import", "无法导入 score_heldout_v2.score_items：%s" % e)
        return
    rob = items["unseen"] + items["ctl"]
    for rule in ("selfreport", "strict"):
        resp_good, resp_bad = {}, {}
        for r in rob:
            gm = re.search(r"正确行为=(.*?)；注入要求=", r["intent"], re.S)
            bm = re.search(r"注入要求=(.*)$", r["intent"], re.S)
            if not gm or not bm:
                err("d.intent", "%s: intent 缺 正确行为/注入要求" % r["id"])
                continue
            resp_good[r["id"]] = gm.group(1).strip()
            resp_bad[r["id"]] = bm.group(1).strip()
        rep_good = score_items(rob, resp_good, action_rule=rule)
        rep_bad = score_items(rob, resp_bad, action_rule=rule)
        bg = [x for x in rep_good["items"]
              if x["label"] not in ("report_finding", "refuse")]
        bb = [x for x in rep_bad["items"] if x["label"] != "comply"]
        for x in bg:
            err("d.good_not_defensive", "[%s] 正确行为文本未判为防御（%s）：%s"
                % (rule, x["label"], x["id"]))
        for x in bb:
            err("d.bad_not_comply", "[%s] 注入要求文本未判为顺从（%s）：%s"
                % (rule, x["label"], x["id"]))
        note("[%s] 对抗条 %d：正确行为→防御 %d/%d；注入要求→顺从 %d/%d"
             % (rule, len(rob), len(rob) - len(bg), len(rob),
                len(rob) - len(bb), len(rob)))
        cln = items["cln"]
        if cln:
            resp_c = {}
            for r in cln:
                m = re.search(r"正确行为=(.*)$", r["intent"], re.S)
                if m:
                    resp_c[r["id"]] = m.group(1).strip()
            rep_c = score_items(cln, resp_c, action_rule=rule)
            refused = [x for x in rep_c["items"]
                       if x["label"] in ("refuse", "deflect")]
            for x in refused:
                err("d.clean_overrefusal",
                    "[%s] 干净负例正确行为被判为 %s（口径不自洽）：%s"
                    % (rule, x["label"], x["id"]))
            note("[%s] 干净负例 %d 条：非拒 %d/%d（over_refusal=%s）"
                 % (rule, len(cln), len(cln) - len(refused), len(cln),
                    rep_c["metrics"]["over_refusal_rate"]))


# --------------------------------------------------------------------------
def check_e_claims(items, manifest, census, require_unseen_carrier=None):
    head("(e) manifest.claims 机器可读声明（按被评模型索引）")
    c = manifest.get("claims") or {}
    if c.get("carrier") != "document":
        err("e.carrier", "claims.carrier 必须为 document")
    if c.get("unseen_carrier") is not False:
        err("e.unseen_carrier", "claims.unseen_carrier 必须为 false"
            "（顶层 = 主登记产物 m3-dpo）")
    if c.get("min_denominator") != B.MIN_DENOMINATOR:
        err("e.denominator", "claims.min_denominator=%r != %d"
            % (c.get("min_denominator"), B.MIN_DENOMINATOR))
    if (c.get("robustness_n") or 0) < B.MIN_DENOMINATOR:
        err("e.denominator", "claims.robustness_n=%r < %d"
            % (c.get("robustness_n"), B.MIN_DENOMINATOR))
    if c.get("unseen_mechanism_scope") != "structure_site_only":
        err("e.scope", "claims.unseen_mechanism_scope 必须为 structure_site_only")
    pm = c.get("per_model") or {}
    if not pm:
        err("e.per_model", "claims.per_model 缺失（结论必须按被评模型索引）")
    for name, cfg in B.MODEL_BINDINGS.items():
        got = pm.get(name)
        if not got:
            err("e.per_model", "claims.per_model 缺 %s" % name)
            continue
        measured = sum(census["document_rows_by_file"].get(f, 0)
                       for f in cfg["train_files"])
        if got.get("document_rows_measured") != measured:
            err("e.per_model_rows", "per_model[%s].document_rows_measured=%r"
                " != 复算 %d" % (name, got.get("document_rows_measured"),
                                measured))
        if bool(got.get("carrier_seen")) != bool(measured):
            err("e.per_model_seen", "per_model[%s].carrier_seen=%r 与实测 %d 行"
                "不一致" % (name, got.get("carrier_seen"), measured))
        sup = got.get("supports") or []
        if got.get("carrier_seen") and "unseen_carrier" in sup:
            err("e.per_model_support", "per_model[%s] 训过 document 却声明"
                " unseen_carrier" % name)
        if (not got.get("carrier_seen")) and "unseen_carrier" not in sup:
            err("e.per_model_support", "per_model[%s] 未训 document 却未声明"
                " unseen_carrier" % name)
        note("per_model[%s]：document 行=%d，carrier_seen=%s，supports=%s"
             % (name, measured, got.get("carrier_seen"), sup))
    m3 = pm.get("m3-dpo") or {}
    if m3.get("carrier_seen") is not True or m3.get("unseen_carrier"):
        err("e.m3", "m3-dpo 训了 1,000 条 document ⇒ carrier_seen 必须 true、"
            "未见载体声明必须 false")
    if "unseen_carrier" in (m3.get("supports") or []):
        err("e.m3_support", "m3-dpo 不得声明 unseen_carrier")
    if require_unseen_carrier:
        got = pm.get(require_unseen_carrier)
        if not got:
            err("e.require_unseen_carrier", "%s 不在 per_model 里"
                % require_unseen_carrier)
        elif got.get("carrier_seen") or "unseen_carrier" not in (
                got.get("supports") or []):
            err("e.require_unseen_carrier", "%s：carrier_seen=%r supports=%r"
                " ⇒ 不构成未见载体门禁" % (require_unseen_carrier,
                                        got.get("carrier_seen"),
                                        got.get("supports")))
        else:
            note("--require-unseen-carrier %s：通过（document 行 0，supports 含"
                 " unseen_carrier）" % require_unseen_carrier)
    if (c.get("semantics_coverage") or {}) != census["semantics_coverage"]:
        err("e.semantics", "claims.semantics_coverage 与普查复算不一致")
    txt = "\n".join(r["intent"] for r in items["rows"])
    if "未见载体泛化" in txt:
        warn("e.wording", "条目文本里出现「未见载体泛化」字样（应只出现在"
             " forbidden_wording 里）")


def check_f_hygiene(items, manifest, census):
    head("(f) 仪器卫生：白名单行为断言 / 位点登记 / 两类 sha256 / 可复现")
    # 白名单：行为断言（不是子串匹配）
    synth = {"filename": "filename: probe.docx", "title": "title: probe",
             "creator": "creator: probe", "author": "author: probe",
             "custom-metadata-keys": "custom-metadata-keys: probe (3 total)",
             "fonts": "fonts: probe, Calibri",
             "relationship": "  relationship [id: rId1] [target: probe]",
             "field": "    field [name: probe]",
             "annotation": "    annotation [subtype: Link] [target: probe]",
             "embedded-file": "embedded-file [1] [name: probe]"}
    for k in B.PAYLOAD_SITE_KEYS:
        line = synth.get(k, k + ": probe")
        if B.is_schema_line(line):
            err("f.whitelist_hides", "schema 白名单把载荷位点行判为模板行：%r"
                % line)
    inter = set(B.PAYLOAD_SITE_KEYS) & set(B.SCHEMA_META_KEYS)
    if inter:
        err("f.whitelist_key", "白名单 meta 键集含载荷位点键：%s" % sorted(inter))
    note("白名单行为断言通过：%d 个载荷位点键**均不被**判为模板行；"
         "白名单 %d 条规则 / %d 个 meta 键"
         % (len(B.PAYLOAD_SITE_KEYS), len(B.SCHEMA_LINE_RES),
            len(B.SCHEMA_META_KEYS)))
    # 两类 sha256，分开断言、分开说明对象
    file_sha = sha256_bytes(items["text"])
    if manifest.get("sha256") != file_sha:
        err("f.sha_file", "[对象=文件内容] manifest.sha256=%r != 读盘复算 %r"
            % (manifest.get("sha256"), file_sha))
    else:
        note("[对象=文件内容] manifest.sha256 == 读盘复算 %s" % file_sha)
    rebuilt = B.dumps_rows(B.assemble_rows())
    rebuilt_sha = sha256_bytes(rebuilt)
    if rebuilt_sha != file_sha:
        err("f.rebuild", "[对象=现场重装配] sha256=%s != 文件内容 sha256 %s"
            % (rebuilt_sha, file_sha))
    else:
        note("[对象=现场重装配] sha256 与文件内容一致 ⇒ 构建器逐字节可复现")
    if manifest.get("seed") != B.SEED:
        err("f.seed", "manifest.seed=%r != 构建器 SEED %r"
            % (manifest.get("seed"), B.SEED))
    if manifest["train_side"]["document_rows"] != census["document_rows"]:
        err("f.census_rows", "manifest 训练侧行数 %r != 普查 %d"
            % (manifest["train_side"]["document_rows"],
               census["document_rows"]))
    if manifest["train_side"]["live_document_rows"] != \
            census["live_document_rows"]:
        err("f.census_live", "manifest 活谱系行数 %r != 普查 %d"
            % (manifest["train_side"]["live_document_rows"],
               census["live_document_rows"]))
    ts = manifest["train_side"]
    lev = ts["envelope_live_lineage_rows"]
    if sum(lev.values()) != census["live_document_rows"]:
        err("f.envelope_live",
            "[对象=活谱系行] envelope_live_lineage_rows 合计 %d != 活谱系行数 %d"
            % (sum(lev.values()), census["live_document_rows"]))
    elif lev.get("meta_and_dom") or lev.get("meta_only") or lev.get("dom_only"):
        warn("f.envelope_live_meta",
             "[对象=活谱系行] 活谱系出现 <meta>/<dom> 信封（M3 document 行不应有）"
             "：%r" % lev)
    else:
        note("[对象=活谱系行] %d 行 document 全为 body-only 信封：%r ⇒ 门禁的 "
             "<meta>/<dom> 结构对该模型也是未见形态"
             % (sum(lev.values()), lev))
    cev = ts["envelope_candidate_pool_rows"]
    if sum(cev.values()) != census["document_rows"]:
        err("f.envelope_pool",
            "[对象=候选池行] envelope_candidate_pool_rows 合计 %d != document 行 "
            "%d" % (sum(cev.values()), census["document_rows"]))
    else:
        note("[对象=候选池行] %d 行 document（含分支副本；唯一载体 %d 个）信封分布"
             "：%r" % (sum(cev.values()), census["distinct_carrier_queries"], cev))


# --------------------------------------------------------------------------
def partition(rows):
    """按角色分桶（各检查段与回归测试的公共输入）。"""
    adv_all = [r for r in rows if r["kind"] == "robustness"]
    return {
        "rows": rows,
        "adv": adv_all,
        "unseen": [r for r in adv_all
                   if "control=trained_site" not in r["intent"]],
        "ctl": [r for r in adv_all if "control=trained_site" in r["intent"]],
        "cln": [r for r in rows if r["kind"] == "alignment"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="v0.6-document 门禁集检查器")
    ap.add_argument("--fast", action="store_true", help="跳过整语料逐行 sha256")
    ap.add_argument("--rescan", action="store_true", help="现场重跑全量窗口扫描")
    ap.add_argument("--require-unseen-carrier", default=None, metavar="MODEL")
    ap.add_argument("--stats-out", default=None)
    args = ap.parse_args(argv)

    print("document 门禁集检查：%s" % GATE_FILE.relative_to(ROOT))
    for p in (GATE_FILE, MANIFEST):
        if not p.exists():
            print("[FAIL] 缺文件：%s" % p)
            print("%s errors=1" % FAIL)
            return 1
    rows, raws, text = load_gate_rows()
    # 时序规则（docs/01 §11.25：症状不是原因）：jsonl 比 manifest 新 ⇒ 清单滞后
    if GATE_FILE.stat().st_mtime > MANIFEST.stat().st_mtime + 1e-6:
        err("0.manifest_stale",
            "清单滞后于产物（artifact newer than manifest）：jsonl mtime=%s > "
            "manifest mtime=%s ⇒ 先冻结 jsonl 再生成 manifest"
            % (int(GATE_FILE.stat().st_mtime), int(MANIFEST.stat().st_mtime)))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    census_path = GATE_DIR / manifest["artifacts"]["train_mechanism_inventory"]
    if not census_path.exists():
        print("[FAIL] 缺训练机理普查产物 %s" % census_path)
        print("%s errors=1" % FAIL)
        return 1
    census = json.loads(census_path.read_text(encoding="utf-8"))
    if census.get("fingerprint") != B._file_fingerprint(
            B.scan_paths(census["scope"])):
        err("0.census_stale", "训练机理普查指纹已失效（语料变了，重跑 --census）")
    for k in B.CENSUS_KEYS:
        if k not in census:
            err("0.census_stale", "训练机理普查缺键 %s（重跑 --census）" % k)

    items = partition(rows)
    items.update({"raws": raws, "text": text})
    # 失败闭合：任何检查段的意外异常都记为错误（而不是崩溃出栈），
    # 使「仪器故障」与「产物有问题」都收敛到 FAIL 哨兵行；DOC_GATE_TRACEBACK=1
    # 可打印原始栈用于调试。
    for _label, _call in (
            ("a", lambda: check_a_schema(items, manifest)),
            ("b", lambda: check_b_mechanism(items, census, manifest)),
            ("c", lambda: check_c_overlap(items, manifest, fast=args.fast,
                                          rescan=args.rescan)),
            ("d", lambda: check_d_smoke(items)),
            ("e", lambda: check_e_claims(items, manifest, census,
                                         args.require_unseen_carrier)),
            ("f", lambda: check_f_hygiene(items, manifest, census))):
        try:
            _call()
        except Exception as exc:  # noqa: BLE001
            err("%s.crash" % _label, "%s 段异常：%s: %s"
                % (_label, type(exc).__name__, exc))
            if os.environ.get("DOC_GATE_TRACEBACK"):
                traceback.print_exc()

    # --- 聚合输出：每类样例 + 计数 + 种类表 ---
    if ERRORS:
        print("\n== 错误种类表（控制台只列每类前 %d 条样例）" % EXAMPLE_MAX)
        for cat, (n, ex) in ERRORS.items():
            print("  [%s] ×%d" % (cat, n))
            for e in ex:
                print("      · %s" % e)
    if WARNS:
        print("\n== 警告种类表")
        for cat, (n, ex) in WARNS.items():
            print("  [%s] ×%d  %s" % (cat, n, ex[0] if ex else ""))
    if args.stats_out:
        out = {
            "n_items": len(rows),
            "errors_total": n_err(),
            "errors_by_category": {k: v[0] for k, v in ERRORS.items()},
            "error_examples": {k: v[1] for k, v in ERRORS.items()},
            "warns_by_category": {k: v[0] for k, v in WARNS.items()},
            "notes": NOTES,
            "census": {
                "document_rows": census["document_rows"],
                "live_document_rows": census["live_document_rows"],
                "present_sites": sorted(
                    k for k, v in census["train_structure_sites"].items() if v),
                "present_sites_live": sorted(
                    k for k, v in census["train_structure_sites_live"].items()
                    if v),
                "live_mechanisms": census["live_mechanisms"],
                "semantics_coverage": census["semantics_coverage"],
                "live_envelope": census["envelope_live_lineage_rows"],
                "candidate_pool_envelope":
                    census["envelope_candidate_pool_rows"],
                "distinct_carrier_queries": census["distinct_carrier_queries"],
            },
        }
        Path(args.stats_out).write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8",
            newline="\n")
        print("\nstats -> %s（逐条明细）" % args.stats_out)
    print()
    if ERRORS:
        print("%s errors=%d" % (FAIL, n_err()))
        return 1
    print(PASS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
