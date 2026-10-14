# -*- coding: utf-8 -*-
"""C 路补齐「三族行为观测仪」独立校验器（硬断言；任一失败 → 非零退出）。

对象：data/heldout/v0.5-topup-families/{t2_mechanism,doc_structure,t9_phish}.jsonl
用途：reports/c-path-topup-preregistration.md §3 的**观测项**——判定 topup（S1 三族
      低 LR 补训）是否真的学到了 T2 机理 / T15 文档结构 / T9 钓鱼话术三族行为，
      用来识破"主判据通过但三族零提升"的伪通过（防伪）模式。

本校验器**不复用生成器的任何自报数据**：对象侧只用探针 jsonl，基线侧只读
data/sft/m2.5-staging/*.jsonl 与 data/heldout/v0.{2.1,3-gen,4-toolout}/。

--------------------------------------------------------------------------
train-disjoint 裁定口径（与 scripts/check_sft_contamination.py 同源：
官方匹配器用「预筛：连续共享 8-gram ≥40 个」+「LCS ≥60 字符」判定真嵌入；
本校验器比它更严，明确把 schema 模板与内容分开）
--------------------------------------------------------------------------
1) 行级 schema 剥离：探针 user 文本按行切分后，满足下列任一条的整行视为
   **schema 行**（不进内容比对，仅登记审计）：
     a. 该行规范化后在同族同语言训练集 ≥2 行中原样出现（信封/HTML 骨架/
        T15 块标签/macro 记录等逐字复用行）；
     b. 该行形如 `<meta键>: 值`，键 ∈ 训练侧 `<meta>` 出现过的键名词表，
        且键 ≠ title（title 是自撰自由文本，按内容比对）；
     c. 该行以 `macro-stream [` 开头（训练侧 macro 记录模板，值另行核对）。
2) gram 级 schema 词元：同族同语言训练集 ≥5 行都出现的 8-gram（`<input `、
   `method="`、`https://`、`.example`、` trace-i` 等 schema 词元及跨行边界片段）
   不计命中，但**全部逐条登记**在报告里供人工复核。
3) 硬闸：
     C1  探针 user 文本与同族训练 user 文本**精确同文 = 0**；
     C2  内容级 8-gram 命中（按 1)+2) 剥离后）= 0；
     C3  内容级连续共享 8-gram 游程 < RUN_MAX（⇒ 无 ≥RUN_MAX+7 字符连续同文）；
     C4  载荷区（T15：<body> 可见行与 `text:` 值；T9：<dom> 文本节点与
         action/name/id 属性值）8-gram 命中 = 0；
     C5  主机名：探针任一 host 不得作为子串出现在任一训练 user 文本中；
     C6  meta 值不复用：探针 `<meta>` 标量值与同键训练值集合零交集，
         macro 记录 size 与训练侧 size 集合零交集。

其余硬闸：schema 逐字/取值域、跨留出集零重叠、配比、语言、虚构性、政策三元组。
输出：reports/topup-family-probe-stats.json（含全部被剥离项，可复核）。
用法：python scripts/check_topup_family_probe.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_sft_contamination import normalize, ngrams  # noqa: E402  官方规范化/8-gram

PROBE_DIR = ROOT / "data" / "heldout" / "v0.5-topup-families"
STAGE = ROOT / "data" / "sft" / "m2.5-staging"
HELDOUT = [ROOT / "data" / "heldout" / v
           for v in ("v0.2.1", "v0.3-gen", "v0.4-toolout")]
OUT = ROOT / "reports" / "topup-family-probe-stats.json"

NGRAM_N = 8
LINE_SCHEMA_MIN_ROWS = 2      # 行级：同族同语言训练集 ≥N 行原样出现 ⇒ schema 行
GRAM_SCHEMA_MIN_ROWS = 5      # gram 级：同族同语言训练集 ≥N 行出现 ⇒ schema 词元
RUN_MAX = 8                   # 内容级连续共享 8-gram 游程上限（⇒ < 15 字符连续同文）
RUN_RAW_MAX = 20              # 含 schema 词元的连续共享游程上限（⇒ < 27 字符连续同文，
                              #   仍远严于官方匹配器的 50 gram 预筛 / 60 字符 LCS 判定）
CONTENT_TITLE = "title"       # 自由文本键：按内容比对（其余 <meta> 键按 schema 剥离）
FAMILIES = {
    "T2": {"probe": "t2_mechanism.jsonl",
           "train": ["t2_mechanism.jsonl"], "env": False},
    "T15": {"probe": "doc_structure.jsonl",
            "train": ["doc_structure.jsonl"], "env": True},
    "T9": {"probe": "t9_phish.jsonl",
           "train": ["t9_phish_expand.jsonl", "t9_phishing.jsonl"], "env": True},
}
PACKS = ("conservative", "default", "professional")
LANGS = ("zh", "en")
TOP_KEYS = {"id", "task", "pack", "lang", "messages"}
MSG_KEYS = {"role", "content"}
VKEYS = {"action", "verdict", "confidence", "findings", "policy"}
ACTIONS = {"answer", "refuse", "report"}
_CJK = re.compile(r"[\u4e00-\u9fff]")
HOST_OK = re.compile(r"^(?:[a-z0-9-]+\.)*(?:example|example\.com|example\.net|"
                     r"example\.org|attacker\.example)$")
HOST_RE = re.compile(r"(?:https?|ftp)://([A-Za-z0-9._-]+)")
IP_HOST_OK = re.compile(r"^198\.51\.100\.(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$")
# 负例判据（逐族显式）：干净负例 = 参考裁决落在"非攻击/非上报"分支
NEG_KINDS = {"T2": {"neg", "poln"}, "T15": set(), "T9": set()}
NEG_VERDICT = {"T2": set(), "T15": {"clean"}, "T9": {"benign"}}
META_LINE_RE = re.compile(r"^([a-z][a-z0-9-]*): (.*)$")
ATTR_RE = re.compile(r'="[^"]*"')
# 身份型 meta 键（取值必须**新**，复用训练侧取值即判失败）
IDENTIFYING_META = {"filename", "title", "created", "modified", "size-bytes",
                    "producer", "url", "fetched"}
# 其余 meta 键为**枚举/结构型**：闭合词表的键必须落在训练侧取值集合内；
# 开放取值的键只要求**取值形状类**与训练侧一致（int / int-paren / 单token / 多词）。
CLOSED_VOCAB = {"detected-container", "macros", "javascript", "pdf-version"}


def shape_class(v: str) -> str:
    v = v.strip()
    if re.fullmatch(r"\d+", v):
        return "int"
    if re.match(r"^\d+ \(", v):
        return "int-paren"
    if re.fullmatch(r"[A-Za-z0-9._+-]+", v):
        return "token"
    return "text"


def mask_attrs(text: str) -> str:
    """把 HTML 属性值抹成占位符：属性槽是 schema 位（主机名由 C5 单独断言、
    取值域由 C6 单独断言），不做 8-gram 内容比对，避免
    `id="f-xx34" action="…"` 这类**属性值↔schema词元**的边界假命中。"""
    return ATTR_RE.sub('="…"', text)


# schema 注解：T9 的 [collects: …] / [sensitive-input] 是全族共用的模板注解，
# 与属性值同理抹成占位符；其内容由 C5/C6 与载荷区断言单独覆盖。
ANNOT_RE = re.compile(r"\[collects: [^\]]*\]|\[sensitive-input\]")
# 操作者任务行里的载体编号行（信封模板）
TRACEID_RE = re.compile(r"^[（(](?:文件编号|document ref) trace-id:")


def mask_annot(text: str) -> str:
    return ANNOT_RE.sub("[…]", text)


def load_jsonl(p: Path):
    rows = []
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if line.strip():
                rows.append((i + 1, json.loads(line)))
    return rows


def user_of(r): return next(m["content"] for m in r["messages"] if m["role"] == "user")
def asst_of(r): return next(m["content"] for m in r["messages"] if m["role"] == "assistant")


def verdict_of(r):
    a = asst_of(r)
    if "VERDICT: " not in a:
        return None
    try:
        return json.loads(a.rsplit("VERDICT: ", 1)[1])
    except json.JSONDecodeError:
        return None


def kind_of(rid): 
    p = rid.split("-")
    return p[4] if len(p) > 4 else "?"


def slug_of(rid):
    p = rid.split("-")
    return p[3] if len(p) > 3 else "?"


def meta_pairs(user):
    """<meta> 块内的 (键, 值) 列表。"""
    m = re.search(r"<meta>\n(.*?)\n</meta>", user, re.S)
    if not m:
        return []
    out = []
    for ln in m.group(1).split("\n"):
        mm = META_LINE_RE.match(ln.strip())
        if mm:
            out.append((mm.group(1), mm.group(2).strip()))
    return out


def dom_heads(user):
    m = re.search(r"<dom>\n(.*?)\n</dom>", user, re.S)
    if not m:
        return set()
    return {mm.group(1) for mm in
            (re.match(r"\s*([a-z][a-z0-9-]*)\s*[\[(]", ln)
             for ln in m.group(1).split("\n")) if mm}


def payload_text(fam, user):
    """载荷区（自撰新内容的所在）：T15=<body> 可见行 + `text:` 值；T9=<dom> 文本节点
    与 action/name/id 属性值；T2=全文（无 schema 信封，整段都是自撰）。"""
    if fam == "T2":
        return user
    if fam == "T15":
        m = re.search(r"<body>\n(.*?)\n</body>", user, re.S)
        body = m.group(1) if m else ""
        out = []
        for ln in body.split("\n"):
            t = ln.strip()
            if not t or t.startswith("["):
                continue
            out.append(t[5:].strip() if t.startswith("text:") else t)
        return " | ".join(out)
    m = re.search(r"<dom>\n(.*?)\n</dom>", user, re.S)
    d = m.group(1) if m else ""
    nodes = [x.strip() for x in re.findall(r">([^<>]{2,})<", d) if x.strip()]
    attrs = re.findall(r'(?:action|name|id)="([^"]+)"', d)
    return " | ".join(nodes + attrs)


def run_checks(probe_dir: Path = PROBE_DIR) -> tuple[dict, list[str]]:
    """在给定探针目录上跑全部硬断言，返回 (报告 dict, 错误列表)。
    错误列表非空 ⇒ 调用方应非零退出。真实目录与测试用临时目录走同一条码路。"""
    global PROBE_DIR
    _saved, PROBE_DIR = PROBE_DIR, Path(probe_dir)
    try:
        return _run_checks_impl(Path(probe_dir))
    finally:
        PROBE_DIR = _saved


def _run_checks_impl(probe_dir: Path) -> tuple[dict, list[str]]:
    errors: list[str] = []
    rep: dict = {"probe_dir": str(probe_dir),
                 "criteria": {
                     "ngram_n": NGRAM_N,
                     "line_schema_min_rows": LINE_SCHEMA_MIN_ROWS,
                     "gram_schema_min_rows": GRAM_SCHEMA_MIN_ROWS,
                     "run_max_grams": RUN_MAX,
                     "run_max_chars_equivalent": RUN_MAX + NGRAM_N - 1,
                     "run_raw_max_grams": RUN_RAW_MAX,
                     "run_raw_max_chars_equivalent": RUN_RAW_MAX + NGRAM_N - 1,
                     "repo_official_lcs_min_chars": 60,
                     "repo_official_prefilter_grams": 40,
                 },
                 "families": {}}

    # ---------------- 训练侧基线 ----------------
    train = {f: [r for _, r in load_jsonl(STAGE / fn) if True]
             for f, cfg in FAMILIES.items() for fn in cfg["train"]}
    # 上面的推导会把多文件族的行覆盖掉，这里显式重算
    train = {}
    for f, cfg in FAMILIES.items():
        rows = []
        for fn in cfg["train"]:
            rows += [r for _, r in load_jsonl(STAGE / fn)]
        train[f] = rows
    train_sys = {(f, r["pack"], r["lang"]): r["messages"][0]["content"]
                 for f, rows in train.items() for r in rows}
    train_tasks = {f: {r["task"] for r in rows} for f, rows in train.items()}
    train_user_norm = {f: [normalize(user_of(r)) for r in rows]
                       for f, rows in train.items()}
    # 行级 / gram 级 / meta 键值 / 主机 基线
    line_cnt = collections.defaultdict(collections.Counter)
    gram_cnt = collections.defaultdict(collections.Counter)
    content_gram = {}
    meta_keys = defaultdict = None
    meta_keys = collections.defaultdict(set)
    meta_vals = collections.defaultdict(lambda: collections.defaultdict(set))
    for f, rows in train.items():
        for r in rows:
            lg = r["lang"]
            u = user_of(r)
            for ln in {normalize(x) for x in u.split("\n") if x.strip()}:
                line_cnt[(f, lg)][ln] += 1
            for g in set(ngrams(normalize(u), NGRAM_N)):
                gram_cnt[(f, lg)][g] += 1
            for k, v in meta_pairs(u):
                meta_keys[f].add(k)
                meta_vals[f][k].add(normalize(v))
    t15_meta_vocab = meta_keys["T15"]
    t15_dom_vocab = set()
    for r in train["T15"]:
        t15_dom_vocab |= dom_heads(user_of(r))
    t9_tech = set()
    t9_chan, t9_label = set(), set()
    for r in train["T9"]:
        p = r["task"].split(":")
        if len(p) == 4:
            t9_chan.add(p[1]); t9_tech.add(p[2]); t9_label.add(p[3])
        elif len(p) == 3:
            t9_tech.add(p[1]); t9_label.add(p[2])
    macro_sizes = set()
    for r in train["T15"]:
        macro_sizes |= set(re.findall(r"macro-stream \[\d+\] \[name: [^\]]+\] \[size: (\d+) bytes\]",
                                      user_of(r)))
    train_hosts = set()
    train_urls = set()
    for f, rows in train.items():
        for r in rows:
            u = user_of(r)
            train_hosts |= set(HOST_RE.findall(u))
            train_urls |= {normalize(x) for x in
                           re.findall(r'(?:https?|ftp)://[^\s"<>\]]+', u)}
    rep["train_baseline"] = {
        "rows": {f: len(v) for f, v in train.items()},
        "tasks_T15": sorted(train_tasks["T15"]),
        "meta_vocab_T15": sorted(t15_meta_vocab),
        "dom_vocab_T15": sorted(t15_dom_vocab),
        "T9_techniques": sorted(t9_tech),
        "T9_channels": sorted(t9_chan),
        "T9_labels": sorted(t9_label),
        "macro_sizes_T15": sorted(macro_sizes),
        "hosts": sorted(train_hosts),
    }

    # 内容 gram / schema gram：按族按语言预计算
    schema_grams, content_grams = {}, {}
    for f, rows in train.items():
        for lg in LANGS:
            schema_grams[(f, lg)] = {g for g, c in gram_cnt[(f, lg)].items()
                                     if c >= GRAM_SCHEMA_MIN_ROWS}
            content_grams[(f, lg)] = set(gram_cnt[(f, lg)])

    # ---------------- 跨留出集 ----------------
    holdout_ids, holdout_q, hstat = set(), set(), {}
    for d in HELDOUT:
        ids, qs, n = set(), set(), 0
        for fp in sorted(d.glob("*.jsonl")):
            for _, j in load_jsonl(fp):
                n += 1
                if j.get("id"):
                    ids.add(str(j["id"]))
                if j.get("query"):
                    qs.add(normalize(j["query"]))
        holdout_ids |= ids
        holdout_q |= qs
        hstat[d.name] = {"rows": n, "ids": len(ids), "queries": len(qs)}
    rep["holdout_baseline"] = hstat
    rep["holdout_cross_overlap"] = {"id": [], "query": []}

    # ---------------- 逐族 ----------------
    all_ids = set()
    for fam, cfg in FAMILIES.items():
        p = PROBE_DIR / cfg["probe"]
        if not p.exists():
            errors.append(f"{fam}: 缺少探针文件 {p}")
            continue
        raw = load_jsonl(p)
        st: dict = {"file": cfg["probe"], "rows": len(raw)}
        packs, langs, kinds, slugs, verdicts, actions, tasks = (collections.Counter()
                                                               for _ in range(7))
        n_neg = 0
        exact_users = set()
        dropped_lines, excl_grams = collections.Counter(), collections.Counter()
        content_hits, run_max_seen, run_worst = collections.Counter(), 0, None
        raw_hits_count, raw_run_max, raw_run_worst = 0, 0, None
        raw_runs_long = []
        payload_hits = collections.Counter()
        meta_value_conflicts, host_bad, ip_bad = [], [], []
        enum_value_outside = []
        c2_rows, c4_rows = set(), set()

        for ln_no, r in raw:
            sid = f"{fam}:{cfg['probe']}:{ln_no}:{r.get('id')}"
            if set(r) != TOP_KEYS:
                errors.append(f"{sid}: 顶层键 {sorted(r)} != {sorted(TOP_KEYS)}")
                continue
            if [m.get("role") for m in r["messages"]] != ["system", "user", "assistant"] \
                    or any(set(m) != MSG_KEYS for m in r["messages"]):
                errors.append(f"{sid}: messages 结构/键不符")
                continue
            pk, lg, tk = r["pack"], r["lang"], r["task"]
            if r["id"] in all_ids:
                errors.append(f"{sid}: id 全局重复")
            all_ids.add(r["id"])
            if pk not in PACKS:
                errors.append(f"{sid}: pack 非法 {pk!r}")
            if lg not in LANGS:
                errors.append(f"{sid}: lang 非法 {lg!r}")
            if r["messages"][0]["content"] != train_sys.get((fam, pk, lg)):
                errors.append(f"{sid}: system 串非训练侧同 (pack,lang) 逐字复用")
            u, a = user_of(r), asst_of(r)

            # --- task 取值域 ---
            if fam == "T2":
                if tk != "T2-mechanism":
                    errors.append(f"{sid}: task 非法 {tk!r}（训练侧恒为 T2-mechanism）")
            elif fam == "T15":
                if tk not in train_tasks["T15"]:
                    errors.append(f"{sid}: task 取值域外 {tk!r}")
            else:
                pt = tk.split(":")
                if len(pt) != 4 or pt[0] != "T9-phish":
                    errors.append(f"{sid}: task 文法非法 {tk!r}")
                else:
                    if pt[1] not in t9_chan:
                        errors.append(f"{sid}: channel 域外 {pt[1]!r}")
                    if pt[3] not in t9_label:
                        errors.append(f"{sid}: label 域外 {pt[3]!r}")
                    if pt[2] in t9_tech:
                        errors.append(f"{sid}: technique 与训练侧重名 {pt[2]!r}")

            # --- VERDICT 契约 ---
            v = verdict_of(r)
            if v is None:
                errors.append(f"{sid}: VERDICT 缺失/解析失败")
            else:
                if set(v) != VKEYS:
                    errors.append(f"{sid}: VERDICT 键集异常 {sorted(v)}")
                if list(v) != ["action", "verdict", "confidence", "findings", "policy"]:
                    errors.append(f"{sid}: VERDICT 键序非 action/verdict/confidence/"
                                  f"findings/policy：{list(v)}")
                if v.get("policy") != pk:
                    errors.append(f"{sid}: VERDICT.policy != pack")
                if v.get("action") not in ACTIONS:
                    errors.append(f"{sid}: action 域外 {v.get('action')!r}")
                if not isinstance(v.get("findings"), list):
                    errors.append(f"{sid}: findings 非 list")
                if not isinstance(v.get("confidence"), (int, float)):
                    errors.append(f"{sid}: confidence 非数值")
                actions[str(v.get("action"))] += 1
                verdicts[str(v.get("verdict"))] += 1

            # --- 语言一致性 ---
            env = u.lstrip().startswith("<dsh-protocol")
            if lg == "zh" and not env and len(_CJK.findall(u)) < 10:
                errors.append(f"{sid}: zh 行 user 中文不足 10 字")
            if lg == "en":
                if _CJK.search(u):
                    errors.append(f"{sid}: en 行 user 含中文")
                if _CJK.search(a):
                    errors.append(f"{sid}: en 行 assistant 含中文")

            # --- 负例判据 ---
            if kind_of(r["id"]) in NEG_KINDS[fam] or \
                    (v is not None and str(v.get("verdict")) in NEG_VERDICT[fam]):
                n_neg += 1
            packs[pk] += 1; langs[lg] += 1; kinds[kind_of(r["id"])] += 1
            slugs[slug_of(r["id"])] += 1; tasks[tk] += 1
            exact_users.add(normalize(u))

            # --- C1 精确同文 ---
            # （在族级统一比对）
            # --- C2 内容级 8-gram ---
            meta_kv = meta_pairs(u)
            mk = {k for k, _ in meta_kv}
            keep_lines = []
            for line in u.split("\n"):
                n = normalize(line)
                if not n:
                    continue
                if line_cnt[(fam, lg)][n] >= LINE_SCHEMA_MIN_ROWS:
                    dropped_lines[n] += 1
                    continue
                mm = META_LINE_RE.match(line.strip())
                if mm and mm.group(1) in meta_keys[fam] and mm.group(1) != CONTENT_TITLE:
                    dropped_lines[f"<{mm.group(1)}>: …"] += 1
                    continue
                if line.strip().startswith("macro-stream [") or \
                        TRACEID_RE.match(line.strip()):
                    dropped_lines["macro-stream/ / trace-id 行"] += 1
                    continue
                keep_lines.append(mask_annot(mask_attrs(n)))
            content = " | ".join(keep_lines)
            cg = ngrams(content, NGRAM_N)
            coll, coll_raw = [], []
            for g in cg:
                shared = g in content_grams.get((fam, lg), set())
                coll_raw.append(shared)
                if not shared:
                    coll.append(False); continue
                if g in schema_grams.get((fam, lg), set()):
                    excl_grams[g] += 1
                    coll.append(False)
                else:
                    content_hits[g] += 1
                    c2_rows.add(r["id"])
                    coll.append(True)
            raw_hits_count += sum(coll_raw)
            i, run = 0, 0
            while i < len(coll_raw):
                if not coll_raw[i]:
                    i += 1; continue
                j = i
                while j < len(coll_raw) and coll_raw[j]:
                    j += 1
                run = j - i
                if run > raw_run_max:
                    raw_run_max = run
                    raw_run_worst = (r["id"], content[i:i + run + NGRAM_N - 1])
                if run >= 12:
                    raw_runs_long.append((run, r["id"],
                                          content[i:i + run + NGRAM_N - 1]))
                i = j
            i = 0
            while i < len(coll):
                if not coll[i]:
                    i += 1; continue
                j = i
                while j < len(coll) and coll[j]:
                    j += 1
                if j - i > run_max_seen:
                    run_max_seen = j - i
                    run_worst = (r["id"], content[i:i + (j - i) + NGRAM_N - 1])
                i = j
            # --- C4 载荷区 ---
            for g in set(ngrams(normalize(payload_text(fam, u)), NGRAM_N)):
                if g in content_grams.get((fam, lg), set()) and \
                        g not in schema_grams.get((fam, lg), set()):
                    payload_hits[g] += 1
                    c4_rows.add(r["id"])
            # --- C5 主机名 ---
            for h in set(HOST_RE.findall(u)):
                if h in train_hosts or any(h in t for t in train_user_norm[fam]):
                    host_bad.append((r["id"], h))
                if IP_HOST_OK.match(h):
                    continue
                if not HOST_OK.match(h.lower()):
                    ip_bad.append((r["id"], h))
            # --- C6 meta 值：身份型必须新、枚举型必须落在训练侧值域内 ---
            for k, val in meta_kv:
                nv = normalize(val)
                if not nv:
                    continue
                if k in IDENTIFYING_META:
                    if nv in meta_vals[fam][k]:
                        meta_value_conflicts.append((r["id"], k, val))
                elif k in CLOSED_VOCAB:
                    if meta_vals[fam][k] and nv not in meta_vals[fam][k]:
                        enum_value_outside.append((r["id"], k, val))
                elif meta_vals[fam][k] and shape_class(nv) not in \
                        {shape_class(x) for x in meta_vals[fam][k]}:
                    enum_value_outside.append((r["id"], k, val))
            for sz in re.findall(r"\[size: (\d+) bytes\]", u):
                if sz in macro_sizes:
                    meta_value_conflicts.append((r["id"], "macro-size", sz))
            # --- C6b URL / 链接取值必须新 ---
            for url in set(re.findall(r'(?:https?|ftp)://[^\s"<>\]]+', u)):
                if normalize(url) in train_urls:
                    meta_value_conflicts.append((r["id"], "url", url))
            # --- I schema 词汇 ---
            if fam == "T15":
                out = mk - t15_meta_vocab
                if out:
                    errors.append(f"{sid}: <meta> 键超出训练侧词表 {sorted(out)}")
                oh = dom_heads(u) - t15_dom_vocab
                if oh:
                    errors.append(f"{sid}: <dom> node head 超出训练侧词表 {sorted(oh)}")
            # --- D 跨留出集 ---
            if r["id"] in holdout_ids:
                rep["holdout_cross_overlap"]["id"].append(r["id"])
                errors.append(f"{sid}: id 与留出集重叠")
            if normalize(u) in holdout_q:
                rep["holdout_cross_overlap"]["query"].append(r["id"])
                errors.append(f"{sid}: user 文本与留出集 query 同文")

        # ---------------- 族级裁定 ----------------
        dup_train = exact_users & set(train_user_norm[fam])
        if dup_train:
            errors.append(f"{fam}: C1 失败——与训练侧 user 精确同文 {len(dup_train)} 条")
        if content_hits:
            errors.append(f"{fam}: C2 失败——内容级 8-gram 命中 {len(content_hits)} 个"
                          f"（涉及 {len(c2_rows)} 行）：{list(content_hits)[:6]}")
        if run_max_seen >= RUN_MAX:
            errors.append(f"{fam}: C3 失败——内容级连续共享游程 {run_max_seen} ≥ {RUN_MAX}"
                          f"（{run_max_seen + NGRAM_N - 1} 字符）：{run_worst}")
        if raw_run_max >= RUN_RAW_MAX:
            errors.append(f"{fam}: C3b 失败——含 schema 词元的连续共享游程 {raw_run_max} ≥ "
                          f"{RUN_RAW_MAX}（{raw_run_max + NGRAM_N - 1} 字符）：{raw_run_worst}")
        if payload_hits:
            errors.append(f"{fam}: C4 失败——载荷区 8-gram 命中 {len(payload_hits)} 个"
                          f"（涉及 {len(c4_rows)} 行）：{list(payload_hits)[:6]}")
        if host_bad:
            errors.append(f"{fam}: C5 失败——主机名出现在训练文本中 {host_bad[:4]}")
        if meta_value_conflicts:
            errors.append(f"{fam}: C6 失败——meta/URL 取值复用训练侧 "
                          f"{meta_value_conflicts[:4]}")
        if enum_value_outside:
            errors.append(f"{fam}: C6 失败——枚举型 meta 取值落在训练侧值域外 "
                          f"{enum_value_outside[:4]}")
        if ip_bad:
            errors.append(f"{fam}: 虚构性失败——host 非 RFC2606/5737 保留域 {ip_bad[:4]}")
        if len(raw) < 24:
            errors.append(f"{fam}: 条数 {len(raw)} < 24")
        if raw:
            ratio = n_neg / len(raw)
            st.update({"negatives": n_neg, "negative_ratio": round(ratio, 4)})
            if ratio < 0.25:
                errors.append(f"{fam}: 负例占比 {ratio:.3f} < 0.25")
            for lg in LANGS:
                sh = langs[lg] / len(raw)
                if sh < 0.40:
                    errors.append(f"{fam}: {lg} 占比 {sh:.3f} < 0.40")
            for pk in PACKS:
                if packs[pk] == 0:
                    errors.append(f"{fam}: 政策包缺失 {pk}")
            if len(slugs) < 8:
                errors.append(f"{fam}: id 第 4 字段种类 {len(slugs)} < 8（{sorted(slugs)}）")
        st.update({
            "packs": dict(packs), "langs": dict(langs), "kinds": dict(kinds),
            "varieties": len(slugs), "slugs": sorted(slugs),
            "tasks": dict(tasks), "verdicts": dict(verdicts), "actions": dict(actions),
            "train_disjoint": {
                "C1_exact_user_matches": len(dup_train),
                "C2_content_ngram_hits": len(content_hits),
                "C2_rows": sorted(c2_rows),
                "C2_hits": dict(content_hits.most_common(20)),
                "C3_max_contiguous_run_grams": run_max_seen,
                "C3_max_contiguous_chars": run_max_seen + NGRAM_N - 1,
                "C3_worst": run_worst,
                "C3b_raw_shared_grams": raw_hits_count,
                "C3b_raw_max_contiguous_run_grams": raw_run_max,
                "C3b_raw_max_contiguous_chars": raw_run_max + NGRAM_N - 1,
                "C3b_raw_worst": raw_run_worst,
                "C3b_raw_runs_ge12": sorted(raw_runs_long, reverse=True)[:20],
                "C4_payload_hits": len(payload_hits),
                "C4_rows": sorted(c4_rows),
                "C5_host_hits": host_bad,
                "C6_meta_value_conflicts": meta_value_conflicts,
                "C6_enum_values_outside_domain": enum_value_outside,
                "schema_lines_removed": dict(dropped_lines.most_common(40)),
                "schema_gram_tokens_excluded": len(excl_grams),
                "schema_gram_tokens": dict(excl_grams.most_common(60)),
            },
        })
        rep["families"][fam] = st

    # ---------------- 政策条件化三元组 ----------------
    trip = {}
    for fam, cfg in FAMILIES.items():
        p = PROBE_DIR / cfg["probe"]
        if not p.exists():
            continue
        groups = collections.defaultdict(list)
        for _, r in load_jsonl(p):
            if kind_of(r["id"]) in ("poln", "pola"):
                groups[(kind_of(r["id"]), slug_of(r["id"]), r["lang"])].append(r)
        for key, rs in sorted(groups.items()):
            if len(rs) != 3:
                errors.append(f"{fam}: 政策三元组 {key} 条数 {len(rs)} != 3")
                continue
            if {r["pack"] for r in rs} != set(PACKS):
                errors.append(f"{fam}: 政策三元组 {key} 未覆盖三包")
            if len({user_of(r) for r in rs}) != 1:
                errors.append(f"{fam}: 政策三元组 {key} user 文本不一致")
            if len({r["messages"][0]["content"] for r in rs}) != 3:
                errors.append(f"{fam}: 政策三元组 {key} system 未随包变化")
            trip[f"{fam}:{key[0]}:{key[1]}:{key[2]}"] = {
                "rows": len(rs), "packs": [r["pack"] for r in rs],
                "user_identical": True,
                "sys_distinct": True,
                "verdicts": [str(verdict_of(r).get("verdict")) for r in rs],
                "actions": [str(verdict_of(r).get("action")) for r in rs],
            }
    rep["policy_triplets"] = trip
    if len(trip) < 3:
        errors.append(f"政策条件化三元组仅 {len(trip)} 组（三族各需 ≥1 组）")

    rep["errors"] = errors
    rep["verdict"] = "PASS" if not errors else f"FAIL ({len(errors)})"
    return rep, errors


def main() -> int:
    rep, errors = run_checks(PROBE_DIR)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    for fam, st in rep["families"].items():
        td = st["train_disjoint"]
        print(f"[probe] {fam:4s} rows={st['rows']:3d} neg={st['negatives']:3d} "
              f"({st['negative_ratio']:.3f}) packs={st['packs']} langs={st['langs']}")
        print(f"        kinds={st['varieties']} verdicts={st['verdicts']} "
              f"actions={st['actions']}")
        print(f"        C1_exact={td['C1_exact_user_matches']} "
              f"C2_content_hits={td['C2_content_ngram_hits']} "
              f"C3_max_run={td['C3_max_contiguous_run_grams']}g/"
              f"{td['C3_max_contiguous_chars']}c (limit {RUN_MAX - 1}g/"
              f"{RUN_MAX - 1 + NGRAM_N - 1}c) "
              f"C4_payload_hits={td['C4_payload_hits']} "
              f"C5_host={len(td['C5_host_hits'])} C6_meta={len(td['C6_meta_value_conflicts'])}")
        print(f"        C3b_raw_shared={td['C3b_raw_shared_grams']} "
              f"C3b_raw_max_run={td['C3b_raw_max_contiguous_run_grams']}g/"
              f"{td['C3b_raw_max_contiguous_chars']}c (limit {RUN_RAW_MAX - 1}g/"
              f"{RUN_RAW_MAX - 1 + NGRAM_N - 1}c)")
        print(f"        schema_lines_removed={len(td['schema_lines_removed'])} "
              f"schema_gram_tokens_excluded={td['schema_gram_tokens_excluded']}")
        for g, c in list(td["C2_hits"].items())[:5]:
            print(f"          !! C2 hit {g!r} x{c}")
    print(f"[probe] holdout cross-overlap id={len(rep['holdout_cross_overlap']['id'])} "
          f"query={len(rep['holdout_cross_overlap']['query'])}")
    print(f"[probe] policy triplets={len(rep['policy_triplets'])}")
    if errors:
        print(f"[probe] FAIL ({len(errors)})")
        for e in errors[:30]:
            print("   -", e)
        print(f"-> {OUT}")
        return 1
    print("[probe] PASS：schema 逐字一致 / train-disjoint(C1–C6) / 跨留出集零重叠 / "
          "配比与语言达标 / 政策三元组可判")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
