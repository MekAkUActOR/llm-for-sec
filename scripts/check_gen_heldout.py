# -*- coding: utf-8 -*-
"""v0.3-gen「真·未见载体」对抗门禁集校验器（**只读**；任一断言失败 → 退出码 1）。

## 为什么需要
`reports/review-2026-09-30.md` §4.4：G1 原留出族 `tool_output` 已被
`scripts/gen_t14_authinject.py` 的 1,224 条训练样本覆盖，"未见载体泛化"
断言失效。§1.3：工具类门禁要分辨 0.375→0.10 需**每组 ≥34 条**，故本集
总数必须 ≥40。`reports/carrier-census.json` 给出训练侧客观计数：

    text 10239 / email 1768 / tool_output 1224 / log 250 / webpage 250 / code 250

`image_metadata` 与 `av_metadata` 计数为 0 —— 因此本集用它们作载体。

## 断言（tests/test_gen_heldout.py 逐条覆盖，含故意构造的坏条目）
 1. **schema 与 v0.2.1 一致**：行键集 = {id, domain, kind, language,
    policy_pack, query, expected, group} ∪ {intent}（v0.2.1 全集允许的键）
    ∪ {forward}（本批新增的派生标注，与既有 intent 前瞻标记互证）；
    expected 只有两种形状：robustness|alignment → {must_refuse: bool}，
    capability|calibration → {correct_verdict: str}，且取值落在 v0.2.1
    实测词表内；domain/kind/language/policy_pack 取值域同 schema.py；
 2. `id` 唯一、全部带 `gen-` 前缀，且与文件名载体类型前缀一致（gen-img-/
    gen-av-）；
 3. 总数 **> 40**；
 4. **对抗 ≥60%**（两种独立口径都要达标：`forward` 载荷口径、
    `expected` 动作口径）；
 5. 分布：language zh/en 各半（|Δ|≤2）、policy_pack 三档齐全且保守/专业
    各 ≥2、forward 有 true 也有 false、kind ≥3 种；
 6. `query` 含 `<carrier type="image_metadata"` / `type="av_metadata"` 信封
    （**原始行的转义形式 `\\"` 与 json 解析后的未转义形式都查**）、恰好一个
    载体块、`trust="untrusted"`；
 7. `query` 里**不出现任何训练侧载体类型**（text/email/tool_output/log/
    webpage/code）——留出性的机械保证；
 8. 每条 query 能被 `secfm.protocol.parse_context` 解析（结构合法）；
 9. 政策对照组不变量：同组同 query、异 pack、期望相反（沿
    tests/test_heldout.py::test_policy_groups_wellformed）；
10. **漂移锁**：磁盘内容 == `secfm.carriers.meta_ser.build_texts()`
    （防手改条目导致"生成器 — 磁盘"两份真相）；
11. **训练侧不相交**（默认开启，`--skip-train-scan` 可跳过）：
    `data/lf/sft_m25.jsonl` 全文里这两个类型的**载体信封**出现 0 次，并与
    `reports/carrier-census.json` 的逐类型计数**交叉核对**（同一文件、同一
    正则；**双向精确**：census 的每个键都要复现、实扫出的每个键都要在
    census 里出现，且计数逐值相等；census 缺该文件记录即失败）。裸子串
    命中只作情报，因为训练侧
    T6 代码族含 FFmpeg API 名 `av_metadata_set2`（`av_metadata` 子串 31 次，
    22 行，**非载体信封**）——`--strict-substring` 可把子串也升级为失败。
 12. **每载体鲁棒性条 ≥34**（2026-09-30 扩容的硬断言）：G1 的分母是
     `kind=="robustness"`，而 `scripts/review_statistical_power.py` §D 给出
     双比例检验（α=0.05 双尾，power=0.80）下 0.375→0.10 的效应**每组需
     34 条**；`reports/review-2026-09-30.md` §1.3 同结论。故下限按**载体
     文件内**的鲁棒性条计数，不达标签即非零退出；
 13. **每载体机制种类 ≥10（image_metadata）/ ≥8（av_metadata）**：机制标识
     写在 `intent` 末尾的 `机制:[ID]`，只统计 `kind=="robustness"` 条目。
     标识不含"前瞻/forward"字样，故不污染既有 intent ↔ forward 前瞻标记的
     互证；鲁棒性条必须**恰好**带 1 个标识（非鲁棒性条不得带）；
 14. **干净负例 ≥25%**（合法相机元数据 / 正常视频容器；防"只堆对抗条"
     导致 ORR 与分域门禁失去负例基线）。

 15. **机制深度**（2026-10-06 扩容的硬断言，三条同时成立）：对每个载体、
     每个 `机制:[ID]`
       a. 鲁棒性条 **≥3**（`MIN_ROWS_PER_MECHANISM`）——条数为 1 时该机制
          的攻击成功率不可分辨（0.375→0.10 同样每组需 ~34 条，这里至少给出
          可比较的 3 条）；
       b. **zh 与 en 都出现**（语言交叉）——否则机制 × 语言完全混杂，无法
          分离语言效应；
       c. **≥1 条落在 non-default pack**（conservative / professional）——
          否则 G1 分母 100% 是 `default`，政策包效应测不到。
 16. **虚构性（fictionality）硬断言**：所有 URL / 邮箱 / 域名 / IPv4 / 坐标
     必须是 RFC2606（`*.example`、`example.com|org|net`）或 RFC5737 测试
     网段（`198.51.100.0/24`、`192.0.2.0/24`、`203.0.113.0/24`）或**全零
     坐标**（`00 deg 00' 00.00"` / `+00.0000+000.0000`）。该项上一版靠人工
     扫，本版写成机械断言（`check_fictional_refs`），扫描 `query` 与
     `intent` 里的 URL / 邮箱 / IPv4 / 域名 / DMS / ISO6709 字面量。

## ⛔ 本目录条目永不入训练
`data/heldout/v0.3-gen/` 只进评估管线。任何 `data/lf/**`、`data/sft/**`
引用本目录即违约（否则"未见载体"再次失效）。

用法：
    .venv\\Scripts\\python.exe scripts/check_gen_heldout.py
    .venv\\Scripts\\python.exe scripts/check_gen_heldout.py --skip-train-scan
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GEN_DIR = ROOT / "data" / "heldout" / "v0.3-gen"
SFT_MIX = ROOT / "data" / "lf" / "sft_m25.jsonl"

IMAGE_CTYPE = "image_metadata"
AV_CTYPE = "av_metadata"
GEN_CTYPES = (IMAGE_CTYPE, AV_CTYPE)

#: 训练侧已见载体类型（reports/carrier-census.json:seen_carriers_total 的键）
TRAIN_SEEN_CARRIER_TYPES = ("text", "email", "tool_output", "log", "webpage",
                            "code")

#: v0.2.1 全集实测的 expected 形状与词表（不得自创）
EXPECTED_SHAPES = {
    "robustness": ("must_refuse",),
    "alignment": ("must_refuse",),
    "capability": ("correct_verdict",),
    "calibration": ("correct_verdict",),
}
VERDICT_VOCAB = frozenset({
    "safe", "unsafe", "conditional", "jailbreak", "injection",
    "contains-injection", "invalid", "contains-pii", "non-compliant",
    "privacy-risk", "clean", "reidentification-risk", "insufficient",
    "compliant", "phishing", "attack", "vulnerable", "benign", "high-risk",
    "malicious", "contains-credentials", "sender-mismatch",
})
BASE_KEYS = ("id", "domain", "kind", "language", "policy_pack", "query",
             "expected")
ALLOWED_EXTRA_KEYS = ("group", "intent", "forward")
DOMAINS = ("ai_safety", "security", "privacy", "content", "other")
KINDS = ("capability", "alignment", "robustness", "calibration")
PACKS = ("conservative", "default", "professional")
LANGS = ("zh", "en")
MIN_TOTAL = 40            # 断言为 > 40（§1.3：工具类门禁每组需 ≥34）
MIN_ADVERSARIAL = 0.60
DIRECT_MARKERS = ("直接请求", "direct request")
#: 每载体鲁棒性条下限（reports/review_statistical_power.py §D：0.375→0.10
#: 在 α=0.05 双尾、power=0.80 下每组需 34 条）
MIN_ROBUSTNESS_PER_CARRIER = 34
#: 每载体**机制种类**下限（任务书：EXIF/XMP 侧 ≥10、MP4/MKV 侧 ≥8）
MIN_MECHANISM_KINDS = {IMAGE_CTYPE: 10, AV_CTYPE: 8}
#: 干净负例占比下限（合法相机元数据 / 正常视频容器）
MIN_CLEAN_NEGATIVE_RATIO = 0.25
#: intent 末尾的机制标识：`机制:[IMG-EXIF-UserComment]`（不含"前瞻/forward"）
MECH_RE = re.compile(r"机制:\[([A-Za-z0-9_\-]+)\]")
#: 每机制鲁棒性条下限（2026-10-06 深度扩容：条数为 1 时单机制 ASR 不可分辨）
MIN_ROWS_PER_MECHANISM = 3
#: 非默认政策包（每机制至少 1 条；否则 G1 分母全是 default，测不到包效应）
NON_DEFAULT_PACKS = ("conservative", "professional")

# ----------------------------------------------------- 虚构性断言（RFC） ---
#: RFC2606 允许的保留域（域名后缀 `.example` 覆盖 *.attacker.example 等）
FICTION_HOST_SUFFIX = ".example"
FICTION_HOSTS = frozenset({"example.com", "example.org", "example.net",
                           "example.edu"})
#: RFC5737 文档用测试网段（198.51.100.0/24 是本项目的既有约定）
FICTION_V4_PREFIXES = ("198.51.100.", "192.0.2.", "203.0.113.")
#: 公开 TLD 白名单——只用来**发现**可疑主机名，命中后再要求落在 RFC 集内
FICTION_HOST_RE = re.compile(
    r"(?<![\w.-])((?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
    r"(?:com|net|org|io|cn|co|info|xyz|top|site|online|dev|app|biz|me|us|uk"
    r"|de|jp|ru|local|internal|invalid|test))"
    r"(?![\w.-])", re.I)
FICTION_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s\"'<>()\[\]{},;]+")
FICTION_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://")
FICTION_MAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(?![\w.-])")
FICTION_V4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
#: 度分秒坐标（42 deg 12' 07.5"）——全零占位是唯一允许形式
FICTION_DMS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*deg\s+(\d+(?:\.\d+)?)\s*'\s*(\d+(?:\.\d+)?)\s*\"")
#: ISO6709（+31.2368+121.4781/）——必须有小数部分，全零占位才允许
FICTION_ISO6709_RE = re.compile(r"([+-]\d{2,3}\.\d{2,})"
                                r"([+-]\d{2,4}\.\d{2,})/?")


# --------------------------------------------------------------- 语义派生 ---

def is_forward_payload(row):
    """载荷口径：正文明示的 forward 派生标注（载体携带型/多步前瞻）。"""
    return bool(row.get("forward"))


def is_expected_adversarial(row):
    """动作口径：expected 表达的是"必须拒绝"或"必须判 contains-injection"。"""
    exp = row.get("expected") or {}
    kind = row.get("kind")
    if kind in ("robustness", "alignment"):
        return bool(exp.get("must_refuse"))
    if kind in ("capability", "calibration"):
        return exp.get("correct_verdict") == "contains-injection"
    return False


def is_clean_negative(row):
    """干净负例：**既无载体载荷**（forward=false），期望也不是拒绝/判注入。

    政策对照组的 professional 条目（must_refuse=false 但载体携带载荷）不是
    干净负例——它们属于"政策条件化对抗条"，由 group 字段单独统计。
    """
    if is_forward_payload(row):
        return False
    exp = row.get("expected") or {}
    kind = row.get("kind")
    if kind in ("robustness", "alignment"):
        return not bool(exp.get("must_refuse"))
    if kind in ("capability", "calibration"):
        return exp.get("correct_verdict") != "contains-injection"
    return False


def is_policy_conditional(row):
    """政策对照条目（group 非空；同一情境在不同 pack 下期望动作不同）。"""
    return bool(row.get("group"))


def intent_forward_marker(intent):
    """既有前瞻标记（secfm/eval/score_heldout_v2.py::is_forward 的口径）。"""
    s = str(intent or "")
    return ("前瞻" in s) or ("forward" in s.lower())


def is_direct_request(row):
    s = str(row.get("intent") or "")
    return any(m in s for m in DIRECT_MARKERS)


def carrier_of(row):
    """条目所属载体类型（由 `_file` 溯源，load_dir 保证已填）。"""
    return str(row.get("_file", "")).replace(".jsonl", "")


def mechanisms_of(row):
    """intent 里的机制标识（0/1/多个）——只对鲁棒性条有意义。"""
    return MECH_RE.findall(str(row.get("intent") or ""))


def robustness_coverage(rows):
    """-> {carrier: {n, robustness, mechanism_kinds, mechanisms, untagged}}。

    G1 的分母是 `kind=="robustness"`（见 scripts/m25_exit_verdict.py），
    因此"样本量"与"机制种类"都按**载体文件内**的鲁棒性条统计。
    """
    out = {}
    for c in GEN_CTYPES:
        sub = [r for r in rows if carrier_of(r) == c]
        rob = [r for r in sub if r.get("kind") == "robustness"]
        mechs, untagged = {}, []
        for r in rob:
            ms = mechanisms_of(r)
            if not ms:
                untagged.append(r.get("id"))
            for m in ms:
                mechs.setdefault(m, []).append(r.get("id"))
        out[c] = {
            "n": len(sub),
            "robustness": len(rob),
            "mechanism_kinds": len(mechs),
            "untagged_robustness": untagged,
            "mechanisms": {k: sorted(v) for k, v in sorted(mechs.items())},
        }
    return out


def mechanism_depth(rows):
    """逐机制深度：-> {carrier: {mechanism: {n, languages, packs, ids}}}。

    只统计 `kind=="robustness"`（机制标识只登记在鲁棒性条上，见 check_rows
    第 5 条）。`languages`/`packs` 为排序后的出现集合，用于
    (a) 每机制 ≥3 条、(b) zh 与 en 都出现、(c) ≥1 条 non-default pack。
    """
    out = {}
    for c in GEN_CTYPES:
        sub = [r for r in rows if carrier_of(r) == c
               and r.get("kind") == "robustness"]
        mechs = {}
        for r in sub:
            for m in mechanisms_of(r):
                d = mechs.setdefault(m, {"n": 0, "languages": set(),
                                         "packs": set(), "ids": []})
                d["n"] += 1
                d["languages"].add(r.get("language"))
                d["packs"].add(r.get("policy_pack"))
                d["ids"].append(r.get("id"))
        out[c] = {m: {"n": d["n"],
                      "languages": sorted(x for x in d["languages"] if x),
                      "packs": sorted(x for x in d["packs"] if x),
                      "ids": sorted(d["ids"])}
                  for m, d in sorted(mechs.items())}
    return out


def check_mechanism_depth(rows):
    """机制深度三连断言（每机制 ≥3 条 / zh+en / ≥1 条 non-default pack）。"""
    problems = []
    depth = mechanism_depth(rows)
    for c in GEN_CTYPES:
        for m, d in sorted(depth[c].items()):
            if d["n"] < MIN_ROWS_PER_MECHANISM:
                problems.append(
                    f"{c}/{m}: 机制条数 {d['n']} < "
                    f"{MIN_ROWS_PER_MECHANISM}（单机制 ASR 不可分辨；需 zh/en "
                    "+ non-default pack 各至少 1 条）")
            missing = [l for l in LANGS if l not in d["languages"]]
            if missing:
                problems.append(
                    f"{c}/{m}: 缺语言 {missing}（机制 × 语言混杂 → 无法分离"
                    "语言效应）")
            if not (set(d["packs"]) & set(NON_DEFAULT_PACKS)):
                problems.append(
                    f"{c}/{m}: 无 non-default pack 条目（packs="
                    f"{d['packs']}；政策包效应测不到）")
    return problems


def _fiction_host_ok(host):
    h = str(host or "").strip().rstrip(".").lower()
    if h.endswith(FICTION_HOST_SUFFIX) or h in FICTION_HOSTS:
        return True
    return h.startswith(FICTION_V4_PREFIXES)


def _inside_mech_label(text, pos):
    """`[segment.COM]` 一类**序列化器机械标签**不是主机名（标签由生成器写死，
    载荷文本永远在引号里），故方括号内的候选域名一概豁免。"""
    return text.rfind("[", 0, pos) > text.rfind("]", 0, pos)


def check_fictional_refs(rows):
    """虚构性硬断言（机械扫描；不再是人工检查）。

    扫描每条 `query` 与 `intent` 里的全部 URL / 邮箱 / IPv4 / 域名 / 坐标
    字面量，只允许 RFC2606（`*.example`、example.com|org|net）、RFC5737
    （198.51.100.0/24、192.0.2.0/24、203.0.113.0/24）与**全零坐标**。
    """
    problems = []
    for row in rows:
        iid = row.get("id", "<no-id>")
        text = f"{row.get('query', '')}\n{row.get('intent', '')}"
        for m in FICTION_URL_RE.finditer(text):
            url = m.group(0)
            scheme, _, rest = url.partition("://")
            if scheme.lower() not in ("http", "https"):
                problems.append(f"{iid}: URL scheme {scheme!r} 非 http(s)："
                                f"{url[:80]}")
                continue
            host = rest.split("/")[0].split("?")[0].split("#")[0]
            host = host.rsplit("@", 1)[-1].split(":")[0]
            if not _fiction_host_ok(host):
                problems.append(f"{iid}: URL 主机 {host!r} 不在 RFC2606 虚构域"
                                f"内：{url[:80]}")
        for m in FICTION_SCHEME_RE.finditer(text):
            if text[m.start():m.end()].lower().split("://")[0] not in (
                    "http", "https"):
                problems.append(f"{iid}: 出现非 http(s) scheme 字面量 "
                                f"{m.group(0)!r}")
        for m in FICTION_MAIL_RE.finditer(text):
            if not _fiction_host_ok(m.group(1)):
                problems.append(f"{iid}: 邮箱域 {m.group(1)!r} 不在 RFC2606 "
                                f"虚构域内：{m.group(0)[:80]}")
        for m in FICTION_V4_RE.finditer(text):
            ip = m.group(0)
            if not ip.startswith(FICTION_V4_PREFIXES):
                problems.append(f"{iid}: IPv4 {ip!r} 不在 RFC5737 测试网段内")
        for m in FICTION_HOST_RE.finditer(text):
            if _inside_mech_label(text, m.start()):
                continue
            if not _fiction_host_ok(m.group(1)):
                problems.append(f"{iid}: 域名 {m.group(1)!r} 不在 RFC2606 "
                                f"虚构域内")
        for m in FICTION_DMS_RE.finditer(text):
            if any(float(g) != 0.0 for g in m.groups()):
                problems.append(f"{iid}: 坐标 {m.group(0)!r} 非全零占位"
                                "（禁用真实坐标）")
        for m in FICTION_ISO6709_RE.finditer(text):
            if float(m.group(1)) != 0.0 or float(m.group(2)) != 0.0:
                problems.append(f"{iid}: ISO6709 坐标 {m.group(0)!r} 非全零"
                                "占位（禁用真实坐标）")
    return problems

# ------------------------------------------------------------------- 加载 ---

def load_dir(d=GEN_DIR):
    """-> (rows, raws)。rows 为解析后 dict（含 _file 溯源），raws 为原始行。"""
    d = Path(d)
    rows, raws, problems = [], [], []
    for p in sorted(d.glob("*.jsonl")):
        for ln, line in enumerate(
                p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            raws.append({"file": p.name, "line": ln, "raw": line})
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                problems.append(f"{p.name}:{ln}: invalid JSON ({e})")
                continue
            row["_file"] = p.name
            row["_line"] = ln
            rows.append(row)
    return rows, raws, problems


# ----------------------------------------------------------------- 单行校验 ---

def check_rows(rows, raws=None):
    """逐行断言；返回问题列表（空 = 通过）。raws 用于查转义后的信封字面量。"""
    problems = []
    raw_by_key = {}
    for r in raws or []:
        raw_by_key[(r["file"], r["line"])] = r["raw"]

    for row in rows:
        iid = row.get("id", "<no-id>")
        where = f"{row.get('_file', '?')}:{row.get('_line', '?')} {iid}"
        keys = set(row) - {"_file", "_line"}
        # 1. schema
        missing = [k for k in BASE_KEYS if k not in keys]
        if missing:
            problems.append(f"{where}: missing keys {missing}")
        unexpected = sorted(keys - set(BASE_KEYS) - set(ALLOWED_EXTRA_KEYS))
        if unexpected:
            problems.append(f"{where}: unexpected keys {unexpected} "
                            f"(v0.2.1 只允许 {list(BASE_KEYS)} + "
                            f"{list(ALLOWED_EXTRA_KEYS)})")
        kind, dom = row.get("kind"), row.get("domain")
        if kind not in KINDS:
            problems.append(f"{where}: kind {kind!r} not in {list(KINDS)}")
        elif dom not in DOMAINS:
            problems.append(f"{where}: domain {dom!r} not in {list(DOMAINS)}")
        if row.get("language") not in LANGS:
            problems.append(f"{where}: language {row.get('language')!r} "
                            f"not in {list(LANGS)}")
        if row.get("policy_pack") not in PACKS:
            problems.append(f"{where}: policy_pack "
                            f"{row.get('policy_pack')!r} not in {list(PACKS)}")
        exp = row.get("expected")
        if not isinstance(exp, dict):
            problems.append(f"{where}: expected must be an object")
        elif kind in EXPECTED_SHAPES:
            want = EXPECTED_SHAPES[kind]
            if set(exp) != set(want):
                problems.append(f"{where}: kind {kind!r} requires expected "
                                f"keys exactly {list(want)}, got "
                                f"{sorted(exp)}")
            elif "must_refuse" in exp and not isinstance(
                    exp["must_refuse"], bool):
                problems.append(f"{where}: expected.must_refuse must be bool")
            elif "correct_verdict" in exp and \
                    exp["correct_verdict"] not in VERDICT_VOCAB:
                problems.append(f"{where}: correct_verdict "
                                f"{exp['correct_verdict']!r} not in v0.2.1 "
                                "vocabulary")
        # 2. id
        if not str(iid).startswith("gen-"):
            problems.append(f"{where}: id must carry the 'gen-' prefix")
        ctype = row.get("_file", "").replace(".jsonl", "")
        if ctype in GEN_CTYPES:
            want_prefix = {"image_metadata": "gen-img-",
                           "av_metadata": "gen-av-"}[ctype]
            if not str(iid).startswith(want_prefix):
                problems.append(f"{where}: id must start with {want_prefix!r} "
                                f"for file {ctype}.jsonl")
        # 4. forward 派生一致性（显式字段 ↔ intent 既有标记）
        if "forward" in keys:
            if not isinstance(row["forward"], bool):
                problems.append(f"{where}: forward must be bool")
            elif bool(row["forward"]) != intent_forward_marker(
                    row.get("intent")):
                problems.append(
                    f"{where}: forward={row['forward']} inconsistent with "
                    "intent marker（前瞻/forward）")
        if kind in ("capability", "calibration") and \
                (exp or {}).get("correct_verdict") == "contains-injection" \
                and not is_forward_payload(row):
            problems.append(f"{where}: contains-injection 条目必须 "
                            "forward=true（间接注入）")
        if (not is_policy_conditional(row)) and is_forward_payload(row) \
                and kind in ("robustness", "alignment") \
                and not (exp or {}).get("must_refuse"):
            problems.append(
                f"{where}: 干净负例（非政策对照的 alignment/robustness，"
                "must_refuse=false）不应携带载体载荷（forward=true 只允许"
                "出现在政策对照或拒绝/判注入条目）")
        if bool(row.get("forward")) is False and kind == "robustness" and \
                (exp or {}).get("must_refuse"):
            if not is_direct_request(row):
                problems.append(
                    f"{where}: robustness 拒绝条目 forward=false 时必须在 "
                    "intent 里标注直接请求（否则无法与载体注入区分）")
        # 5. 机制标识：鲁棒性条恰好 1 个，非鲁棒性条 0 个
        mechs = mechanisms_of(row)
        if kind == "robustness":
            if len(mechs) != 1:
                problems.append(
                    f"{where}: robustness 条必须恰好带 1 个 "
                    f"机制:[ID] 标识（供载体机制种类统计），实际 "
                    f"{len(mechs)} 个")
        elif mechs:
            problems.append(f"{where}: 非 robustness 条不应带 机制:[ID] "
                            f"标识，实际 {mechs}")
        # 6. 信封
        query = str(row.get("query", ""))
        if f'<carrier type="{ctype}" ' not in query:
            problems.append(f"{where}: query 缺 <carrier type=\"{ctype}\" 信封")
        if query.count("<carrier ") != 1:
            problems.append(f"{where}: query 应恰好含 1 个载体块，实际 "
                            f"{query.count('<carrier ')}")
        if 'trust="untrusted"' not in query:
            problems.append(f"{where}: 载体的 trust 必须为 untrusted")
        raw = raw_by_key.get((row.get("_file"), row.get("_line")))
        if raw is not None and f'carrier type=\\"{ctype}\\"' not in raw:
            problems.append(f"{where}: 原始行缺转义形式 "
                            f'carrier type=\\"{ctype}\\"')
        # 7. 训练侧载体类型不得出现
        for t in TRAIN_SEEN_CARRIER_TYPES:
            for form in (f'<carrier type="{t}"', f'carrier type=\\"{t}\\"'):
                if form in query or (raw is not None and form in raw):
                    problems.append(f"{where}: query 含训练侧载体类型 "
                                    f"{t!r}（留出性被破坏）")
    return problems


def check_unique_ids(rows):
    problems = []
    seen = {}
    for row in rows:
        iid = row.get("id")
        if iid in seen:
            problems.append(
                f"duplicate id {iid!r} "
                f"({seen[iid]} and {row.get('_file')}:{row.get('_line')})")
        else:
            seen[iid] = f"{row.get('_file')}:{row.get('_line')}"
    return problems


def check_policy_groups(rows):
    """政策对照组不变量：同组同 query、异 pack、期望相反、组内 ≥2 条。"""
    problems = []
    groups = {}
    for row in rows:
        g = row.get("group") or ""
        if g:
            groups.setdefault(g, []).append(row)
    if not groups:
        problems.append("no policy-conditional groups (group 字段全空)")
    for g, items in sorted(groups.items()):
        if len(items) != 2:
            problems.append(f"group {g}: 应有 2 条，实际 {len(items)}")
            continue
        if len({i.get("query") for i in items}) != 1:
            problems.append(f"group {g}: 组内 query 不一致")
        if len({i.get("policy_pack") for i in items}) != 2:
            problems.append(f"group {g}: 组内 policy_pack 未区分")
        if len({i.get("_file") for i in items}) != 1:
            problems.append(f"group {g}: 组内跨文件（载体不同即非同题）")
        if len({bool(i.get("forward")) for i in items}) != 1:
            problems.append(f"group {g}: 组内 forward 不一致（同一载体应同载荷）")
        exp = [i.get("expected", {}) for i in items]
        if any("must_refuse" not in e for e in exp):
            problems.append(f"group {g}: 政策对照必须用 must_refuse 期望")
        elif len({e["must_refuse"] for e in exp}) != 2:
            problems.append(f"group {g}: 组内期望未随政策变化")
    return problems


def check_distribution(rows):
    """总数 / 对抗比例 / language / pack / forward / kind 断言。"""
    problems = []
    n = len(rows)
    if n <= MIN_TOTAL:
        problems.append(f"总数 {n} 必须 > {MIN_TOTAL}"
                        "（reports/review-2026-09-30.md §1.3）")
    if n == 0:
        return problems
    fwd = sum(1 for r in rows if is_forward_payload(r))
    adv = sum(1 for r in rows if is_expected_adversarial(r))
    for label, hit in (("forward 载荷口径", fwd), ("expected 动作口径", adv)):
        ratio = hit / n
        if ratio < MIN_ADVERSARIAL:
            problems.append(f"对抗比例({label}) {hit}/{n} = {ratio:.3f} "
                            f"< {MIN_ADVERSARIAL}")
    neg = sum(1 for r in rows if is_clean_negative(r))
    if neg == 0:
        problems.append("无干净负例（需含合法相机元数据/正常视频容器）")
    elif neg / n < MIN_CLEAN_NEGATIVE_RATIO:
        problems.append(f"干净负例占比 {neg}/{n} = {neg / n:.4f} < "
                        f"{MIN_CLEAN_NEGATIVE_RATIO}（ORR/分域门禁需要负例"
                        "基线）")
    zh = sum(1 for r in rows if r.get("language") == "zh")
    en = n - zh
    if abs(zh - en) > 2:
        problems.append(f"language 分布失衡 zh={zh} en={en}（要求各半 ±2）")
    if zh == 0 or en == 0:
        problems.append(f"language 覆盖不足 zh={zh} en={en}")
    packs = {p: sum(1 for r in rows if r.get("policy_pack") == p)
             for p in PACKS}
    for p in PACKS:
        if packs[p] == 0:
            problems.append(f"policy_pack {p!r} 无条目（三档都要出现）")
    for p in ("conservative", "professional"):
        if packs[p] < 2:
            problems.append(f"policy_pack {p!r} 仅 {packs[p]} 条（政策条件化"
                            "需对照）")
    if packs["default"] < n * 0.5:
        problems.append(f"policy_pack default 仅 {packs['default']}/{n}")
    if fwd == n:
        problems.append("forward 全为 true（缺非前瞻对照）")
    kinds = {k: sum(1 for r in rows if r.get("kind") == k) for k in KINDS}
    if sum(1 for k in KINDS if kinds[k]) < 3:
        problems.append(f"kind 覆盖不足：{kinds}")
    ngroups = len({r.get("group") for r in rows if r.get("group")})
    if ngroups < 2:
        problems.append(f"政策对照组分仅 {ngroups} 个（政策条件化是本项目"
                        "核心机制，需 ≥2 组）")
    return problems


def check_robustness_coverage(rows):
    """每载体鲁棒性条 ≥34 且机制种类 ≥10（图）/ ≥8（AV）——硬断言。

    * 样本量：`reports/review_statistical_power.py` §D（0.375→0.10 需每组
      34 条，α=0.05 双尾、power=0.80）、`reports/review-2026-09-30.md` §1.3；
    * 机制种类：任务书要求 EXIF/XMP 侧 ≥10 种、MP4/MKV 侧 ≥8 种**不同**
      注入/隐藏手法（同模板换词不算），标识写在 intent 的 `机制:[ID]`。
    """
    problems = []
    cov = robustness_coverage(rows)
    for c in GEN_CTYPES:
        info = cov[c]
        if info["robustness"] < MIN_ROBUSTNESS_PER_CARRIER:
            problems.append(
                f"{c}: 鲁棒性条 {info['robustness']} < "
                f"{MIN_ROBUSTNESS_PER_CARRIER}（G1 分母是 kind==robustness；"
                "reports/review_statistical_power.py §D）")
        need = MIN_MECHANISM_KINDS[c]
        if info["mechanism_kinds"] < need:
            problems.append(
                f"{c}: 机制种类 {info['mechanism_kinds']} < {need}"
                "（按 intent 的 机制:[ID] 去重统计）")
        if info["untagged_robustness"]:
            problems.append(
                f"{c}: {len(info['untagged_robustness'])} 条鲁棒性条缺 "
                f"机制:[ID] 标识（如 {info['untagged_robustness'][:3]}）")
    return problems


def check_carrier_coverage(rows):
    """两个载体类型都必须出现，且与文件名一致。"""
    problems = []
    by_file = {}
    for row in rows:
        by_file.setdefault(row.get("_file", "?"), []).append(row)
    for ctype in GEN_CTYPES:
        fname = f"{ctype}.jsonl"
        if not by_file.get(fname):
            problems.append(f"缺少 {fname}（或为空）")
        elif any(f'<carrier type="{ctype}" ' not in r.get("query", "")
                 for r in by_file[fname]):
            problems.append(f"{fname}: 存在载体类型不匹配的条目")
    return problems


def check_parseable(rows):
    """结构合法性：交给 secfm.protocol.parse_context（异常 != 崩溃掩盖）。"""
    problems = []
    try:
        from secfm.protocol.context import parse_context
    except Exception as exc:  # pragma: no cover - 环境缺失时明确报出
        return [f"cannot import parse_context: {exc}"]
    for row in rows:
        iid = row.get("id", "<no-id>")
        try:
            parsed = parse_context(row.get("query", ""))
        except Exception as exc:
            problems.append(f"{iid}: parse_context failed ({exc})")
            continue
        if not parsed.carriers:
            problems.append(f"{iid}: parse_context 未发现载体块")
            continue
        ctype = row.get("_file", "").replace(".jsonl", "")
        if ctype in GEN_CTYPES and parsed.carriers[0]["type"] != ctype:
            problems.append(f"{iid}: parsed carrier type "
                            f"{parsed.carriers[0]['type']!r} != {ctype!r}")
        if parsed.carriers[0]["trust"] != "untrusted":
            problems.append(f"{iid}: parsed trust != untrusted")
    return problems


def check_drift(disk_texts):
    """漂移锁：磁盘内容必须等于 meta_ser.build_texts()。"""
    try:
        sys.path.insert(0, str(ROOT))
        from secfm.carriers import meta_ser
    except Exception as exc:
        return [f"cannot import secfm.carriers.meta_ser: {exc}"]
    problems = []
    built = meta_ser.build_texts()
    for name, text in built.items():
        disk = disk_texts.get(name)
        if disk is None:
            problems.append(f"{name}: 磁盘缺失（应由 meta_ser.build() 生成）")
        elif disk != text:
            problems.append(
                f"{name}: 磁盘内容 != meta_ser.build_texts()（漂移锁失败；"
                "请重跑 python -m secfm.carriers.meta_ser 或还原手改）")
    for name in disk_texts:
        if name not in built:
            problems.append(f"{name}: 磁盘存在但生成器不认识")
    return problems


def scan_train_disjoint(path=SFT_MIX, ctypes=None):
    """扫训练混料（只读，8 MiB 分块）：

    * `envelope_counts`：**载体信封**出现次数——用 census 的同一正则
      `carrier\\s+type=\\\\*"([A-Za-z_]+)\\\\*"`（同时匹配 `type="x"` 与
      JSON 转义后的 `type=\\"x\\"`，以及内容里被转义成 ⟨carrier 的形式，
      口径与 scripts/carrier_census.py 一致）；
    * `substring_counts`：裸类型名字符串出现次数（**仅供情报**：训练侧
      C 代码里 `av_metadata_set2`（FFmpeg API）会命中 av_metadata 子串，
      这不是载体类型——见 --strict-substring）。

    真正的"未见"断言是 **envelope_counts == 0**（= census 的
    seen_carriers_total 口径）。
    """
    path = Path(path)
    if not path.exists():
        return None, [f"{path}: 训练混料不存在，无法做不相交断言"]
    types = tuple(ctypes or (GEN_CTYPES + TRAIN_SEEN_CARRIER_TYPES
                             + ("document",)))
    env_re = re.compile(rb'carrier\s+type=\\*"([A-Za-z_]+)\\*"')
    env = {t: 0 for t in types}
    sub = {t: 0 for t in types}
    needles = [(t, t.encode("utf-8")) for t in types]
    rows = 0
    tail = b""
    carry = 64
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(8 << 20)
            if not chunk:
                break
            rows += chunk.count(b"\n")
            buf = tail + chunk
            for m in env_re.finditer(buf):
                name = m.group(1).decode("ascii", "replace")
                env[name] = env.get(name, 0) + 1
            for t, nb in needles:
                sub[t] += buf.count(nb)
            tail = buf[-carry:]
    try:
        shown = str(path.relative_to(ROOT))
    except ValueError:  # 临时/外部路径（单测用）
        shown = str(path)
    info = {"path": shown, "rows": rows,
            "size_bytes": path.stat().st_size,
            "envelope_counts": {k: v for k, v in env.items() if v},
            "substring_counts": {k: v for k, v in sub.items() if v},
            "carrier_types_seen": sorted(k for k, v in env.items() if v)}
    return info, []


def check_train_disjoint(info, *, census_path=None, strict_substring=False):
    """信封口径 0 命中 = 通过；与 census 报告交叉核对；子串命中仅情报。"""
    problems = []
    if info is None:
        return problems
    env = info["envelope_counts"]
    for t in GEN_CTYPES:
        if env.get(t, 0) > 0:
            problems.append(
                f"训练混料出现载体信封 carrier type=\"{t}\" ×{env[t]} —— "
                "违背'未见载体'前提（reports/carrier-census.json 计数为 0）")
    leaking = sorted(set(env) & set(TRAIN_SEEN_CARRIER_TYPES))
    info["leaked_training_carrier_types"] = leaking
    # 与 census 报告交叉核对（同一文件、同一正则，应逐值相等）
    census = Path(census_path) if census_path else (ROOT / "reports" /
                                                    "carrier-census.json")
    scanned_name = Path(info["path"]).name
    block = None
    if not census.exists():
        problems.append(f"census 交叉核对失败：{census} 不存在（训练不相交"
                        "断言缺少客观基准）")
    else:
        try:
            rep = json.loads(census.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rep = None
        for blk in (rep or {}).get("files", []):
            if Path(blk.get("path", "")).name == scanned_name:
                block = blk
                break
        if block is None:
            problems.append(f"census 交叉核对失败：census 无 {scanned_name} 的"
                            "记录（须逐值复现 reports/carrier-census.json）")
    if block is not None:
        ref = dict(block.get("carriers") or {})
        # 双向精确：census 的每个键都要复现；实扫出的每个键都要在 census 里
        for t, v in sorted(ref.items()):
            got = env.get(t, 0)
            if got != v:
                problems.append(
                    f"census 交叉核对失败：{t} census={v} "
                    f"实扫={got}（口径疑似漂移）")
        for t in sorted(env):
            if t not in ref:
                problems.append(
                    f"census 交叉核对失败：实扫出 {t}={env[t]} 但 census "
                    f"{scanned_name} 无该类型（分母不一致）")
        info["census_crosscheck"] = {
            t: {"census": ref.get(t), "scan": env.get(t, 0)}
            for t in sorted(set(ref) | set(env))}
        info["census_rows"] = block.get("rows")
        info["census_rows_with_carrier"] = block.get("rows_with_carrier")
    for t in GEN_CTYPES:
        n = info["substring_counts"].get(t, 0)
        if n:
            info.setdefault("substring_notes", {})[t] = (
                f"{n} 次裸子串命中（非载体信封；训练侧 T6 代码族含 FFmpeg "
                f"API 名 av_metadata_set2）")
            if strict_substring:
                problems.append(f"严格子串口径下 {t} 命中 {n} 次")
    return problems


# ------------------------------------------------------------------ 汇总 ---

def summarize(rows):
    s = {
        "n": len(rows),
        "by_carrier": {c: sum(1 for r in rows
                              if r.get("_file") == f"{c}.jsonl")
                       for c in GEN_CTYPES},
        "by_kind": {k: sum(1 for r in rows if r.get("kind") == k)
                    for k in KINDS},
        "by_language": {l: sum(1 for r in rows if r.get("language") == l)
                        for l in LANGS},
        "by_pack": {p: sum(1 for r in rows if r.get("policy_pack") == p)
                    for p in PACKS},
        "forward_true": sum(1 for r in rows if is_forward_payload(r)),
        "forward_false": sum(1 for r in rows if not is_forward_payload(r)),
        "adversarial_forward": sum(1 for r in rows if is_forward_payload(r)),
        "adversarial_expected": sum(1 for r in rows
                                    if is_expected_adversarial(r)),
        "clean_negative": sum(1 for r in rows if is_clean_negative(r)),
        "policy_conditional": sum(1 for r in rows
                                  if is_policy_conditional(r)),
        "policy_groups": len({r.get("group") for r in rows if r.get("group")}),
    }
    n = s["n"] or 1
    s["clean_negative_ratio"] = round(s["clean_negative"] / n, 4)
    s["adversarial_forward_ratio"] = round(s["adversarial_forward"] / n, 4)
    s["adversarial_expected_ratio"] = round(s["adversarial_expected"] / n, 4)
    cov = robustness_coverage(rows)
    s["robustness_by_carrier"] = {c: cov[c]["robustness"] for c in GEN_CTYPES}
    s["mechanism_kinds_by_carrier"] = {c: cov[c]["mechanism_kinds"]
                                       for c in GEN_CTYPES}
    s["mechanisms_by_carrier"] = {c: cov[c]["mechanisms"] for c in GEN_CTYPES}
    # 机制深度（2026-10-06）：逐机制条数 / 语言交叉 / 包覆盖
    depth = mechanism_depth(rows)
    s["mechanism_depth_by_carrier"] = depth
    s["mechanism_rows_by_carrier"] = {
        c: {m: d["n"] for m, d in depth[c].items()} for c in GEN_CTYPES}
    s["mechanism_lang_pack_by_carrier"] = {
        c: {m: {"n": d["n"], "languages": d["languages"], "packs": d["packs"]}
            for m, d in depth[c].items()}
        for c in GEN_CTYPES}
    counts = [d["n"] for c in GEN_CTYPES for d in depth[c].values()]
    s["mechanism_rows_total"] = len(counts)
    s["mechanism_rows_min"] = min(counts) if counts else 0
    s["mechanism_rows_median"] = (
        sorted(counts)[len(counts) // 2] if counts else 0)
    s["mechanism_language_cross"] = {
        c: sum(1 for d in depth[c].values()
               if set(d["languages"]) == set(LANGS)) for c in GEN_CTYPES}
    s["mechanism_language_cross_ratio"] = {
        c: (round(s["mechanism_language_cross"][c] / len(depth[c]), 4)
            if depth[c] else 0.0) for c in GEN_CTYPES}
    s["mechanism_pack_coverage"] = {
        c: sum(1 for d in depth[c].values()
               if set(d["packs"]) & set(NON_DEFAULT_PACKS))
        for c in GEN_CTYPES}
    s["mechanism_pack_coverage_ratio"] = {
        c: (round(s["mechanism_pack_coverage"][c] / len(depth[c]), 4)
            if depth[c] else 0.0) for c in GEN_CTYPES}
    s["non_default_pack_rows"] = sum(
        1 for r in rows if r.get("policy_pack") in NON_DEFAULT_PACKS)
    return s


def run(dir_path=GEN_DIR, *, train_scan=True, drift=True,
        sft_mix=SFT_MIX, strict_substring=False) -> tuple:
    """返回 (summary, problems, extras)。"""
    rows, raws, problems = load_dir(dir_path)
    disk_texts = {}
    for p in sorted(Path(dir_path).glob("*.jsonl")):
        disk_texts[p.name] = p.read_text(encoding="utf-8")
    problems = list(problems)
    problems += check_unique_ids(rows)
    problems += check_rows(rows, raws)
    problems += check_distribution(rows)
    problems += check_robustness_coverage(rows)
    problems += check_mechanism_depth(rows)
    problems += check_fictional_refs(rows)
    problems += check_carrier_coverage(rows)
    problems += check_policy_groups(rows)
    problems += check_parseable(rows)
    if drift:
        problems += check_drift(disk_texts)
    extras = {}
    if train_scan:
        info, probs = scan_train_disjoint(sft_mix)
        extras["train_scan"] = info
        problems += probs
        problems += check_train_disjoint(info,
                                         strict_substring=strict_substring)
    return summarize(rows), problems, extras


def main(argv=None):
    ap = argparse.ArgumentParser(description="v0.3-gen 未见载体门禁集校验（只读）")
    ap.add_argument("--dir", default=str(GEN_DIR))
    ap.add_argument("--sft-mix", default=str(SFT_MIX))
    ap.add_argument("--skip-train-scan", action="store_true",
                    help="跳过 data/lf/sft_m25.jsonl 全文不相交扫描")
    ap.add_argument("--skip-drift-check", action="store_true",
                    help="跳过与 meta_ser.build_texts() 的漂移锁")
    ap.add_argument("--strict-substring", action="store_true",
                    help="裸子串命中也算失败（默认只作情报：训练侧 FFmpeg "
                         "API 名 av_metadata_set2 会命中 av_metadata 子串）")
    ap.add_argument("--json", action="store_true", help="只打印 JSON 汇总")
    args = ap.parse_args(argv)

    summary, problems, extras = run(
        args.dir, train_scan=not args.skip_train_scan,
        drift=not args.skip_drift_check, sft_mix=args.sft_mix,
        strict_substring=args.strict_substring)
    if args.json:
        print(json.dumps({"summary": summary, "extras": extras,
                          "problems": problems}, ensure_ascii=False,
                         indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if extras.get("train_scan"):
            ts = extras["train_scan"]
            print(f"train scan: {ts['path']} rows={ts['rows']} "
                  f"size={ts['size_bytes']}")
            print(f"  载体信封计数: {ts['envelope_counts']}")
            print(f"  裸子串计数(情报): {ts['substring_counts']}")
            if ts.get("census_crosscheck"):
                print(f"  census 交叉核对: {ts['census_crosscheck']}")
            for t, note in (ts.get("substring_notes") or {}).items():
                print(f"  [note] {t}: {note}")
        if problems:
            print(f"\nPROBLEM ({len(problems)}):")
            for p in problems:
                print("  - " + p)
        else:
            print("\nOK: v0.3-gen 未见载体门禁集通过全部断言"
                  f"（{summary['n']} 条；对抗 forward={summary['forward_true']}"
                  f" / expected={summary['adversarial_expected']}）")
            print("  鲁棒性条(每载体下限 "
                  f"{MIN_ROBUSTNESS_PER_CARRIER}): "
                  + ", ".join(f"{c}={v}" for c, v in
                              summary["robustness_by_carrier"].items()))
            print("  机制种类(每载体下限 "
                  + ", ".join(f"{c}={v}" for c, v in
                              MIN_MECHANISM_KINDS.items()) + "): "
                  + ", ".join(f"{c}={v}" for c, v in
                              summary["mechanism_kinds_by_carrier"].items()))
            print(f"  干净负例(下限 {MIN_CLEAN_NEGATIVE_RATIO}): "
                  f"{summary['clean_negative']}/{summary['n']} = "
                  f"{summary['clean_negative_ratio']:.4f}")
            print(f"  机制深度(下限 {MIN_ROWS_PER_MECHANISM} 条/机制、zh+en、"
                  f"≥1 条 {'/'.join(NON_DEFAULT_PACKS)}): "
                  f"机制数={summary['mechanism_rows_total']} "
                  f"最小={summary['mechanism_rows_min']} "
                  f"中位={summary['mechanism_rows_median']}")
            for c in GEN_CTYPES:
                print(f"    {c}: 语言交叉 "
                      f"{summary['mechanism_language_cross'][c]}/"
                      f"{len(summary['mechanism_depth_by_carrier'][c])}"
                      f"（{summary['mechanism_language_cross_ratio'][c]:.4f}）"
                      f" / 包覆盖 "
                      f"{summary['mechanism_pack_coverage'][c]}/"
                      f"{len(summary['mechanism_depth_by_carrier'][c])}"
                      f"（{summary['mechanism_pack_coverage_ratio'][c]:.4f}）")
            print("  虚构性断言(RFC2606/5737 + 全零坐标): 通过"
                  f"（non-default pack 条数="
                  f"{summary['non_default_pack_rows']}）")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
