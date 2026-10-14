r"""t13 长文档检索种子生成器（M2.5 备料：needle 深位精确检索 SFT）。

背景（2026-09-28 深夜实测，父会话诊断）：M1.6-32k 恢复跑把 32k PPL 拉回
base 之下（en -7.4% / zh -11.1%），但 needle 深位检索未愈（6/12 vs base
12/12，32k/en 0/3）——wiki 叙事 CPT 不训练"深位精确检索"，正解是检索式
SFT 数据。本生成器产 t13 行族：长上下文 + 深位（相对深度 0.3-0.9）埋点 +
精确值检索 + 出处定位引用。

## 设计（组装式合成，上下文真实性优先）

- 上下文骨架 100% 取自 clean 语料层：en = enwiki_gen（百科叙事）/
  sans-isc（威胁简报）/ debian-dsa（安全通告）/ cve（通告条目）/
  cwe（弱点条目）/ t6_devign（代码清单）；zh = zhwiki_gen / zhwiki_sec /
  c2_privacy_cn_laws_full（法规条文）。绝不从零虚构整篇文档。
- 查询目标两种机制：
  - 埋入式（log-ip / credential / code-needle / wiki-fact / spec-block）：
    真实长文中按 token 深度受控插入原生形态针（登录日志摘录块 / 配置
    快照 / 代码 SEC 标记注释行 / 归档附注 / 版本记录块），深度定向。
  - 选取式（cve-digest / cwe-lookup / clause-lookup）：真实短条目拼接成
    通告摘要/弱点名录/条文选编，查询目标选取于相对深度 0.3-0.9 处的条目。
- 安全域倾斜 ~60%（异常 IP / 凭证泄露 / 代码 SEC 标记行 / 法规条款号 /
  CVE ID / CWE 编号），通用检索 ~40%（存档编号 / 底稿号 / 构建号 /
  版本字段值）——防过拟合到安全词表。
- hard-negative 15%：查询近义但目标不存在于文中（成功会话 IP / 缺席产品
  / 缺席条款号 / 缺席标记 / 缺席版本号 / 缺席附注字段）→ assistant 必答
  "文中未出现"而非幻觉；absent 术语写入 VERDICT findings 供独立复检。
- zh:en = 40:60（主集 600:900、深位 80:120）；三包梯度覆盖（default 为主、
  cons/prof 非零——检索行为 pack 无关，答案不随包分化，教包不变性）。
- 问题位置混合：~70% 问前文后（标准 QA），~30% 文末追问（对齐 needle
  探针的文末提问形态）。

## 红线与污染纪律（全继承 v0/m25）

- 评估/探针文本**永不进产物**：所有骨架单元过 8-gram 匹配器 v3 全量基线
  （探针四版本 + 留出三版本，与 check_m25_staging 同口径）单元级预筛，
  产物级再全量复扫断言零命中。基线在本文件中只用于**排除**方向（与
  check_m25_staging.py 的匹配器引用侧同性质）。
- GDPR 全文经实测与隐私探针系统性同文（74/114 条命中），弃用；原 en
  条款族容量并入 cve-digest（见配额表）。
- 不用 GPU；不写 data/lf/；不动 m1/v0/v0x 与 t1/t9 既有产物。
- 全部 assistant 以 VERDICT 行结尾（判分器 v2 严格模板层可解析）。
- PII 零真实值：IP 用 RFC 5737 文档段/私网段，凭证用合成形状，编号类值
  由确定性 rng 生成且断言全文唯一。

## 生产硬断言（本脚本内联 + scripts/check_t13.py 独立复检）

结构（字段集 = m1 契约 {id,task,pack,lang,messages} / system 政策引用 /
角色交替 / VERDICT 闭环 / policy==pack）、行数精确（主 1,500 / 深位 200）、
id 与 (pack,user) 唯一、lang↔内容一致（zh 行 user ≥10 CJK、en 行
user+assistant 零 CJK）、**深位断言**（hit 行答案值 token 相对深度 ∈
[0.30, 0.90]）、**答案唯一性**（hit 行答案值在文档区恰好出现 1 次）、
**出处可验证**（引用段/行处确实含答案值）、**包络**（主集全行
tokens+32 ≤ 4096；深位子集 8k-32k 落 t13_retrieval_longctx.jsonl 独立
文件——即 longctx 标记，M2.5 维持 cutoff 4096 时暂存不用）、配比精确
（zh:en、sec:gen、hardneg、三包非零）、与 v0/v0x/m1/m25-staging(t1,t9)
及跨文件零同文。

用法：.venv\\Scripts\\python.exe scripts\\gen_t13_retrieval.py
（确定性 seed=20260930；全程约 10-20 分钟：语料池筛查 + m1 去重基线 + 产物复扫）
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
from collections import deque
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gen_sft_v0 import (POLICY_SYSTEM, build_sample,  # noqa: E402  v0 契约复用
                        verdict_line)
from check_sft_contamination import (  # noqa: E402  匹配器 v3（排除方向）
    PREFIX_LEN, build_ngram_index, compile_alt_regex, doc_probe_hits,
    extract_ais_title, normalize, verify_shared_substring)

# ---------------------------------------------------------------- 常量区 ---
OUT_DIR = ROOT / "data" / "sft" / "m2.5-staging"
REPORTS = ROOT / "reports"
CLEAN = ROOT / "data" / "corpora" / "clean"
RNG_SEED = 20260930
N_MAIN, N_DEEP = 1500, 200
TOKENIZER_ID = "Qwen/Qwen3-0.6B-Base"    # 与训练谱系同 tokenizer（qwen3-06b 族）
CJK = re.compile(r"[\u4e00-\u9fff]")
DOC_MARK = {"zh": ("===== 文档开始 =====", "===== 文档结束 ====="),
            "en": ("===== DOCUMENT START =====", "===== DOCUMENT END =====")}
DEPTH_LO, DEPTH_HI = 0.30, 0.90          # 深位断言区间（相对 token 深度）
MAIN_DOC_LO, MAIN_DOC_HI = 1000, 3500    # 主集文档 token 包络
DEEP_DOC_LO, DEEP_DOC_HI = 8000, 32768   # 深位子集文档 token 包络
ROW_CAP = 4096 - 32                      # 主集全行 token 上限（含模板开销余量）

# 主集配额：family → lang → (hit, hardneg)
MAIN_QUOTA = {
    "log-ip":        {"en": (122, 22), "zh": (82, 14)},
    "credential":    {"en": (92, 16), "zh": (61, 11)},
    "cve-digest":    {"en": (202, 38)},
    "cwe-lookup":    {"en": (51, 9)},
    "clause-lookup": {"zh": (77, 13)},
    "code-needle":   {"en": (77, 13)},
    "wiki-fact":     {"en": (143, 25), "zh": (189, 33)},
    "spec-block":    {"en": (77, 13), "zh": (102, 18)},
}
# 深位子集配额（独立文件 = longctx 标记）
DEEP_QUOTA = {
    "log-ip":        {"en": (17, 3), "zh": (11, 2)},
    "credential":    {"en": (12, 2), "zh": (8, 2)},
    "cve-digest":    {"en": (23, 4)},
    "cwe-lookup":    {"en": (7, 1)},
    "clause-lookup": {"zh": (10, 2)},
    "code-needle":   {"en": (14, 2)},
    "wiki-fact":     {"en": (19, 3), "zh": (26, 4)},
    "spec-block":    {"en": (11, 2), "zh": (13, 2)},
}
SEC_FAMILIES = {"log-ip", "credential", "cve-digest", "cwe-lookup",
                "clause-lookup", "code-needle"}
DEEP_BUCKETS = [8192] * 20 + [12288] * 24 + [16384] * 36 + [20480] * 30 \
    + [24576] * 30 + [28672] * 24 + [32768] * 36
PACK_CYCLE = ["default", "professional", "default", "conservative"]

# 生产断言 0：源码不把评估目录当数据源引用（沿用 gen_sft_m25 口径：字面量
# 只允许出现在本断言内 ≤2 次；基线路径经 Path 部件拼接构造，仅供匹配器
# 排除方向使用——产物零命中断言是真正的双保险）
_src = Path(__file__).read_text(encoding="utf-8")
for _fp in ("data/probes", "data/heldout"):
    assert _src.count(_fp) <= 2, f"eval path referenced: {_fp}"


# ============================================================== 匹配器基线 ==
def load_baseline() -> dict:
    """8-gram 匹配器 v3 全量基线（探针四版本 + 留出三版本；仅用于排除）。"""
    probe_dirs = [ROOT / "data" / "probes" / v
                  for v in ("v0.1", "v0.1.1", "v0.3", "ais-500-draft")]
    heldout_dirs = [ROOT / "data" / "heldout" / v
                    for v in ("v0.1", "v0.2", "v0.2.1")]
    probes, ais_titles, seen = {}, {}, set()
    for d in probe_dirs:
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                j = json.loads(line)
                text = j.get("text") or ""
                if text:
                    key = normalize(text)
                    if key not in seen:
                        seen.add(key)
                        probes[f"{d.name}/{f.stem}:{j.get('id', len(probes))}"] = text
                        if f.stem == "ais":
                            t = extract_ais_title(text)
                            if t:
                                ais_titles.setdefault(normalize(t), 1)
    queries = set()
    for d in heldout_dirs:
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                j = json.loads(line)
                q = j.get("query") or j.get("text") or ""
                if q:
                    queries.add(normalize(q))
    return {"probes": probes,
            "index": build_ngram_index(probes),
            "prefix": compile_alt_regex(
                [normalize(t)[:PREFIX_LEN] for t in probes.values()
                 if len(normalize(t)) >= PREFIX_LEN]),
            "title": compile_alt_regex(
                [t for t in ais_titles if len(t) >= 16]),
            "query": compile_alt_regex(
                [q for q in queries if len(q) >= 12])}


def doc_contaminated(doc: str, base: dict) -> bool:
    t = normalize(doc)
    if base["prefix"].search(t) or base["title"].search(t) \
            or base["query"].search(t):
        return True
    for pid, win in doc_probe_hits(doc, base["index"]).items():
        if verify_shared_substring(doc, base["probes"][pid], window=win) >= 60:
            return True
    return False


# ================================================================== 分词器 ==
class Tok:
    def __init__(self):
        os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from transformers import AutoTokenizer
        self.t = AutoTokenizer.from_pretrained(TOKENIZER_ID)

    def n(self, text: str) -> int:
        return len(self.t(text, add_special_tokens=False)["input_ids"])


# ================================================================ 语料池 ====
def _reservoir(path: Path, k: int, keep, rng) -> list[tuple[int, str]]:
    """单遍流式蓄水池采样（确定性）。返回 (语料行号, text) 列表。"""
    buf: list[tuple[int, str]] = []
    i = 0
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f):
            if not line.strip():
                continue
            try:
                text = json.loads(line)["text"]
            except (json.JSONDecodeError, KeyError):
                continue
            if not keep(text):
                continue
            item = (line_no, text)
            if i < k:
                buf.append(item)
            else:
                j = rng.randint(0, i)
                if j < k:
                    buf[j] = item
            i += 1
    return buf


def _cap_paras(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    out, used = [], 0
    for p in text.split("\n\n"):
        if used + len(p) > max_chars:
            break
        out.append(p)
        used += len(p)
    return "\n\n".join(out) if out else text[:max_chars]


class Pools:
    """筛查后的骨架单元池。消耗型池（pop 后可回收）与复用型池（条目级采样）。"""

    def __init__(self, tok: Tok, base: dict, rng: random.Random):
        self.tok, self.base, self.rng = tok, base, rng
        self.stats: dict = {}
        self.consume: dict[str, deque] = {}
        self.spent: dict[str, list] = {}
        self.reuse: dict[str, list] = {}
        self.laws: list[tuple[str, list[str]]] = []   # (法规全名, [条文...])
        self._build()

    def _screen(self, corpus: str, cands: list[tuple[int, str]],
                lang: str) -> list[tuple[int, str]]:
        pool, flagged, cjk_drop, seen_t = [], 0, 0, set()
        for idx, t in cands:
            if lang == "en" and CJK.search(t):
                cjk_drop += 1
                continue
            nt = normalize(t)
            if nt in seen_t:
                continue
            if doc_contaminated(t, self.base):
                flagged += 1
                continue
            seen_t.add(nt)
            pool.append((idx, t))
        self.stats[corpus] = {"sampled": len(cands), "flagged": flagged,
                              "cjk_dropped": cjk_drop, "clean": len(pool)}
        print(f"  pool {corpus}: sampled={len(cands)} flagged={flagged} "
              f"cjk={cjk_drop} clean={len(pool)}", flush=True)
        return pool

    def _build(self) -> None:
        rng = self.rng

        def txt(pool):
            return deque(t for _, t in pool)

        self.consume["enwiki"] = txt(self._screen(
            "enwiki", _reservoir(CLEAN / "c1_enwiki_gen.jsonl", 1400,
                                 lambda t: len(t) >= 2000, rng), "en"))
        self.consume["zhwiki"] = txt(self._screen(
            "zhwiki", _reservoir(CLEAN / "c1_zhwiki_gen.jsonl", 1700,
                                 lambda t: len(t) >= 1200, rng), "zh"))
        self.consume["zhsec"] = txt(self._screen(
            "zhsec", _reservoir(CLEAN / "c1_zhwiki_sec.jsonl", 900,
                                lambda t: len(t) >= 1200, rng), "zh"))
        self.consume["sans"] = txt(self._screen(
            "sans", [(i, _cap_paras(t, 16000)) for i, t in _reservoir(
                CLEAN / "c0_sans-isc.jsonl", 1500,
                lambda t: len(t) >= 800, rng)], "en"))
        self.consume["dsa"] = txt(self._screen(
            "dsa", [(i, _cap_paras(t, 16000)) for i, t in _reservoir(
                CLEAN / "c0_debian-dsa.jsonl", 1000,
                lambda t: len(t) >= 1200, rng)], "en"))

        def devign_keep(t: str) -> bool:
            parts = t.split("\n\n", 1)
            return len(parts) == 2 and 500 <= len(parts[1]) <= 9000

        self.consume["devign"] = txt(self._screen(
            "devign", [(i, p.split("\n\n", 1)[1].replace("\n\n", "\n"))
                       for i, p in _reservoir(
                           CLEAN / "t6_devign.jsonl", 1500, devign_keep, rng)],
            "en"))
        # cve/cwe：条目必须单行（摘要拼接与"第 k 条=第 k 段"引用约定）
        self.reuse["cve"] = [t for _, t in self._screen(
            "cve", [(i, t) for i, t in _reservoir(
                CLEAN / "c0_cve.jsonl", 18000,
                lambda t: 100 <= len(t) <= 2500 and "\n" not in t, rng)],
            "en")]
        self.reuse["cwe"] = [t for _, t in self._screen(
            "cwe", [(i, t) for i, t in enumerate(
                [json.loads(l)["text"] for l in
                 (CLEAN / "c0_cwe.jsonl").read_text(encoding="utf-8")
                 .splitlines() if l.strip()])
                if "\n" not in t], "en")]

        # 法规条文（c2_privacy_cn_laws_full：4 部法规按行首"第X条"切分）
        law_rows = [json.loads(l)["text"] for l in
                    (CLEAN / "c2_privacy_cn_laws_full.jsonl").read_text(
                        encoding="utf-8").splitlines() if l.strip()]
        law_units = []
        for text in law_rows:
            lines = text.split("\n")
            law_full = lines[0].split("（")[0].strip()
            clauses, cur = [], None
            for ln in lines[1:]:
                s = ln.strip()
                if re.match(r"^第[一二三四五六七八九十百零]+条", s):
                    if cur:
                        clauses.append(cur)
                    cur = s
                elif cur is not None and s:
                    cur += s
            if cur:
                clauses.append(cur)
            assert 40 <= len(clauses) <= 130, \
                f"law parse anomaly: {law_full} -> {len(clauses)} clauses"
            self.laws.append((law_full, clauses))
            law_units += clauses
        screened = self._screen("cn_laws",
                                [(i, t) for i, t in enumerate(law_units)],
                                "zh")
        clean_set = {t for _, t in screened}
        self.laws = [(full, [c for c in cs if c in clean_set])
                     for full, cs in self.laws]
        assert all(len(cs) >= 40 for _, cs in self.laws), "law clauses lost"

    def pop(self, corpora: list[str]) -> tuple[str, str]:
        """按序从消耗型池取单元；主池耗尽时回灌重洗一次。"""
        for c in corpora:
            q = self.consume.get(c)
            if q:
                item = (c, q.popleft())
                self.spent.setdefault(c, []).append(item[1])
                return item
        c = corpora[0]
        sp = self.spent.get(c) or []
        if not sp:
            raise RuntimeError(f"pools exhausted: {corpora}")
        self.rng.shuffle(sp)
        self.consume[c] = deque(sp)
        self.spent[c] = []
        self.spent[c].append(sp[0])
        return c, self.consume[c].popleft()

    def pushback(self, corpus: str, text: str) -> None:
        self.consume.get(corpus, deque()).append(text)


# ============================================================ 组装引擎 ====
class Row:  # 生成态（不进产物；供断言与复检使用）
    def __init__(self, **kw):
        self.__dict__.update(kw)


def para_tokens(paras: list[tuple[str, int]]) -> int:
    return sum(pt for _, pt in paras)


def build_backbone(pools: Pools, corpora: list[str], budget: int, tok: Tok,
                   usage: list) -> list[tuple[str, int]]:
    """拼骨架至 token 预算（末单元按段截断）。paras = [(text, tokens)]。"""
    paras: list[tuple[str, int]] = []
    used = 0
    while used < budget:
        c, text = pools.pop(corpora)
        usage.append((c, text[:60]))
        # 段粒度：有空行按空行；纯单换行文本（简报/通告/日志式）按行
        parts = (text.split("\n\n") if "\n\n" in text
                 else [ln for ln in text.split("\n") if ln.strip()])
        # +1/段 ≈ "\n\n" 连接边界 token——避免 sum-of-parts 低估真实 doc 长度
        tp = [(p, tok.n(p) + 1) for p in parts if p.strip()]
        total = sum(pt for _, pt in tp)
        if total <= budget - used:
            paras.extend(tp)
            used += total
        else:
            room, keep, k = budget - used, [], 0
            for p, pt in tp:
                if k + pt > room:
                    break
                keep.append((p, pt))
                k += pt
            if len(keep) >= 2:
                paras.extend(keep)
                used += k
            break
    assert paras and used >= budget * 0.75, \
        f"backbone underfill {used}/{budget} ({corpora})"
    return paras


def insert_at_depth(paras: list[tuple[str, int]], needle: str,
                    tok: Tok, rng: random.Random) -> list[tuple[str, int]]:
    """把 needle 作为独立段插入 token 深度带内（就近边界，带外即 Retry）。"""
    nt = tok.n(needle) + 1                        # +1 连接边界
    total = para_tokens(paras) + nt
    cums = [0]
    for _, pt in paras:
        cums.append(cums[-1] + pt)
    d = rng.uniform(0.36, 0.84)
    at = None
    for _, i in sorted((abs(cums[i] / total - d), i)
                       for i in range(len(paras) + 1)):
        if 0.32 <= cums[i] / total <= 0.88:
            at = i
            break
    if at is None:
        raise Retry("no insertion point in depth band")
    return paras[:at] + [(needle, nt)] + paras[at:]


def doc_from_paras(paras: list[tuple[str, int]]) -> str:
    return "\n\n".join(p for p, _ in paras)


def depth_of(doc: str, value: str, tok: Tok) -> float:
    off = doc.index(value)
    return tok.n(doc[:off]) / max(1, tok.n(doc))


def para_index_of(doc: str, value: str) -> int:
    return doc[: doc.index(value)].count("\n\n") + 1


def line_index_of(doc: str, value: str) -> int:
    return doc[: doc.index(value)].count("\n") + 1


def trim_quote(s: str, limit: int = 110) -> str:
    """截引文到 limit 内（硬截断、不加省略号——保证是文档区精确子串，
    供 hit 行“引文在文中”断言与 check_t13.py 复检）。"""
    s = s.strip()
    return s[:limit]


# ------------------------------------------------------------ 值与针生成 --
_DOC_IPS = ("203.0.113.", "198.51.100.", "192.0.2.")


def rand_ip(rng) -> str:
    return rng.choice(_DOC_IPS) + str(rng.randint(20, 240))


def rand_hex(rng, n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def rand_token(rng) -> str:
    shape = rng.randrange(3)
    if shape == 0:
        return f"sk-svc-{rand_hex(rng, 12)}"
    if shape == 1:
        return f"{rand_hex(rng, 8)}-{rand_hex(rng, 4)}-{rand_hex(rng, 12)}"
    return "AKIAIOSFODNN7EXAMPLE"


def rand_code(rng) -> str:
    return rng.choice(("AX", "KZ", "MR", "GS", "DT")) + "-" \
        + str(rng.randint(1000, 99999))


def rand_batch(rng) -> str:
    return f"B{rng.randint(10, 29)}-{rng.randint(100, 999)}"


def rand_bld(rng) -> str:
    return f"BLD-{rng.randint(2100, 9899)}"


def rand_ts(rng) -> str:
    return f"{rng.randint(1, 23):02d}:{rng.randint(0, 59):02d}:" \
           f"{rng.randint(0, 59):02d}"


def rand_date(rng) -> str:
    return f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def rand_ver(rng) -> str:
    return f"{rng.randint(0, 1)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"


def log_needle(rng, lang) -> tuple[str, str, str, list[str], str]:
    """登录日志摘录块：三行三个互异文档段 IP；目标行账户名唯一。
    返回 (块文本, 目标IP, 首行时间戳, 全部IP, 目标账户名)。"""
    ips = []
    while len(ips) < 3:
        ip = rand_ip(rng)
        if ip not in ips:
            ips.append(ip)
    tgt = rng.randrange(3)
    users = ["root", "root", "root"]
    users[tgt] = rng.choice(("admin", "svc_deploy", "audit"))
    t0 = rand_ts(rng)
    ts = [t0]
    for _ in range(2):
        t = rand_ts(rng)
        while t <= ts[-1]:
            t = rand_ts(rng)
        ts.append(t)
    port = [rng.randint(49200, 61000) for _ in range(3)]
    head = (f"[节点 build-{rng.randint(2, 88):02d} auth.log 摘录 "
            f"{rand_date(rng)}]" if lang == "zh" else
            f"[node build-{rng.randint(2, 88):02d} auth.log excerpt "
            f"{rand_date(rng)}]")
    lines = [head] + [
        f"{ts[i]} sshd[{20000 + rng.randint(100, 900)}]: Failed password "
        f"for {users[i]} from {ips[i]} port {port[i]} ssh2"
        for i in range(3)]
    return "\n".join(lines), ips[tgt], t0, ips, users[tgt]


def cred_needle(rng, lang) -> tuple[str, str]:
    """配置快照块。返回 (块文本, api_key 值)。"""
    key = rand_token(rng)
    head = (f"[网关认证服务配置快照 {rand_date(rng)} "
            f"build-{rng.randint(2, 88):02d}]" if lang == "zh" else
            f"[gateway auth-service config snapshot {rand_date(rng)} "
            f"build-{rng.randint(2, 88):02d}]")
    lines = [head, f"api_key = {key}",
             f"session_ttl = {rng.choice((1800, 3600, 7200))}s",
             "audit_sink = syslog:localhost:514"]
    return "\n".join(lines), key


def spec_needle(rng, lang) -> tuple[str, list[str], list[str]]:
    """版本记录块（3 行）。返回 (块文本, 版本列表, 构建号列表)。"""
    vers = []
    while len(vers) < 3:
        v = rand_ver(rng)
        if v not in vers:
            vers.append(v)
    blds = []
    while len(blds) < 3:
        b = rand_bld(rng)
        if b not in blds:
            blds.append(b)
    dates = []
    while len(dates) < 3:
        d = rand_date(rng)
        if d not in dates:
            dates.append(d)
    dates.sort()
    if lang == "zh":
        lines = ["[维护归档：版本与构建记录]",
                 f"- v{vers[0]}（{dates[0]}）：修复连接池泄漏，构建号 {blds[0]}",
                 f"- v{vers[1]}（{dates[1]}）：修复缓存竞争，构建号 {blds[1]}",
                 f"- v{vers[2]}（{dates[2]}）：新增导出模块，构建号 {blds[2]}"]
    else:
        lines = ["[Maintenance archive: versions and builds]",
                 f"- v{vers[0]} ({dates[0]}): connection-pool leak fix, "
                 f"build {blds[0]}",
                 f"- v{vers[1]} ({dates[1]}): cache-race fix, build {blds[1]}",
                 f"- v{vers[2]} ({dates[2]}): export module added, "
                 f"build {blds[2]}"]
    return "\n".join(lines), vers, blds


S6_MARKERS = ("FIXME-SEC", "NOTE-SEC", "AUDIT-SEC")
S6_DESC_ZH = {"FIXME-SEC": "服务令牌", "NOTE-SEC": "调试端点",
              "AUDIT-SEC": "审计密钥"}
S6_DESC_EN = {"FIXME-SEC": "service token", "NOTE-SEC": "debug endpoint",
              "AUDIT-SEC": "audit key"}


def code_needle(rng, marker) -> tuple[str, str]:
    """代码 SEC 标记注释行。返回 (行文本, 目标值)。"""
    if marker == "FIXME-SEC":
        v = f"svc-legacy-{rand_hex(rng, 6)}"
        return (f"    /* FIXME-SEC: rotate hardcoded service token {v} "
                f"before decommission */", v)
    if marker == "NOTE-SEC":
        v = (f"10.{rng.randint(0, 31)}.{rng.randint(0, 255)}."
             f"{rng.randint(2, 254)}:{rng.randint(1024, 65535)}")
        return (f"    // NOTE-SEC: debug endpoint {v} enabled in this "
                f"build, do not ship", v)
    v = f"keyid-{rand_hex(rng, 8)}"
    return f"    /* AUDIT-SEC: audit key {v} rotates quarterly, owner sec-ops */", v


# ------------------------------------------------------------ 问题与模板 --
DOC_LABEL = {
    "log-ip":       {"zh": "安全主题资料汇编", "en": "threat-diary compilation"},
    "credential":   {"zh": "安全主题资料汇编",
                     "en": "security advisory compilation"},
    "cve-digest":   {"en": "CVE advisory digest"},
    "cwe-lookup":   {"en": "CWE reference digest"},
    "clause-lookup": {"zh": "法规条文选编"},
    "code-needle":  {"en": "source-code listing"},
    "wiki-fact":    {"zh": "百科条目存档", "en": "encyclopedia article archive"},
    "spec-block":   {"zh": "资料档案汇编", "en": "archived reference dossier"},
}

FRAME_ZH = [
    "下面是一份{doc_label}。请只依据文中内容检索：{question}"
    "。若文中没有所问信息，请直接说明，不要推测。",
    "请在下面这份{doc_label}中完成检索——{question}"
    "。答案必须来自原文并给出处；文中未出现时请如实回答。",
    "检索任务：{question}。请从下面的{doc_label}中找出精确值并注明位置"
    "（段/行）；找不到就说明不存在。",
]
FRAME_EN = [
    "Below is {art} {doc_label}. Using only the text, retrieve: {question}. "
    "If the information is not present in the text, state that plainly "
    "instead of guessing.",
    "Search the {doc_label} below and answer: {question}. The answer must "
    "come from the text itself; if it is absent, say so.",
    "Retrieval task: {question}. Locate the exact value in the {doc_label} "
    "below and cite its position, or report that it does not appear.",
]
FRAME_AFTER_ZH = [
    "请阅读下面的{doc_label}，然后回答文末的检索问题。",
    "下面是一份{doc_label}，文末附有一个检索问题，请依据原文作答。",
]
FRAME_AFTER_EN = [
    "Read the {doc_label} below, then answer the retrieval question at "
    "the end.",
    "Below is {art} {doc_label} with one retrieval question appended at "
    "the end; answer it from the text.",
]
TAIL_ZH = ["检索问题：{question}", "现在请回答：{question}"]
TAIL_EN = ["Retrieval question: {question}", "Now answer: {question}"]


def make_user(lang: str, family: str, question: str, doc: str,
              rng: random.Random) -> str:
    m0, m1 = DOC_MARK[lang]
    label = DOC_LABEL[family][lang]
    art = "an" if label[0].lower() in "aeiou" else "a"
    if rng.random() < 0.7:                      # 问前文后（标准 QA）
        tpl = rng.choice(FRAME_ZH if lang == "zh" else FRAME_EN)
        return tpl.format(art=art, doc_label=label, question=question) \
            + f"\n\n{m0}\n{doc}\n{m1}"
    tpl = rng.choice(FRAME_AFTER_ZH if lang == "zh" else FRAME_AFTER_EN)
    tail = rng.choice(TAIL_ZH if lang == "zh" else TAIL_EN)
    return tpl.format(art=art, doc_label=label) + f"\n\n{m0}\n{doc}\n{m1}\n\n" \
        + tail.format(question=question)


def hit_reply(lang, value, cite, quote, pack, rng) -> str:
    conf = rng.choice((0.9, 0.92, 0.93, 0.95))
    if lang == "zh":
        body = f"{value}。\n出处：{cite}，原文摘录：“{quote}”。"
    else:
        body = f"{value}.\nLocation: {cite} — verbatim: “{quote}”."
    return body + "\n" + verdict_line("answer", "retrieved", conf, [], pack)


def miss_reply(lang, evidence, absent, pack, rng) -> str:
    conf = rng.choice((0.88, 0.9))
    if lang == "zh":
        body = f"文中未出现所问信息：{evidence}"
    else:
        body = (f"The requested information does not appear in the "
                f"document: {evidence}")
    return body + "\n" + verdict_line(
        "answer", "not-in-doc", conf, [f"absent: {absent}"], pack)


class Retry(Exception):
    pass


def check_common(row: Row, lang: str, doc: str, kind: str, value: str,
                 absent: str, tok: Tok, pack: str, user: str,
                 assistant: str, deep: bool) -> None:
    """族无关生产断言（失败抛 AssertionError → 整行重建）。"""
    if kind == "hit":
        assert doc.count(value) == 1, "answer value not unique in doc"
        assert 0.30 <= depth_of(doc, value, tok) <= DEPTH_HI, \
            f"depth {depth_of(doc, value, tok):.3f} out of band"
    else:
        assert absent and doc.count(absent) == 0, "absent term present"
    dt = tok.n(doc)
    if deep:
        assert DEEP_DOC_LO <= dt <= DEEP_DOC_HI, f"deep doc tokens {dt}"
    else:
        assert MAIN_DOC_LO <= dt <= MAIN_DOC_HI, f"main doc tokens {dt}"
        total = tok.n(POLICY_SYSTEM[pack]["zh" if lang == "zh" else "en"]) \
            + tok.n(user) + tok.n(assistant)
        assert total <= ROW_CAP, f"row tokens {total} > {ROW_CAP}"
    if lang == "zh":
        assert len(CJK.findall(user)) >= 10, "zh user lacks CJK"
    else:
        assert not CJK.search(user) and not CJK.search(assistant), \
            "en content contains CJK"
    assert quote_marker_ok(user, lang), "doc markers malformed"


def quote_marker_ok(user: str, lang: str) -> bool:
    m0, m1 = DOC_MARK[lang]
    return user.count(m0) == 1 and user.count(m1) == 1


# ============================================================== 族构建器 ==
# 每个构建器返回 dict：doc/question/value/absent/cite/quote/evidence
Q_LOGIP_ZH = ["登录摘录中对 {user} 账户的失败登录来自哪个 IP？",
              "auth 摘录里 {user} 那条失败记录的来源 IP 是多少？",
              "摘录中针对 {user} 的 Failed password 记录来源地址是多少？"]
Q_LOGIP_EN = ["Which source IP made the failed login attempt against the "
              "{user} account in the excerpt?",
              "In the auth excerpt, what is the source IP of the failed "
              "record for {user}?"]
Q_LOGT_ZH = ["登录摘录中最早一条失败登录的时间戳是多少？",
             "摘录里第一条 Failed password 记录的时间是什么？"]
Q_LOGT_EN = ["What is the timestamp of the earliest failed login in the "
             "excerpt?",
             "At what time did the first Failed password record in the "
             "excerpt occur?"]
Q_CRED_ZH = ["配置快照中 api_key 的取值是多少？",
             "网关认证服务的 api_key 值是什么？",
             "快照里 api_key 字段的内容是多少？"]
Q_CRED_EN = ["What is the value of api_key in the config snapshot?",
             "What does the api_key field contain in the snapshot?"]
Q_CVE_EN = ["Which CVE ID in the digest describes {phrase}?",
            "In the digest below, what CVE number corresponds to the entry "
            "mentioning {phrase}?",
            "Locate the CVE ID for the advisory in the digest that "
            "mentions {phrase}."]
Q_CVE_NEG_EN = ["Which CVE ID in the digest affects {term}?",
                "What CVE number in the digest covers {term}?"]
Q_CWE_EN = ["What is the CWE ID for “{name}”?",
            "In the digest, which CWE number is assigned to the weakness "
            "named “{name}”?"]
Q_CWE_NEG_EN = ["What is the CWE ID for “{name}”?"]
Q_CLAUSE_ZH = ["条文选编中，包含“{key}”内容的是哪一条？",
               "选编里哪一条规定了“{key}”？"]
Q_CLAUSE2_ZH = ["《{law}》{no}的主要规定是什么？",
                "选编中《{law}》{no}规定了什么？"]
Q_CLAUSE_NEG_ZH = ["条文选编中{no}的内容是什么？",
                   "选编里{no}作了什么规定？"]
Q_CODE_EN = ["Which line of the listing carries the {marker} marker, and "
             "what is the {desc} it names?",
             "Find the {marker} marker line in the listing: what line "
             "number is it on, and what {desc} does it name?"]
Q_CODE_NEG_EN = ["Which line of the listing carries the {marker} marker?"]
Q_WIKI_NOTE_ZH = ["归档附注中的存档编号是多少？",
                  "条目的存档编号是什么（见归档附注）？"]
Q_WIKI_NOTE_EN = ["What is the archive code in the archive note?",
                  "What archive code does the archive note record?"]
Q_WIKI_BATCH_ZH = ["归档附注中的校对批次是多少？"]
Q_WIKI_BATCH_EN = ["What is the proofing batch in the archive note?"]
Q_WIKI_INLINE_ZH = ["修订核对所用的底稿编号是多少？",
                    "文中提到的底稿编号是什么？"]
Q_WIKI_INLINE_EN = ["What is the master draft code mentioned for the "
                    "revision check?",
                    "Which draft code does the revision-check note record?"]
Q_WIKI_FOOT_ZH = ["本段资料登记的批次号是多少？",
                  "登记的批次号是什么（见文内注释）？"]
Q_WIKI_FOOT_EN = ["What is the registration batch noted for this section?",
                  "Which registration batch does the in-text note give?"]
Q_WIKI_NEG_ZH = {"note": "归档附注中复核员的代号是多少？",
                 "inline": "文中提到的交接登记号是多少？",
                 "foot": "登记记录里校对员的代号是多少？"}
Q_WIKI_NEG_EN = {"note": "What is the reviewer code in the archive note?",
                 "inline": "What is the handover log number mentioned in "
                 "the text?",
                 "foot": "What proofreader id does the registration note "
                 "record?"}
Q_SPEC_ZH = ["版本记录中 v{ver} 对应的构建号是多少？",
             "维护归档里 v{ver} 的构建号是什么？"]
Q_SPEC_EN = ["What is the build number for v{ver} in the version record?",
             "In the maintenance archive, which build corresponds to "
             "v{ver}?"]
Q_SPEC_NEG_ZH = ["版本记录中 v{ver} 对应的构建号是多少？"]
Q_SPEC_NEG_EN = ["What is the build number for v{ver} in the version "
                 "record?"]
ABSENT_PRODUCTS = ["nginx", "WordPress", "Apache Tomcat", "Chrome",
                   "Firefox", "Squid", "Postfix", "cPanel", "Drupal",
                   "Jenkins", "Gitea", "ownCloud"]
ABSENT_CLAUSES = ["第六十条", "第七十条", "第八十条", "第九十条",
                  "第九十九条", "第一百零八条", "第一百二十条"]
ABSENT_VERS = ["v2.5.0", "v3.1.0", "v0.9.4", "v4.0.1"]


def _fam_log_ip(pools, tok, rng, lang, kind, budget, deep, usage):
    corpora = ["sans"] if lang == "en" else ["zhsec", "zhwiki"]
    paras = build_backbone(pools, corpora, budget - 80, tok, usage)
    block, tgt_ip, t0, ips, tgt_user = log_needle(rng, lang)
    paras = insert_at_depth(paras, block, tok, rng)
    doc = doc_from_paras(paras)
    out = {"doc": doc}
    if kind == "hit":
        if rng.random() < 0.7:                       # IP 目标
            value = tgt_ip
            q = rng.choice(Q_LOGIP_ZH if lang == "zh" else Q_LOGIP_EN)
            out["question"] = q.format(user=tgt_user)
        else:                                        # 时间戳目标
            value = t0
            out["question"] = rng.choice(
                Q_LOGT_ZH if lang == "zh" else Q_LOGT_EN)
        blines = block.split("\n")
        li = next(i for i, ln in enumerate(blines) if value in ln)
        line = blines[li]
        p = para_index_of(doc, value)
        out["value"] = value
        out["cite"] = (f"文档第 {p} 段（登录摘录块）第 {li + 1} 行"
                       if lang == "zh" else
                       f"paragraph {p} of the document "
                       f"(login-excerpt block), line {li + 1}")
        out["quote"] = trim_quote(line)
    else:
        if lang == "zh":
            out["question"] = (f"登录摘录中对 {tgt_user} 账户的成功登录"
                               f"（Accepted password）会话来自哪个 IP？")
        else:
            out["question"] = (f"Which source IP made the successful "
                               f"login (Accepted password) session for "
                               f"the {tgt_user} account in the excerpt?")
        out["absent"] = "Accepted password"
        out["evidence"] = (
            f"摘录块共 3 条记录，均为 Failed password 失败尝试（涉及 "
            f"root 与 {tgt_user}），全文未出现成功登录（Accepted "
            f"password）记录。"
            if lang == "zh" else
            f"the excerpt block holds 3 records, all \"Failed password\" "
            f"attempts (against root and {tgt_user}); no successful "
            f"\"Accepted password\" session appears anywhere in the text.")
    return out


def _fam_credential(pools, tok, rng, lang, kind, budget, deep, usage):
    corpora = ["dsa"] if lang == "en" else ["zhsec", "zhwiki"]
    paras = build_backbone(pools, corpora, budget - 60, tok, usage)
    block, key = cred_needle(rng, lang)
    paras = insert_at_depth(paras, block, tok, rng)
    doc = doc_from_paras(paras)
    out = {"doc": doc}
    if kind == "hit":
        out["value"] = key
        out["question"] = rng.choice(Q_CRED_ZH if lang == "zh" else Q_CRED_EN)
        p = para_index_of(doc, key)
        out["cite"] = (f"文档第 {p} 段（配置快照块）第 2 行" if lang == "zh"
                       else f"paragraph {p} of the document "
                            f"(config snapshot block), line 2")
        out["quote"] = trim_quote(f"api_key = {key}")
    else:
        out["question"] = (rng.choice(Q_CRED_ZH).replace(
            "api_key", "db_password（数据库连接密码）")
            if lang == "zh" else "What is the value of db_password in the "
            "config snapshot?")
        out["absent"] = "db_password"
        out["evidence"] = (
            "配置快照仅含 api_key / session_ttl / audit_sink 三个字段，"
            "全文未出现 db_password。"
            if lang == "zh" else
            "the config snapshot contains only api_key / session_ttl / "
            "audit_sink; db_password does not appear in the text.")
    return out


def _fam_cve_digest(pools, tok, rng, lang, kind, budget, deep, usage):
    budget = min(budget, 3300 if not deep else 32600)
    k = max(6, int(budget / 130) + 3)
    entries = rng.sample(pools.reuse["cve"],
                         min(k, len(pools.reuse["cve"])))
    for e in entries:
        usage.append(("cve", e[:60]))
    kept, used = [], 0
    hard_cap = 3490 if not deep else 32760
    soft_floor = 1000 if not deep else 8000
    for e in entries:
        et = tok.n(e) + 1                        # +1 连接边界
        if used + et > hard_cap:
            break
        if used + et > budget and used >= max(soft_floor, budget * 0.75):
            break
        kept.append(e)
        used += et
        if used >= budget:
            break
    doc = "\n\n".join(kept)
    out = {"doc": doc}
    if kind == "hit":
        total = tok.n(doc)
        cum, target = 0, None
        for e in kept:
            et = tok.n(e)
            frac = (cum + et / 2) / total
            if 0.34 <= frac <= 0.86:
                target = e
                break
            cum += et
        if target is None:
            raise Retry("no target at depth")
        m = re.match(r"(CVE-\d{4}-\d+):\s*(.+)", target)
        if not m:
            raise Retry("cve entry head")
        value = m.group(1)
        desc = re.split(r"\s*Affected products:", m.group(2))[0]
        words = desc.split()
        phrase = None
        for s in range(rng.randrange(0, 4), max(1, len(words) - 2)):
            cand = " ".join(words[s: s + 3])
            if len(cand) < 14 or "http" in cand:
                continue
            if doc.count(cand) == 1:
                phrase = cand
                break
        if phrase is None:
            raise Retry("no unique phrase")
        out["value"] = value
        out["question"] = rng.choice(Q_CVE_EN).format(phrase=phrase)
        p = para_index_of(doc, value)
        out["cite"] = (f"entry {p} of the digest (paragraph {p} of the "
                       f"document)")
        out["quote"] = trim_quote(target, 90)
    else:
        term = next((t for t in rng.sample(ABSENT_PRODUCTS, len(
            ABSENT_PRODUCTS)) if doc.count(t) == 0), None)
        if term is None:
            raise Retry("no absent product")
        out["question"] = rng.choice(Q_CVE_NEG_EN).format(term=term)
        out["absent"] = term
        out["evidence"] = (f"the digest contains {len(kept)} CVE entries, "
                           f"and none of them mentions {term}.")
    return out


def _fam_cwe_lookup(pools, tok, rng, lang, kind, budget, deep, usage):
    budget = min(budget, 3300 if not deep else 32600)
    k = max(5, int(budget / 210) + 3)
    picked = rng.sample(pools.reuse["cwe"],
                        min(k, len(pools.reuse["cwe"])))
    for e in picked:
        usage.append(("cwe", e[:60]))
    kept, used = [], 0
    hard_cap = 3490 if not deep else 32760
    soft_floor = 1000 if not deep else 8000
    for e in picked:
        et = tok.n(e) + 1                        # +1 连接边界
        if used + et > hard_cap:
            break
        if used + et > budget and used >= max(soft_floor, budget * 0.75):
            break
        kept.append(e)
        used += et
        if used >= budget:
            break
    doc = "\n\n".join(kept)
    kept_set = set(kept)
    parsed = []
    for e in kept:
        m = re.match(r"(CWE-\d+)\s+([^:]+?):", e)
        if m:
            name = re.sub(r"\s*\((?:Complete|Incomplete|Deprecated|"
                          r"Obsolete)\)\s*$", "", m.group(2).strip())
            parsed.append((e, m.group(1), name))
    if len(parsed) < max(4, len(kept) // 2):
        raise Retry("cwe parse yield low")
    out = {"doc": doc}
    if kind == "hit":
        total = tok.n(doc)
        cum = 0
        target = None
        for e, cid, name in parsed:
            et = tok.n(e)
            if 0.34 <= (cum + et / 2) / total <= 0.86:
                target = (e, cid, name)
                break
            cum += et
        if target is None:
            raise Retry("no target at depth")
        e, cid, name = target
        if doc.count(name) != 1:
            raise Retry("cwe name not unique")
        out["value"] = cid
        out["question"] = rng.choice(Q_CWE_EN).format(name=name)
        p = para_index_of(doc, cid)
        out["cite"] = (f"entry {p} of the digest (paragraph {p} of the "
                       f"document)")
        out["quote"] = trim_quote(e, 90)
    else:
        outside = [e for e in pools.reuse["cwe"] if e not in kept_set]
        m = re.match(r"(CWE-\d+)\s+([^:]+?):", rng.choice(outside))
        if not m:
            raise Retry("neg name parse")
        name = re.sub(r"\s*\((?:Complete|Incomplete|Deprecated|"
                      r"Obsolete)\)\s*$", "", m.group(2).strip())
        if doc.count(name) != 0:
            raise Retry("neg name present")
        out["question"] = rng.choice(Q_CWE_NEG_EN).format(name=name)
        out["absent"] = name
        out["evidence"] = (f"the digest contains {len(kept)} CWE entries; "
                           f"no weakness named {name} appears in the text.")
    return out


_CLAUSE_RE = re.compile(r"^(第[一二三四五六七八九十百零]+条)")


def law_window(pools, tok, rng, budget, deep):
    """法规条文窗口：主集单法窗口；深位跨法续接（带《法规名》（节选续）头）。"""
    laws = pools.laws
    li = rng.randrange(len(laws))
    full, clauses = laws[li]
    need = budget // 110 + 2
    if not deep:
        start = rng.randrange(max(1, len(clauses) - need))
        seq = [(c, full) for c in clauses[start:]]
    else:
        start = rng.randrange(len(clauses))
        seq = [(c, full) for c in clauses[start:]]
        for j in list(range(li + 1, len(laws))) + list(range(0, li)):
            f2, c2 = laws[j]
            seq.append((f"《{f2}》（节选续）", None))
            seq += [(c, f2) for c in c2]
    out, used = [], 0
    hard_cap = 3490 if not deep else 32760
    soft_floor = 1000 if not deep else 8000
    for text, lf in seq:
        pt = tok.n(text) + 1                     # +1 连接边界
        if used + pt > hard_cap:
            break
        if used + pt > budget and used >= max(soft_floor, budget * 0.75):
            break
        if lf is None and used + pt > budget:
            break
        out.append((text, pt, lf))
        used += pt
        if used >= budget:
            break
    if len([o for o in out if o[2]]) < 5:
        raise Retry("law window too small")
    return out


def _fam_clause_lookup(pools, tok, rng, lang, kind, budget, deep, usage):
    budget = min(budget, 3230 if not deep else 32500)
    parts = law_window(pools, tok, rng, budget, deep)
    usage.append(("cn_laws", f"{len(parts)} clauses"))
    doc = "\n\n".join(t for t, _, _ in parts)
    out = {"doc": doc}
    clauses = [(t, lf) for t, pt, lf in parts if lf is not None]
    if kind == "hit":
        total = tok.n(doc)
        cum = 0
        target = None
        for t, lf in clauses:
            ct = tok.n(t)
            if 0.34 <= (cum + ct / 2) / total <= 0.86:
                target = (t, lf)
                break
            cum += ct
        if target is None:
            raise Retry("no clause at depth")
        text, law_full = target
        m = _CLAUSE_RE.match(text)
        if not m:
            raise Retry("clause head")
        no = m.group(1)
        body = text[m.end():].strip()
        law_short = law_full.replace("中华人民共和国", "")
        if rng.random() < 0.6:                       # 内容 → 条号
            key = None
            for s in range(0, max(1, len(body) - 12), 3):
                cand = body[s: s + 12]
                if len(CJK.findall(cand)) >= 8 and doc.count(cand) == 1:
                    key = cand
                    break
            if key is None or doc.count(no) != 1:
                raise Retry("clause key/number not unique")
            out["value"] = no
            out["question"] = rng.choice(Q_CLAUSE_ZH).format(key=key)
            p = para_index_of(doc, no)
            out["cite"] = f"文档第 {p} 段（{law_short}{no} 所在段）"
            out["quote"] = trim_quote(text, 60)
        else:                                        # 条号 → 内容
            quote = re.split(r"[。；]", body)[0][:38].strip("，、： ")
            if not quote or doc.count(quote) != 1:
                raise Retry("clause quote not unique")
            out["value"] = quote
            out["question"] = rng.choice(Q_CLAUSE2_ZH).format(
                law=law_short, no=no)
            p = para_index_of(doc, quote)
            out["cite"] = f"文档第 {p} 段（{no} 所在段）"
            out["quote"] = trim_quote(text, 60)
    else:
        no = next((n for n in rng.sample(
            ABSENT_CLAUSES, len(ABSENT_CLAUSES)) if doc.count(n) == 0), None)
        if no is None:
            raise Retry("no absent clause")
        head = _CLAUSE_RE.match(clauses[0][0])
        tail = _CLAUSE_RE.match(clauses[-1][0])
        out["question"] = rng.choice(Q_CLAUSE_NEG_ZH).format(no=no)
        out["absent"] = no
        out["evidence"] = (
            f"选编条文未包含{no}（本选编覆盖{head.group(1) if head else ''}"
            f"至{tail.group(1) if tail else ''}所在范围的条文，可逐一核对）。")
    return out


def _fam_code_needle(pools, tok, rng, lang, kind, budget, deep, usage):
    budget = min(budget - 30, 3440 if not deep else 32600)
    lines: list[str] = []
    spans = []                                       # (起始行, 行数, tokens)
    used = 0
    while used < budget:
        c, text = pools.pop(["devign"])
        usage.append((c, text[:60]))
        # +2/函数 ≈ 函数间 "\n\n" 分隔 token（函数内部换行已在 tok.n 内）
        ft = tok.n(text) + 2
        if used + ft <= budget:
            fl = text.split("\n")
            spans.append((len(lines), len(fl), ft))
            lines.extend(fl)
            lines.append("")
            used += ft
        else:                                        # 末函数按行截断
            room = budget - used
            fl = text.split("\n")
            keep, k = [], 0
            for ln in fl:
                lt = tok.n(ln)
                if k + lt > room:
                    break
                keep.append(ln)
                k += lt
            if len(keep) >= 5:
                spans.append((len(lines), len(keep), k))
                lines.extend(keep)
                lines.append("")
                used += k
            break
    assert spans and used >= budget * 0.6, "code backbone underfill"
    total = sum(s[2] for s in spans)
    d = rng.uniform(0.38, 0.82)
    cum, chosen = 0, None
    for si, (start, nlines, ft) in enumerate(spans):
        if (cum + ft / 2) / total >= d:
            chosen = si
            break
        cum += ft
    if chosen is None:
        chosen = len(spans) - 1
    marker = rng.choice(S6_MARKERS)
    needle_line, value = code_needle(rng, marker)
    start, nlines, _ = spans[chosen]
    at = start + max(1, int(nlines * rng.uniform(0.3, 0.7)))
    lines.insert(at, needle_line)
    doc = "\n".join(lines)
    out = {"doc": doc}
    if kind == "hit":
        out["value"] = value
        out["question"] = rng.choice(Q_CODE_EN).format(
            marker=marker, desc=S6_DESC_EN[marker])
        n = line_index_of(doc, value)
        out["cite"] = f"document line {n} ({marker} marker line)"
        out["quote"] = trim_quote(needle_line)
    else:
        other = [m for m in S6_MARKERS if m != marker]
        absent = rng.choice(other)
        out["question"] = rng.choice(Q_CODE_NEG_EN).format(marker=absent)
        out["absent"] = absent
        n = line_index_of(doc, value)
        out["evidence"] = (f"the listing carries only the {marker} marker "
                           f"(document line {n}); no {absent} marker line "
                           f"exists in the text.")
    return out


def _fam_wiki_fact(pools, tok, rng, lang, kind, budget, deep, usage):
    corpora = ["enwiki"] if lang == "en" else ["zhwiki"]
    paras = build_backbone(pools, corpora, budget - 60, tok, usage)
    variant = rng.choice(("note", "inline", "foot"))
    code, batch = rand_code(rng), rand_batch(rng)
    date = rand_date(rng)
    ins = None
    if variant == "note":
        needle = (f"[归档附注 {date}] 本条目存档编号 {code}；校对批次 "
                  f"{batch}。" if lang == "zh" else
                  f"[Archive note {date}] Archive code {code}; proofing "
                  f"batch {batch}.")
    elif variant == "foot":
        needle = (f"注：本段资料登记的批次号为 {batch}。" if lang == "zh"
                  else f"Note: the registration batch for this section is "
                       f"{batch}.")
    else:
        needle = None                                # 句内插入，见下
    if needle is not None:
        paras = insert_at_depth(paras, needle, tok, rng)
        doc = doc_from_paras(paras)
    else:
        total = para_tokens(paras)
        cum, at = 0, None
        for i, (_, pt) in enumerate(paras):
            if (cum + pt / 2) / total >= rng.uniform(0.38, 0.82):
                at = i
                break
            cum += pt
        if at is None:
            at = len(paras) // 2
        ptext = paras[at][0]
        if lang == "zh":
            sents = [s for s in re.split(r"(?<=[。！？])", ptext) if s]
            ins = f"（本条目修订核对所用底稿编号为 {code}。）"
            if len(sents) < 2:
                raise Retry("inline paragraph too short")
            ptext2 = "".join(sents[: len(sents) // 2]) + ins \
                + "".join(sents[len(sents) // 2:])
        else:
            sents = re.split(r"(?<=[.!?]) ", ptext)
            ins = f"(The master draft code used for this article's " \
                  f"revision check is {code}.)"
            if len(sents) < 2:
                raise Retry("inline paragraph too short")
            k = len(sents) // 2
            ptext2 = " ".join(sents[:k] + [ins] + sents[k:])
        paras[at] = (ptext2, tok.n(ptext2))
        doc = doc_from_paras(paras)
    out = {"doc": doc}
    if kind == "hit":
        if variant == "note":
            value = code if rng.random() < 0.7 else batch
            out["question"] = (
                rng.choice(Q_WIKI_NOTE_ZH if value == code
                           else Q_WIKI_BATCH_ZH) if lang == "zh"
                else rng.choice(Q_WIKI_NOTE_EN if value == code
                                else Q_WIKI_BATCH_EN))
            p = para_index_of(doc, value)
            out["cite"] = (f"文档第 {p} 段（归档附注）" if lang == "zh"
                           else f"paragraph {p} of the document "
                                f"(archive note)")
        elif variant == "inline":
            value = code
            out["question"] = rng.choice(
                Q_WIKI_INLINE_ZH if lang == "zh" else Q_WIKI_INLINE_EN)
            p = para_index_of(doc, value)
            out["cite"] = (f"文档第 {p} 段（正文句中）" if lang == "zh"
                           else f"paragraph {p} of the document "
                                f"(mid-paragraph sentence)")
        else:
            value = batch
            out["question"] = rng.choice(
                Q_WIKI_FOOT_ZH if lang == "zh" else Q_WIKI_FOOT_EN)
            p = para_index_of(doc, value)
            out["cite"] = (f"文档第 {p} 段（段末注释）" if lang == "zh"
                           else f"paragraph {p} of the document "
                                f"(end-of-paragraph note)")
        out["value"] = value
        out["quote"] = trim_quote(
            needle if needle is not None else ins)
    else:
        absent = {"note": "复核员", "inline": "交接登记号",
                  "foot": "校对员代号"}[variant] if lang == "zh" else \
            {"note": "reviewer code", "inline": "handover log number",
             "foot": "proofreader id"}[variant]
        out["question"] = (Q_WIKI_NEG_ZH[variant] if lang == "zh"
                           else Q_WIKI_NEG_EN[variant])
        ev_zh = {"note": "归档附注仅含存档编号与校对批次两项信息",
                 "inline": "正文只提到修订核对的底稿编号",
                 "foot": "段末注释只登记了批次号"}[variant]
        ev_en = {"note": "the archive note records only an archive code and "
                         "a proofing batch",
                 "inline": "the text mentions only the master draft code "
                           "for the revision check",
                 "foot": "the in-text note gives only a registration "
                         "batch"}[variant]
        out["absent"] = absent
        out["evidence"] = (f"{ev_zh}，全文未出现“{absent}”。"
                           if lang == "zh" else
                           f"{ev_en}; no {absent} appears anywhere in the "
                           f"text.")
    return out


def _fam_spec_block(pools, tok, rng, lang, kind, budget, deep, usage):
    corpora = ["enwiki"] if lang == "en" else ["zhwiki"]
    paras = build_backbone(pools, corpora, budget - 90, tok, usage)
    block, vers, blds = spec_needle(rng, lang)
    paras = insert_at_depth(paras, block, tok, rng)
    doc = doc_from_paras(paras)
    out = {"doc": doc}
    if kind == "hit":
        t = rng.randrange(3)
        value = blds[t]
        out["value"] = value
        out["question"] = rng.choice(
            Q_SPEC_ZH if lang == "zh" else Q_SPEC_EN).format(ver=vers[t])
        p = para_index_of(doc, value)
        out["cite"] = (f"文档第 {p} 段（版本记录块）第 {t + 2} 行"
                       if lang == "zh" else
                       f"paragraph {p} of the document (version-record "
                       f"block), line {t + 2}")
        out["quote"] = trim_quote(block.split("\n")[t + 1])
    else:
        av = next((v for v in rng.sample(ABSENT_VERS, len(ABSENT_VERS))
                   if doc.count(v) == 0), None)
        if av is None:
            raise Retry("no absent version")
        out["question"] = rng.choice(
            Q_SPEC_NEG_ZH if lang == "zh" else Q_SPEC_NEG_EN).format(
                ver=av[1:])
        out["absent"] = av
        out["evidence"] = (
            f"版本记录块仅列出 v{vers[0]} / v{vers[1]} / v{vers[2]} 三个"
            f"版本，全文未出现 {av}。"
            if lang == "zh" else
            f"the version-record block lists only v{vers[0]} / v{vers[1]} "
            f"/ v{vers[2]}; {av} does not appear in the text.")
    return out


BUILDERS = {"log-ip": _fam_log_ip, "credential": _fam_credential,
            "cve-digest": _fam_cve_digest, "cwe-lookup": _fam_cwe_lookup,
            "clause-lookup": _fam_clause_lookup,
            "code-needle": _fam_code_needle, "wiki-fact": _fam_wiki_fact,
            "spec-block": _fam_spec_block}


# ============================================================== 行装配 ====
def pick_budget(rng, deep, buckets, bi) -> int:
    if deep:
        b = buckets[bi[0] % len(buckets)]
        bi[0] += 1
        return int(b * rng.uniform(0.99, 1.0))
    r = rng.random()
    if r < 0.25:
        return int(rng.uniform(1050, 1600))
    if r < 0.60:
        return int(rng.uniform(1600, 2600))
    return int(rng.uniform(2600, 3400))


def build_row(family, lang, kind, pack, pools, tok, rng, budget, deep,
              rid, task, retry_stats) -> dict:
    last = None
    for _ in range(15):
        usage: list = []
        try:
            r = BUILDERS[family](pools, tok, rng, lang, kind, budget,
                                 deep, usage)
            user = make_user(lang, family, r["question"], r["doc"], rng)
            if kind == "hit":
                assert r.get("quote") in r["doc"], "quote not in doc"
                assistant = hit_reply(lang, r["value"], r["cite"],
                                      r["quote"], pack, rng)
            else:
                assistant = miss_reply(lang, r["evidence"], r["absent"],
                                       pack, rng)
            check_common(None, lang, r["doc"], kind, r.get("value"),
                         r.get("absent"), tok, pack, user, assistant, deep)
            sample = build_sample(rid, task, pack, lang, user, assistant)
            return {"sample": sample, "family": family, "lang": lang,
                    "kind": kind, "pack": pack, "value": r.get("value"),
                    "absent": r.get("absent"),
                    "depth": depth_of(r["doc"], r["value"], tok)
                    if kind == "hit" else None,
                    "doc_tokens": tok.n(r["doc"]), "usage": usage}
        except (Retry, AssertionError, RuntimeError, ValueError, IndexError,
                KeyError, StopIteration) as e:
            last = e
            k = f"{family}:{lang}:{kind}"
            retry_stats[k] = retry_stats.get(k, 0) + 1
    raise RuntimeError(f"row build failed {family}/{lang}/{kind}: {last}")


def load_existing_keys() -> set:
    """v0/v0x/m1/m25-staging(t1,t9) 全量规范化 (user,assistant) 键。"""
    keys = set()

    def add_file(p: Path):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                j = json.loads(line)
                msgs = j["messages"]
                keys.add(normalize(msgs[1]["content"] + "\x00"
                                   + msgs[2]["content"]))

    for d in (ROOT / "data" / "sft" / "v0", ROOT / "data" / "sft" / "v0x"):
        for f in sorted(d.glob("*.jsonl")):
            add_file(f)
    for name in ("t1_injection", "t9_phishing"):
        add_file(ROOT / "data" / "sft" / "m2.5-staging" / f"{name}.jsonl")
    add_file(ROOT / "data" / "sft" / "m1" / "train.jsonl")
    return keys


def sweep_contamination(rows: list, base: dict) -> list:
    """产物级匹配器复扫（单元级预筛后的双保险）。返回命中行下标。"""
    hits = []
    for i, r in enumerate(rows):
        s = r["sample"]
        doc = s["messages"][1]["content"] + "\n" \
            + s["messages"][2]["content"]
        if doc_contaminated(doc, base):
            hits.append(i)
    return hits


def dist(values):
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: str(kv[0])))


# ==================================================================== main ==
def main() -> int:
    rng = random.Random(RNG_SEED)
    print("[1/6] matcher baseline (4 probe versions + 3 heldout versions)")
    base = load_baseline()
    print(f"      probes={len(base['probes'])}")
    tok = Tok()
    print("[2/6] corpus pools (reservoir sampling + unit-level screening)")
    pools = Pools(tok, base, rng)
    retry_stats: dict = {}

    def emit(quota, deep, prefix):
        rows = []
        buckets = list(DEEP_BUCKETS) if deep else None
        if deep:
            rng.shuffle(buckets)
        bi = [0]
        rid_n = 0
        for family in quota:
            for lang in ("zh", "en"):
                if lang not in quota[family]:
                    continue
                nh, nn = quota[family][lang]
                for kind, count in (("hit", nh), ("hardneg", nn)):
                    for i in range(count):
                        rid_n += 1
                        budget = pick_budget(rng, deep, buckets, bi)
                        pack = PACK_CYCLE[i % len(PACK_CYCLE)]
                        task = f"T13-retrieval:{family}:{kind}"
                        rows.append(build_row(
                            family, lang, kind, pack, pools, tok, rng,
                            budget, deep, f"{prefix}-{rid_n:04d}", task,
                            retry_stats))
        return rows

    print("[3/6] main set (1,500 rows)")
    rows_main = emit(MAIN_QUOTA, False, "sft-m25-T13")
    print("[4/6] longctx set (200 rows, 8k-32k)")
    rows_deep = emit(DEEP_QUOTA, True, "sft-m25-T13L")

    # ---- 全局断言：行数 / 配比 / 唯一性 ----
    assert len(rows_main) == N_MAIN and len(rows_deep) == N_DEEP
    for rows, quota in ((rows_main, MAIN_QUOTA), (rows_deep, DEEP_QUOTA)):
        exp = {"zh": 0, "en": 0, "sec": 0, "hardneg": 0}
        for family, langs in quota.items():
            for lang, (nh, nn) in langs.items():
                exp[lang] += nh + nn
                exp["hardneg"] += nn
                if family in SEC_FAMILIES:
                    exp["sec"] += nh + nn
        for family in quota:
            for lang in ("zh", "en"):
                if lang not in quota[family]:
                    continue
                nh, nn = quota[family][lang]
                got_h = sum(1 for r in rows if r["family"] == family
                            and r["lang"] == lang and r["kind"] == "hit")
                got_n = sum(1 for r in rows if r["family"] == family
                            and r["lang"] == lang
                            and r["kind"] == "hardneg")
                assert (got_h, got_n) == (nh, nn), \
                    f"quota drift {family}/{lang}: {got_h},{got_n}"
        langs = dist(r["lang"] for r in rows)
        assert langs == {"zh": exp["zh"], "en": exp["en"]}, \
            f"lang mix {langs} != {exp}"
        sec = sum(1 for r in rows if r["family"] in SEC_FAMILIES)
        assert sec == exp["sec"], f"sec mix {sec} != {exp['sec']}"
        neg = sum(1 for r in rows if r["kind"] == "hardneg")
        assert neg == exp["hardneg"], f"hardneg {neg} != {exp['hardneg']}"
        for family in {r["family"] for r in rows}:
            packs = {r["pack"] for r in rows if r["family"] == family}
            assert packs == {"conservative", "default", "professional"}, \
                f"pack gradient missing {family}: {packs}"
        ids = [r["sample"]["id"] for r in rows]
        assert len(set(ids)) == len(ids), "duplicate ids"
        pu = [(r["pack"], r["sample"]["messages"][1]["content"])
              for r in rows]
        assert len(set(pu)) == len(pu), "(pack,user) duplicate"
    assert not ({r["sample"]["id"] for r in rows_main}
                & {r["sample"]["id"] for r in rows_deep}), "cross-set id"
    all_norm = [normalize(r["sample"]["messages"][1]["content"] + "\x00"
                          + r["sample"]["messages"][2]["content"])
                for r in rows_main + rows_deep]
    assert len(set(all_norm)) == len(all_norm), "self duplicate"

    print("[5/6] dedup vs v0/v0x/m1/m25-staging + contamination sweep")
    existing = load_existing_keys()
    for k in all_norm:
        assert k not in existing, "duplicate vs existing corpora"
    flagged = sweep_contamination(rows_main + rows_deep, base)
    assert not flagged, f"contamination {len(flagged)} rows: {flagged[:5]}"

    print("[6/6] writing products")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    for name, rows in (("t13_retrieval", rows_main),
                       ("t13_retrieval_longctx", rows_deep)):
        with open(OUT_DIR / f"{name}.jsonl", "w", encoding="utf-8",
                  newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r["sample"], ensure_ascii=False) + "\n")

    def hist(values, edges):
        h = [0] * len(edges)
        for v in values:
            for i, e in enumerate(edges):
                if v < e:
                    h[i] += 1
                    break
            else:
                h[-1] += 1
        return h

    depths = [r["depth"] for r in rows_main + rows_deep
              if r["depth"] is not None]
    stats = {
        "seed": RNG_SEED,
        "files": {"t13_retrieval": len(rows_main),
                  "t13_retrieval_longctx": len(rows_deep)},
        "mix": {
            "main": {"lang": dist(r["lang"] for r in rows_main),
                     "pack": dist(r["pack"] for r in rows_main),
                     "kind": dist(r["kind"] for r in rows_main),
                     "sec_gen": {"sec": sum(1 for r in rows_main
                                            if r["family"] in SEC_FAMILIES),
                                 "gen": sum(1 for r in rows_main
                                            if r["family"] not in
                                            SEC_FAMILIES)},
                     "family": dist(r["family"] for r in rows_main)},
            "longctx": {"lang": dist(r["lang"] for r in rows_deep),
                        "pack": dist(r["pack"] for r in rows_deep),
                        "kind": dist(r["kind"] for r in rows_deep),
                        "family": dist(r["family"] for r in rows_deep)},
        },
        "depth_histogram_hit_rows": {
            "edges": [0.35, 0.4, 0.5, 0.6, 0.7, 0.8, 0.91],
            "counts": hist(depths, [0.35, 0.4, 0.5, 0.6, 0.7, 0.8, 0.91])},
        "depth_min_max": [round(min(depths), 4), round(max(depths), 4)],
        "doc_tokens_main": {
            "edges": [1500, 2000, 2500, 3000, 3501],
            "counts": hist([r["doc_tokens"] for r in rows_main],
                           [1500, 2000, 2500, 3000, 3501])},
        "doc_tokens_longctx": {
            "edges": [10000, 14000, 18000, 22000, 26000, 30000, 33000],
            "counts": hist([r["doc_tokens"] for r in rows_deep],
                           [10000, 14000, 18000, 22000, 26000, 30000,
                            33000])},
        "pools": pools.stats,
        "row_retries": retry_stats,
        "dedup_baseline_rows": len(existing),
        "contamination_flagged": 0,
    }
    (REPORTS / "t13-gen-stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORTS / "t13-sources.json").write_text(
        json.dumps({r["sample"]["id"]: r["usage"]
                    for r in rows_main + rows_deep}, ensure_ascii=False,
                   indent=1), encoding="utf-8")

    readme = OUT_DIR / "README.md"
    T13_MARK = ("<!-- T13 SECTION BEGIN -->", "<!-- T13 SECTION END -->")
    section = T13_MARK[0] + "\n\n## t13 长文档检索种子（2026-09-29，"
    section += "needle 深位精确检索 SFT）\n\n"
    section += "生成器：`scripts/gen_t13_retrieval.py`（seed=20260930 确定性），"
    section += "复检：`scripts/check_t13.py`。诊断背景：M1.6-32k 的 needle "
    section += "深位检索未愈（6/12 vs base 12/12）——wiki 叙事 CPT 不训练"
    section += "深位精确检索，本行族为检索式 SFT 正解备料。\n\n"
    section += "| 文件 | 行 | 上下文 | 行定义 | 形态 |\n|---|---|---|---|---|\n"
    section += "| t13_retrieval.jsonl | 1,500 | 1,000-3,500 tok | "
    section += "task_single | 8 族（log-ip/credential/cve-digest/cwe-lookup/"
    section += "clause-lookup/code-needle/wiki-fact/spec-block）；hit 1,275 + "
    section += "hard-negative 225（答“文中未出现”）；zh:en=600:900；sec:gen=60:40；"
    section += "埋点相对深度 0.30-0.90；主集全行 ≤4096 tok（cutoff 4096 包络）|\n"
    section += "| t13_retrieval_longctx.jsonl | 200 | 8k-32k tok | "
    section += "task_single（暂存） | 同形态；**独立文件即 longctx 标记**——"
    section += "M2.5 维持 cutoff 4096 时不用，若提高 cutoff 再并入（组装器按"
    section += "文件名分流） |\n\n"
    section += "骨架 100% clean 语料层（enwiki/zhwiki/zhwiki_sec/sans-isc/"
    section += "debian-dsa/cve/cwe/t6_devign/法规条文），单元级 8-gram 匹配器"
    section += " v3 预筛（探针四版本+留出三版本）+ 产物级复扫零命中；GDPR 实测"
    section += "与隐私探针系统性同文已弃用。与 v0/v0x/m1/t1/t9 零同文（断言）。\n\n"
    section += T13_MARK[1] + "\n"
    old = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if T13_MARK[0] in old:
        pre = old.split(T13_MARK[0])[0]
        post = old.split(T13_MARK[1])[1] if T13_MARK[1] in old else "\n"
        old = pre.rstrip("\n") + "\n\n" + section.rstrip("\n") + post
    else:
        old = old.rstrip("\n") + "\n\n" + section
    readme.write_text(old, encoding="utf-8")

    print(json.dumps({"verdict": "PASS", "rows": stats["files"],
                      "lang_main": stats["mix"]["main"]["lang"],
                      "hardneg_main": stats["mix"]["main"]["kind"],
                      "depth_min_max": stats["depth_min_max"],
                      "retries": sum(retry_stats.values())},
                     ensure_ascii=False, indent=2))
    print(f"-> {OUT_DIR / 't13_retrieval.jsonl'}")
    print(f"-> {OUT_DIR / 't13_retrieval_longctx.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
