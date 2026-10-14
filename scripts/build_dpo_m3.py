r"""M3 偏好数据集 v0 加工(build_dpo_m3)——docs/01 §3.3 政策条件化偏好核心。

四类偏好对 → data/dpo/m3/train.jsonl(LLaMA-Factory sharegpt ranking 格式):

  A 政策条件化对(主力,差异化设计,占比 ≥30%):
    v0/policy_pairs + v0x/policy_expansion(T5-policy)+ v0x/t4_grounding
    按 (task, lang, query) 分组,同组异包响应构造**双向对称**有序对:
    system=锚包政策区,chosen=锚包响应,rejected=其余包响应(该响应在锚包
    语境下即错判——教"响应必须匹配激活包")。
  B 储备直通对(稀释盘):data/sft/dpo-reserve/ 四源清洗入列——
    ①排除哈希复检(逐源 replay 装配器逻辑,见下);②chosen==rejected/
    空值剔除;③精确+8-gram 签名近重去重;④按类 A 体量定容采样
    (保 policy 占比 ≥30%)。
  B2 储备衍生拒绝对:bt330 行(上游 chosen=None,仅 rejected 材料)以
    政策化拒绝模板合成 chosen(标记独立统计;上限 6,000)。
  C 拒绝质量对(合成):同查询同包,chosen=带理由+替代路径的拒绝,
    rejected=生硬拒绝(双侧同带 VERDICT——隔离"质量"维度,不混淆
    "格式有无"维度)。
  D 校准偏好对(合成):chosen=诚实澄清弃权(T11 三轴/语境模糊种子),
    rejected=编造式过度自信(双侧同带 VERDICT;rejected 高置信+answer,
    chosen 低置信+insufficient-context)。

排除纪律(父会话 2026-09-26 指令):
  - T5-hardfloor / T5-direction 不进偏好对(三包同拒,无偏好结构);
  - T5-attack(attack_dict)同理不进:实测 1,860/1,860 全拒且三响应除
    开头子句与 VERDICT 外逐字相同(模板级差异非偏好结构);
  - 统一兜底=实质差异过滤:剥离 VERDICT 行后 difflib 相似度 ≥0.88 的
    响应对不入(实测定标:attack_dict 模板对全滤,政策/T4 实质对全保)。

排除哈希复检(红线/污染"复用现有索引哈希"):
  reports/sft-exclusion-hashes.json(sha256 = checker 枚举序文档镜像)。
  逐源 replay:dpo-reserve id → 原始 raw 行 → _dt_* 镜像哈希 ∈ 排除集?
  上游装配已过滤(hh/cv/pku/bt-30k),预期 0 命中;**bt330 上游未过
  滤(330k 文件无 excl 检查)——本脚本补上**,被排除行直接剔除。

LF schema(源码确认,LLaMA-Factory 0.9.6.dev0):
  ranking 数据经 SharegptDatasetConverter:conversations=[system,human]
  + chosen/rejected={"from":"gpt","value":...};stage dpo 内部走
  stage="rm" + ranking=true(loader.py:178 约束);chosen/rejected 列名
  必须在 dataset_info columns 显式声明(converter.py:191 无 None 守卫)。
  注册 sec_dpo_m3(ranking=true,**不默认启用**——无 config 引用)。

纪律:GPU 不碰;评估集/探针路径零引用(源码级断言,沿 test_gen_sft_v0
模式);确定性 seed;PII/武器化内容 rejected 侧亦受排除哈希约束。

用法:python scripts/build_dpo_m3.py [--small] [--no-register]
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import lzma
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from assemble_sft_m2 import (  # noqa: E402  排除镜像/读取助手单一事实源
    REFUSAL_REPLY, _dt_bt, _dt_cv, _dt_hh, _dt_pku, _gz_jsonl_rows,
    _hh_turns, _jsonl_rows, _sha)
from check_sft_contamination import ngrams, normalize  # noqa: E402
from gen_sft_v0 import POLICY_SYSTEM, verdict_line  # noqa: E402  v0 契约

SEED = 20260928
# 实质差异阈值(剥 VERDICT 后 difflib 相似度 ≥ 此值 = 无偏好结构)。
# 实测分布定标(2026-09-26,reports 侧测量):attack_dict 全对
# [0.883, 0.916](模板级差异)→ 0.88 全滤;T5-policy 全对 ≤0.582、
# T4-grounding 全对 ≤0.717(实质差异)→ 0.88 全保;分隔带干净。
SUBST_RATIO = 0.88
BT330_CAP = 6000            # B2 衍生对上限(模板 chosen 重复度护栏)
POLICY_SHARE_MIN = 0.30     # 类 A 占比下限(父指令:不被通用对稀释)
PACK_ORDER = ("conservative", "default", "professional")
RAW = ROOT / "data" / "corpora" / "raw" / "m2"
V0_DIR = ROOT / "data" / "sft" / "v0"
V0X_DIR = ROOT / "data" / "sft" / "v0x"
RESERVE_DIR = ROOT / "data" / "sft" / "dpo-reserve"
EXCL_JSON = ROOT / "reports" / "sft-exclusion-hashes.json"
OUT_DIR = ROOT / "data" / "dpo" / "m3"
LF_DIR = ROOT / "data" / "lf"
DATASET_INFO = LF_DIR / "dataset_info.json"

# A 类语料(政策族):hardfloor/direction/attack 按排除纪律不入
POLICY_FILES = [
    ("T5-policy", V0_DIR / "policy_pairs.jsonl"),
    ("T5-policy", V0X_DIR / "policy_expansion.jsonl"),
    ("T4-grounding", V0X_DIR / "t4_grounding.jsonl"),
]
EXCLUDED_TASK_PREFIXES = ("T5-hardfloor", "T5-direction", "T5-attack")

# C 类:生硬拒绝(与政策化拒绝的"理由+替代路径"形成质量对照)
BARE_REFUSAL = {
    "en": "I can't help with this.",
    "zh": "这个我帮不了。",
}

# D 类:编造式过度自信(按 T11 三轴;内容=无语境即行动/编造细节,
# 不含任何操作性武器化内容)
OVERCONFIDENT = {
    "missing-auth": {
        "en": ("Sure, no problem — I'll start the security test on your "
               "company's systems right away and give you a full report."),
        "zh": "好的没问题,我现在就开始对你们公司系统做安全测试,稍后给你完整报告。"},
    "missing-object": {
        "en": ("On it — I'll check the main server for issues and list "
               "everything I find."),
        "zh": "收到——我这就检查主服务器的问题,把发现的所有问题列出来。"},
    "missing-purpose": {
        "en": ("Done — I'll pull the full dataset export and include every "
               "field so nothing is missed."),
        "zh": "好的——我这就把全量数据导出,所有字段都带上,保证不漏。"},
    "generic": {
        "en": "Absolutely, I can do that — consider it handled.",
        "zh": "完全可以,交给我,马上处理。"},
}
# D 类增补:语境模糊种子(全部拒绝+澄清的正确侧已有;rejected=越权直行)
PROCEED_ANYWAY = {
    "en": "Understood — proceeding with the full action now.",
    "zh": "明白,我现在直接开始执行。",
}


# ============================================================ 基础构件 ===
def strip_verdict(text: str) -> str:
    """剥离末行 VERDICT(实质差异比较排除结构行自身差异)。"""
    if "\nVERDICT:" in text:
        return text.rsplit("\nVERDICT:", 1)[0]
    if text.startswith("VERDICT:"):
        return ""
    return text


def substantive_diff(a: str, b: str,
                     threshold: float = SUBST_RATIO) -> bool:
    """两响应是否存在实质差异(剥 VERDICT 后相似度 < threshold)。"""
    sa, sb = strip_verdict(a).strip(), strip_verdict(b).strip()
    if not sa and not sb:
        return False
    if sa == sb:
        return False
    return difflib.SequenceMatcher(None, sa, sb).ratio() < threshold


def _action_of(text: str) -> str | None:
    """从 VERDICT 行取 action(无 VERDICT 返回 None)。"""
    if '"action"' not in text:
        return None
    try:
        seg = text.rsplit('"action":', 1)[1]
        return seg.split('"')[1]
    except IndexError:
        return None


def load_pack_groups(paths, excluded_prefixes=EXCLUDED_TASK_PREFIXES):
    """按 (task, lang, user_query) 分组 → {key: {pack: assistant}}。

    单轮消息流([system, user, assistant])才入组;多轮(T10-smuggle 等)
    不在 POLICY_FILES 内,防御性跳过。
    """
    groups = defaultdict(dict)
    n_rows = n_skip = 0
    for _, path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                j = json.loads(line)
                n_rows += 1
                if j["task"].startswith(excluded_prefixes):
                    n_skip += 1
                    continue
                msgs = j["messages"]
                if [m["role"] for m in msgs] != ["system", "user",
                                                 "assistant"]:
                    n_skip += 1
                    continue
                user = msgs[1]["content"]
                groups[(j["task"], j["lang"], user)][j["pack"]] = \
                    msgs[2]["content"]
    return dict(groups), n_rows, n_skip


def to_lf(dpo_class: str, sid: str, pack: str, lang: str, system: str,
          user: str, chosen: str, rejected: str, **meta) -> dict:
    """LLaMA-Factory sharegpt ranking 行(经 converter 源码确认)。"""
    assert chosen.strip() and rejected.strip(), f"{sid} 空响应"
    assert chosen != rejected, f"{sid} chosen==rejected(无效偏好对)"
    row = {"dpo_class": dpo_class, "id": sid, "pack": pack, "lang": lang,
           "conversations": [
               {"from": "system", "value": system},
               {"from": "human", "value": user}],
           "chosen": {"from": "gpt", "value": chosen},
           "rejected": {"from": "gpt", "value": rejected}}
    row.update(meta)
    return row


# ================================================== A 类:政策条件化对 ===
def gen_policy_pairs(groups: dict) -> list[dict]:
    """同组异包双向对称有序对(实质差异过滤兜底)。"""
    out = []
    for key in sorted(groups):
        task, lang, user = key
        by_pack = groups[key]
        for anchor in PACK_ORDER:
            if anchor not in by_pack:
                continue
            system = POLICY_SYSTEM[anchor]["zh" if lang == "zh" else "en"]
            for other in PACK_ORDER:
                if other == anchor or other not in by_pack:
                    continue
                if not substantive_diff(by_pack[anchor], by_pack[other]):
                    continue
                out.append(to_lf(
                    "policy", f"dpoA-{len(out):06d}", anchor, lang,
                    system, user, by_pack[anchor], by_pack[other],
                    src_task=task, rejected_pack=other))
    return out


# ================================================= C 类:拒绝质量对 ===
def gen_refusal_quality(groups: dict, n_target: int = 300,
                        seed: int = SEED) -> list[dict]:
    """同查询同包:chosen=政策化拒绝(理由+替代),rejected=生硬拒绝。"""
    rng = random.Random(seed)
    cand = []
    for key in sorted(groups):
        task, lang, user = key
        resp = groups[key].get("conservative")
        if resp and _action_of(resp) == "refuse":
            cand.append((key, resp))
    rng.shuffle(cand)
    out = []
    for (task, lang, user), resp in cand[:n_target]:
        rejected = (BARE_REFUSAL["zh" if lang == "zh" else "en"] + "\n"
                    + verdict_line("refuse", "refuse", 0.9, [],
                                   "conservative"))
        out.append(to_lf(
            "refusal_quality", f"dpoC-{len(out):06d}", "conservative",
            lang, POLICY_SYSTEM["conservative"][
                "zh" if lang == "zh" else "en"],
            user, resp, rejected, src_task=task))
    return out


# =================================================== D 类:校准偏好对 ===
def gen_calibration(v0_dir: Path = V0_DIR, groups: dict | None = None,
                    seed: int = SEED) -> list[dict]:
    """诚实澄清弃权 vs 编造式过度自信(双侧同 VERDICT 隔离格式维度)。"""
    out = []
    # D1:T11 三轴(每行 × 2 过度自信变体:轴模板 + generic 模板)
    for line in open(v0_dir / "calibration.jsonl", encoding="utf-8"):
        if not line.strip():
            continue
        j = json.loads(line)
        msgs = j["messages"]
        user, chosen = msgs[1]["content"], msgs[2]["content"]
        lang = j["lang"]
        axis = j["task"].split(":", 1)[-1] if ":" in j["task"] else "generic"
        pack = j.get("pack", "default")
        system = POLICY_SYSTEM[pack]["zh" if lang == "zh" else "en"]
        tmpl = [OVERCONFIDENT.get(axis, OVERCONFIDENT["generic"]),
                OVERCONFIDENT["generic"]]
        for k, t in enumerate(tmpl):
            rejected = t[lang] + "\n" + verdict_line(
                "answer", None, 0.93, [], pack)
            out.append(to_lf(
                "calibration", f"dpoD-{len(out):06d}", pack, lang, system,
                user, chosen, rejected, src_task=j["task"], variant=k))
    # D2:语境模糊种子(全组拒绝+澄清 vs 越权直行)
    if groups:
        for key in sorted(groups):
            task, lang, user = key
            sid_seg = task.split(":", 1)[-1] if ":" in task else ""
            if not any(k in sid_seg for k in ("vague", "ambig")):
                continue
            for pack in PACK_ORDER:
                resp = groups[key].get(pack)
                if not resp or _action_of(resp) != "refuse":
                    continue
                system = POLICY_SYSTEM[pack][
                    "zh" if lang == "zh" else "en"]
                rejected = (PROCEED_ANYWAY[lang] + "\n" + verdict_line(
                    "answer", "allow", 0.9, [], pack))
                out.append(to_lf(
                    "calibration", f"dpoD-{len(out):06d}", pack, lang,
                    system, user, resp, rejected, src_task=task))
    return out


# ============================================ B 类:储备直通 + 复检 ===
def load_excl(excl_path: Path = EXCL_JSON) -> dict[str, set]:
    d = json.loads(excl_path.read_text(encoding="utf-8"))
    return {k: set(v["sha256"]) for k, v in d.items() if k != "_meta"}


def replay_exclusions(rows: list[dict], excl: dict, raw: Path = RAW):
    """逐源排除哈希复检:返回 (保留行, 统计)。

    id → 原始 raw 行 → _dt_* 镜像哈希 ∈ 排除集 → 剔除。
    hh/cv/pku/bt-30k 上游已过滤(预期 0 命中,统计如实报告);
    bt330 上游未检(330k 无 excl)——此处补检,命中即剔。
    """
    stats = Counter()
    sources = {r["source"] for r in rows}
    kept = []

    # ---- 惰性加载:仅载入实际出现的源对应 raw 文件 ----
    # id 语义(镜像上游装配器):hh=行号 / cv={harm|help}+行号 /
    # pku=目录名(可含连字符)+行号 / bt-30k=prompt 分组 / bt330=n330 计数
    hh_rows = None
    if "hh-rlhf" in sources:
        hh_rows = list(_gz_jsonl_rows(
            raw / "hh-rlhf" / "harmless-base" / "train.jsonl.gz"))
    cv_maps = {}
    if "cvalues" in sources:
        for fname in ("harmless_train.json", "helpful_train.json"):
            cv_maps[fname[:4]] = json.loads(
                (raw / "cvalues" / fname).read_text(encoding="utf-8"))
    pku_maps = {}
    if "pku-saferlhf" in sources:
        for p_ in sorted((raw / "pku-saferlhf" / "data").rglob(
                "train.jsonl")):
            pku_maps[p_.parent.name] = list(_jsonl_rows(p_))
    bt30 = None
    bt330_ok = None
    if sources & {"beavertails", "beavertails-330k"}:
        # 30k:prompt 分组重建(镜像上游;排除行不入池)
        bt30 = defaultdict(lambda: {"safe": [], "unsafe": []})
        for j in _gz_jsonl_rows(raw / "beavertails" / "round0" / "30k" /
                                "train.jsonl.gz"):
            if _sha(_dt_bt(j)) in excl.get("beavertails", set()):
                continue
            p = (j.get("prompt") or "").strip()
            if p:
                bt30[p]["safe" if str(j.get("is_safe")) == "True"
                      else "unsafe"].append((j.get("response") or
                                             "").strip())
        # 330k:n330 计数复刻(镜像上游 every-15 采样)+ 补 excl 检查
        bt330_ok = {}
        n330 = 0
        with lzma.open(raw / "beavertails" / "round0" / "330k" /
                       "train.jsonl.xz", "rt", encoding="utf-8",
                       errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                j = json.loads(line)
                if not (j.get("prompt") or "").strip():
                    continue
                n330 += 1
                if n330 % 15 != 0:
                    continue
                if str(j.get("is_safe")) == "False":
                    bt330_ok[n330] = (j, _sha(_dt_bt(j)))

    for r in rows:
        src, rid = r["source"], r["id"]
        try:
            if src == "hh-rlhf":
                i = int(rid.split("-", 1)[1])
                if _sha(_dt_hh(hh_rows[i])) in excl.get(
                        "hh-rlhf-harmlessness", set()):
                    stats["hh_blocked"] += 1
                    continue
                kept.append(r)
            elif src == "cvalues":
                pre, i = rid.split("-")[1], int(rid.split("-")[2])
                if _sha(_dt_cv(cv_maps[pre][i])) in excl.get(
                        "cvalues", set()):
                    stats["cv_blocked"] += 1
                    continue
                kept.append(r)
            elif src == "pku-saferlhf":
                # 目录名可含连字符(如 Alpaca-7B):尾段=行号,其余=目录
                dir_part, idx_part = rid.split("-", 1)[1].rsplit("-", 1)
                if _sha(_dt_pku(pku_maps[dir_part][int(idx_part)])) in \
                        excl.get("pku-saferlhf", set()):
                    stats["pku_blocked"] += 1
                    continue
                kept.append(r)
            elif src == "beavertails":
                pools = (bt30 or {}).get(r["prompt"])
                if not pools or not pools["safe"] or not pools["unsafe"]:
                    stats["bt30_unmatched"] += 1
                    continue
                if (r["chosen"], r["rejected"]) != (pools["safe"][0],
                                                    pools["unsafe"][0]):
                    stats["bt30_unmatched"] += 1
                    continue
                kept.append(r)
            elif src == "beavertails-330k":
                n = int(rid.split("-")[1])
                if n not in bt330_ok:
                    stats["bt330_unmatched"] += 1
                    continue
                j, h = bt330_ok[n]
                if h in excl.get("beavertails", set()):
                    stats["bt330_blocked"] += 1   # 上游遗漏,此处补剔
                    continue
                if r["rejected"] != (j.get("response") or "").strip():
                    stats["bt330_unmatched"] += 1
                    continue
                kept.append(r)
        except (KeyError, IndexError, ValueError):
            stats["replay_error"] += 1
    return kept, stats


def _sig_grams(grams: tuple) -> tuple:
    """确定性 3-排列 minhash 签名。"""
    sig = []
    for salt in (1, 2, 3):
        sig.append(min((hashlib.md5(f"{salt}\x00{g}".encode()).hexdigest()
                        for g in grams), default=""))
    return tuple(sig)


def dedup_pairs(rows: list[dict], near_threshold: float = 0.7) -> tuple:
    """精确(规范化 prompt+chosen+rejected)+ 近重(prompt 8-gram 签名)去重。

    近重:同签名桶内 containment ≥ threshold 判重(保序留先)。
    """
    exact = set()
    buckets = defaultdict(list)   # sig -> [(idx, gram_set)]
    kept, stats = [], Counter()
    for idx, r in enumerate(rows):
        key = _sha(normalize(r["prompt"]) + "\x00"
                   + normalize(r.get("chosen") or "") + "\x00"
                   + normalize(r["rejected"]))
        if key in exact:
            stats["dup_exact"] += 1
            continue
        grams = set(ngrams(normalize(r["prompt"]), 8, 1))
        sig = _sig_grams(tuple(sorted(grams)))
        dup = False
        for _, og in buckets[sig]:
            inter = len(grams & og)
            if inter and inter / min(len(grams), len(og)) >= near_threshold:
                dup = True
                break
        if dup:
            stats["dup_near"] += 1
            continue
        exact.add(key)
        buckets[sig].append((idx, grams))
        kept.append(r)
    return kept, stats


def clean_reserve(reserve_dir: Path = RESERVE_DIR, excl: dict | None = None,
                  raw: Path = RAW, seed: int = SEED,
                  bt330_cap: int = BT330_CAP):
    """储备清洗主流程:载入 → 复检 → 剔无效 → bt330 合成 → 去重。"""
    rows = []
    for p in sorted(reserve_dir.glob("*.jsonl")):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                rows.append(json.loads(line))
    n_loaded = len(rows)
    if excl is not None:
        rows, rep = replay_exclusions(rows, excl, raw)
    else:
        rep = Counter()
    stats = Counter(loaded=n_loaded, **rep)

    direct, bt330, invalid = [], [], []
    for r in rows:
        if r["source"] == "beavertails-330k":
            (bt330 if r.get("rejected") else invalid).append(r)
        elif r.get("chosen") and r.get("rejected"):
            if r["chosen"] == r["rejected"]:
                stats["same_sides"] += 1
            else:
                direct.append(r)
        else:
            invalid.append(r)
    stats["invalid_dropped"] = len(invalid)

    # B2:bt330 合成 chosen(政策化拒绝,包轮换;上限采样)
    rng = random.Random(seed)
    rng.shuffle(bt330)
    b2 = []
    for k, r in enumerate(bt330[:bt330_cap]):
        pack = PACK_ORDER[k % 3]
        chosen = (REFUSAL_REPLY[pack]["en"] + "\n"
                  + verdict_line("refuse", "refuse", 0.95, [], pack))
        b2.append(dict(r, chosen=chosen, pack=pack, lang="en"))
    stats["bt330_capped"] = len(bt330) - min(len(bt330), bt330_cap)

    all_rows = direct + b2
    all_rows, dstats = dedup_pairs(all_rows)
    stats.update(dstats)
    return all_rows, stats


def stratified_sample(rows: list[dict], cap: int, seed: int = SEED):
    """按 source 比例分层定容采样(确定性;cap ≥ 行数时全保留)。"""
    if cap >= len(rows):
        return rows, {"cap": cap, "n": len(rows), "full": True}
    rng = random.Random(seed)
    by_src = defaultdict(list)
    for r in rows:
        by_src[r["source"]].append(r)
    quotas = {}
    base = {s: cap * len(v) // len(rows) for s, v in by_src.items()}
    rem = cap - sum(base.values())
    frac = sorted(by_src, key=lambda s: (-(cap * len(by_src[s]) / len(rows)
                                           - base[s]), s))
    for s in frac[:rem]:
        base[s] += 1
    picked = []
    for s in sorted(by_src):
        q = min(base[s], len(by_src[s]))
        picked.extend(rng.sample(by_src[s], q))
    return picked, {"cap": cap, "n": len(picked), "full": False,
                    "by_source": {s: min(base[s], len(by_src[s]))
                                  for s in sorted(by_src)}}


# ============================================================== 主流程 ===
def reserve_lang(row: dict) -> str:
    return row.get("lang") or ("zh" if row["source"] == "cvalues"
                               else "en")


def build(v0_dir: Path = V0_DIR, v0x_dir: Path = V0X_DIR,
          reserve_dir: Path = RESERVE_DIR, excl_path: Path = EXCL_JSON,
          raw: Path = RAW, seed: int = SEED, small: bool = False):
    excl = load_excl(excl_path) if excl_path.exists() else None
    paths = [("T5-policy", v0_dir / "policy_pairs.jsonl"),
             ("T5-policy", v0x_dir / "policy_expansion.jsonl"),
             ("T4-grounding", v0x_dir / "t4_grounding.jsonl")]
    groups, n_rows, n_skip = load_pack_groups(paths)
    class_a = gen_policy_pairs(groups)
    class_c = gen_refusal_quality(groups, seed=seed)
    class_d = gen_calibration(v0_dir, groups, seed=seed)

    reserve, rstats = clean_reserve(reserve_dir, excl, raw, seed)
    # 定容:保 policy 占比 ≥ POLICY_SHARE_MIN(公式推导自
    # A/(A+B+C+D) ≥ p → B ≤ A(1-p)/p - C - D;×0.97 安全边际)
    p = POLICY_SHARE_MIN
    cap = int((len(class_a) * (1 - p) / p - len(class_c) - len(class_d))
               * 0.97)
    cap = max(0, cap)
    reserve, sstats = stratified_sample(reserve, cap, seed)

    rows_b = []
    for k, r in enumerate(reserve):
        lang = reserve_lang(r)
        pack = r.get("pack", "default")
        cls = "bt330_refusal" if r["source"] == "beavertails-330k" \
            else "reserve"
        rows_b.append(to_lf(
            cls, f"dpoB-{k:06d}", pack, lang,
            POLICY_SYSTEM[pack]["zh" if lang == "zh" else "en"],
            r["prompt"], r["chosen"], r["rejected"],
            src_id=r["id"], src=r["source"]))

    all_rows = class_a + rows_b + class_c + class_d
    rng = random.Random(seed)
    rng.shuffle(all_rows)

    share = len(class_a) / len(all_rows) if all_rows else 0.0
    stats = {
        "seed": seed,
        "total": len(all_rows),
        "by_class": dict(Counter(r["dpo_class"] for r in all_rows)),
        "policy_share": round(share, 4),
        "policy_share_min": POLICY_SHARE_MIN,
        "pack_dist": dict(Counter(r["pack"] for r in all_rows)),
        "lang_dist": dict(Counter(r["lang"] for r in all_rows)),
        "reserve_source_dist": dict(Counter(
            r.get("src", "?") for r in rows_b)),
        "policy_rows_scanned": n_rows,
        "policy_rows_skipped_task": n_skip,
        "policy_groups": len(groups),
        "reserve_stats": {k: v for k, v in rstats.items() if v},
        "reserve_cap": sstats,
        "exclusion_replay": {k: v for k, v in rstats.items()
                             if k.endswith(("blocked", "unmatched",
                                            "replay_error"))},
    }
    if not small:
        assert share >= POLICY_SHARE_MIN, (
            f"policy share {share:.3f} < {POLICY_SHARE_MIN}")
    return all_rows, stats


def write_outputs(rows: list[dict], stats: dict, out_dir: Path = OUT_DIR,
                  register: bool = True):
    out_dir.mkdir(parents=True, exist_ok=True)
    train = out_dir / "train.jsonl"
    with open(train, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    # README(配比与统计;见 docstring 设计决策)
    bc = stats["by_class"]
    ld = stats["lang_dist"]
    pd_ = stats["pack_dist"]
    rs = stats["reserve_stats"]
    zh = ld.get("zh", 0)
    readme = f"""# M3 偏好数据集 v0(sec_dpo_m3)

生成:scripts/build_dpo_m3.py(seed={stats["seed"]});原料与设计见脚本
docstring。LLaMA-Factory sharegpt ranking 格式;stage dpo 内部走
stage="rm"+ranking=true;**不默认启用**(无 config 引用,dataset_info
已注册 sec_dpo_m3)。

## 配比(总 {stats["total"]:,} 对)

| 类 | 条数 | 占比 | 说明 |
|---|---|---|---|
| A 政策条件化对 | {bc.get("policy", 0):,} | {bc.get("policy", 0) / stats["total"]:.1%} | 同查询异包双向对称;差异化设计主体 |
| B 储备直通对 | {bc.get("reserve", 0):,} | {bc.get("reserve", 0) / stats["total"]:.1%} | 四源清洗(哈希复检+去重+定容) |
| B2 储备衍生拒绝对 | {bc.get("bt330_refusal", 0):,} | {bc.get("bt330_refusal", 0) / stats["total"]:.1%} | bt330 chosen=None 行以政策化拒绝合成 |
| C 拒绝质量对 | {bc.get("refusal_quality", 0):,} | {bc.get("refusal_quality", 0) / stats["total"]:.1%} | 带理由+替代 vs 生硬拒绝(双侧同 VERDICT) |
| D 校准偏好对 | {bc.get("calibration", 0):,} | {bc.get("calibration", 0) / stats["total"]:.1%} | 诚实弃权 vs 过度自信 |

**政策条件化对占比 {stats["policy_share"]:.1%}(下限 {POLICY_SHARE_MIN:.0%})**;
zh:en = {zh}:{stats["total"] - zh}({zh / stats["total"]:.0%}:{(stats["total"] - zh) / stats["total"]:.0%});
包分布 {json.dumps(pd_, ensure_ascii=False)}。

## 储备清洗统计

载入 {rs.get("loaded", 0):,} → 排除哈希复检(hh/cv/pku/bt-30k 上游已滤,
预期 0;bt330 上游未检、此处补剔:{"、".join(f"{k}={v}" for k, v in stats["exclusion_replay"].items()) or "全零"})
→ 无效剔除 {rs.get("invalid_dropped", 0)} / 同侧 {rs.get("same_sides", 0)}
→ 去重(精确 {rs.get("dup_exact", 0)} / 近重 {rs.get("dup_near", 0)})
→ 定容采样 cap={stats["reserve_cap"]["cap"]:,}。

## 设计决策(供复核)

1. **hardfloor/direction/attack_dict 不入偏好对**(父指令+实测:三包同拒
   无偏好结构;attack_dict 1,860 行全拒且响应仅模板级差异);
2. **实质差异过滤兜底**(剥 VERDICT 后相似度 ≥{SUBST_RATIO} 不入,任何源);
3. **bt330 行 chosen=None**(上游仅 rejected 材料):合成政策化拒绝 chosen
   (包轮换,上限 {BT330_CAP:,})——独立统计,可整体剔除重跑;
4. **储备定容公式** B ≤ A(1-p)/p − C − D(p={POLICY_SHARE_MIN}),保政策对
   不被稀释;
5. 储备对响应**不加 VERDICT 行**(第三方文本不编造结构声明;类 A/C/D
   双侧自带 VERDICT);
6. 排除哈希复检逐源 replay 装配器 id 语义(hh=行号/cv=文件+行号/
   pku=目录+行号/bt=prompt 分组/bt330=n330 计数)。

## 启用(stage dpo,届时另建 config)

```yaml
stage: dpo
dataset: sec_dpo_m3        # dataset_dir: data/lf(已注册)
pref_beta: 0.1
```
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    if register:
        # LF 注册(ranking=true;columns 必须显式——converter 无 None 守卫)
        info = json.loads(DATASET_INFO.read_text(encoding="utf-8"))
        info["sec_dpo_m3"] = {
            "file_name": "dpo_m3.jsonl",
            "formatting": "sharegpt",
            "ranking": True,
            "columns": {"messages": "conversations",
                        "chosen": "chosen", "rejected": "rejected"},
            "tags": {"role_tag": "from", "content_tag": "value",
                     "user_tag": "human", "assistant_tag": "gpt",
                     "system_tag": "system"},
        }
        DATASET_INFO.write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        link = LF_DIR / "dpo_m3.jsonl"
        if link.exists():
            link.unlink()
        import os
        os.link(train, link)
    return train


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--small", action="store_true",
                    help="小样本模式(跳过占比断言,测试用)")
    ap.add_argument("--no-register", action="store_true",
                    help="不注册 dataset_info/不建硬链")
    args = ap.parse_args(argv)
    rows, stats = build(small=args.small)
    train = write_outputs(rows, stats,
                          register=not args.no_register)
    print(json.dumps({k: stats[k] for k in
                      ("total", "by_class", "policy_share",
                       "lang_dist", "pack_dist")},
                     ensure_ascii=False, indent=1))
    print(f"-> {train} ({len(rows):,} 对)")


if __name__ == "__main__":
    main()
