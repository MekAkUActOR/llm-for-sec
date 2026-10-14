# -*- coding: utf-8 -*-
"""M3 DPO 混料 v2：为 reserve 类补齐 VERDICT 输出契约（CPU 数据工程，不训练）。

背景（实测，reports/c-path-topup-verdict.md）：任何目标回复若不含 VERDICT
契约，会把已学到的契约冲掉。data/lf/dpo_m3.jsonl 中 reserve 类 30,807 行
（64.2%）两侧 chosen/rejected 都没有 VERDICT——本脚本只修这一块。

设计决策（全部确定性、可复算、幂等）
------------------------------------
1. 协议类（policy / bt330_refusal / refusal_quality / calibration）已 100%
   带 VERDICT：**逐字原样保留** chosen/rejected/conversations，不重写内容。
2. reserve 类：**原文本逐字保留**，仅在其末尾追加一行 VERDICT；
   追加行由确定性规则（classify_reserve_text）渲染，键序 =
   action, verdict, confidence, findings, policy；policy = 该行 pack。
3. action/verdict 描述**文本自身立场**，不评价文本内容是否安全：
     R1  明确拒绝/无法协助            -> action=refuse,  verdict=refuse
     R2  条件化提议/待授权            -> action=propose, verdict=conditional
     R3  反问/索取更多信息            -> action=answer,  verdict=insufficient-context
     R4  提示风险/违法 + 合规建议     -> action=answer,  verdict=conditional
     R5  中性答询（兜底）             -> action=answer,  verdict=allow
   任一 cue 命中即定；优先级 R1>R2>R3>R4>R5。
4. 无法稳定判定（空文本/过短/无文字/拒绝与照做混杂）-> **丢弃并计数**。
5. reserve 占比上限 25%（按总行数），定容 = max r s.t. r <= 0.25*(P+r)
   （P=协议类行数）；按 (lang, pack) 分层、固定 seed 抽样。
6. chosen 与 rejected 的 VERDICT 必须不同：若两侧渲染结果完全相同，则按
   确定性约定把 rejected 侧 confidence 下调 TIEBREAK_DELTA（rejected 是
   未被偏好的响应）——计入报告 tiebreak 数。
7. 行序 = 源文件行序（不做 shuffle）；id 沿用源 id（源内已验证全局唯一），
   未保留的行直接不出现。源里的 provenance 字段（src_id/src 或
   src_task/rejected_pack/variant）原样保留，不伪造 src_task。

用法
----
  python scripts/build_dpo_m3_v2.py              # 构建 + 写报告
  python scripts/build_dpo_m3_v2.py --analyze    # 只统计规则分布，不写文件
  python scripts/build_dpo_m3_v2.py --check      # 构建到内存后跑自断言
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "lf" / "dpo_m3.jsonl"
OUT = ROOT / "data" / "lf" / "dpo_m3_v2.jsonl"
REPORT = ROOT / "reports" / "dpo-m3-v2-report.json"
STRICT_OUT = ROOT / "data" / "lf" / "dpo_m3_v2_strict.jsonl"
STRICT_REPORT = ROOT / "reports" / "dpo-m3-v2-strict-report.json"
Q_OUT = ROOT / "data" / "lf" / "dpo_m3_v2_q.jsonl"
Q_REPORT = ROOT / "reports" / "dpo-m3-v2-q-report.json"

SEED = 20261001
RESERVE_SHARE_MAX = 0.25
TIEBREAK_DELTA = 0.02
# 严格版"立场/信号"字段：一对偏好对只要在这些字段上不同，就认为 VERDICT
# 承载了非置信度的信息（有梯度信号）。注意 policy 必须计入——policy 类
# rejected 侧引用 rejected_pack（错误包对照）正是该类唯一的偏好信号
# （父代理裁定 2026-10-06：这是源数据设计意图，不是缺陷）。
STANCE_FIELDS = ("action", "verdict", "policy", "findings")

PROTOCOL_CLASSES = ("policy", "bt330_refusal", "refusal_quality", "calibration")
RESERVE_CLASS = "reserve"
ALL_CLASSES = PROTOCOL_CLASSES + (RESERVE_CLASS,)

# 哪些类的哪些侧缺 VERDICT、需要就地渲染（实测：reserve 两侧全缺；
# bt330_refusal 仅 rejected 侧缺——父任务给的审计表称该类 100% 合规，实测不符）。
NEEDS_RENDER = {
    "reserve": ("chosen", "rejected"),
    "bt330_refusal": ("rejected",),
}
VERBATIM_CLASSES = ("policy", "refusal_quality", "calibration")

VERDICT_KEYS = ("action", "verdict", "confidence", "findings", "policy")
ACTION_VOCAB = ("answer", "refuse", "propose")
VERDICT_VOCAB = ("allow", "conditional", "refuse", "insufficient-context")
# calibration 保留类里原协议允许 verdict=null（原样保留，不重写）
VERDICT_VOCAB_ALLOW_NULL_CLASSES = ("calibration",)
CONF_MIN, CONF_MAX = 0.05, 0.99

VERDICT_LINE_RE = re.compile(r"(?m)^VERDICT:\s*(\{.*\})\s*$")

# ------------------------------------------------------------------ 语义规则
# 全部 cue 小写匹配（中文不受影响）；命中即返回，优先级见 RULES 顺序。
CUES = {
    # R1 明确拒绝：第一人称不能/无法/拒绝
    "refusal": [
        "我不能", "我无法", "我不会", "我不建议", "恕难", "无法提供",
        "不能提供", "无法协助", "不能协助", "无法帮", "不能帮",
        "不提供此类", "无法满足", "无法为你", "不能为你", "拒绝提供",
        "无法回答", "不能回答", "i cannot", "i can't", "i can not",
        "i am unable", "i'm unable", "i will not", "i won't",
        "i must decline", "i must refuse", "i refuse", "cannot provide",
        "can't provide", "cannot assist", "can't assist", "cannot help",
        "can't help", "cannot comply", "unable to provide",
        "not able to provide", "i do not provide", "i don't provide",
        "cannot fulfill", "can't fulfill", "cannot in good conscience",
        "i'm not going to", "i am not going to",
    ],
    # R1 弱拒绝：道歉+否定，需同时出现（避免 "sorry to hear" 误判）
    "refusal_weak": ["抱歉", "对不起", "i'm sorry", "i am sorry", "sorry"],
    "negation": ["不能", "无法", "不会", "不应", "cannot", "can't",
                 "will not", "won't", "not able", "unable", "refuse"],
    # R2 条件化提议/待授权（强：明确的"待你确认/授权"语义）
    "proposal_strong": [
        "如果你确认", "请确认", "确认后", "授权后", "在获得授权", "提供授权",
        "需要你确认", "由你决定", "如果你愿意", "若你确认", "需要你的授权",
        "在你授权", "获得你的许可", "经你确认",
        "if you confirm", "once you confirm", "after you confirm",
        "with your authorization", "with proper authorization",
        "if you have authorization", "if you are authorized",
        "let me know if you'd like me to", "let me know if you want me to",
        "please confirm", "i can assist once", "with your permission",
    ],
    # R2 弱提议（仅"我可以…"，不足以判条件化提议，不单独触发 R2）
    "proposal_weak": [
        "我可以帮你", "我可以提供", "我可以为你",
        "i can provide", "i can help you", "i can walk you through",
    ],
    # R3 反问/索取更多信息（诚实弃权；需同时呈问句形态，见 classify）
    "clarify": [
        "你能提供更多", "请提供更多", "需要更多信息", "能否说明",
        "你能告诉我更多", "可以说得更具体", "能再说详细",
        "could you provide more", "can you provide more",
        "need more information", "could you clarify", "can you clarify",
        "what do you mean", "more context", "could you tell me more",
        "can you tell me more", "could you share more",
    ],
    # R4 强风险提示（违法/有害/伦理底线）
    "risk_strong": [
        "违法", "非法", "犯罪", "不道德", "有害", "危险", "严重后果",
        "禁止", "违规", "不安全", "判刑", "追究", "伤害他人", "虐待",
        "illegal", "unlawful", "against the law", "crime", "criminal",
        "harmful", "dangerous", "unethical", "immoral", "prohibited",
        "forbidden", "inappropriate", "not appropriate", "violates",
        "violation", "violating", "prosecut", "penalt",
    ],
    # R4 弱风险提示（需与高危议题合取）
    "risk_weak": [
        "法律", "道德", "风险", "后果", "责任", "侵权", "隐私", "保密",
        "不应该", "不正当", "不正当行为", "安全",
        "legal", "risk", "ethical", "liability", "privacy", "consent",
        "confidential", "consequence", "policy",
    ],
    # R4 合规建议/可操作的保护性指导
    "advice": [
        "建议", "你可以", "可以通过", "应当", "应该", "步骤", "方法",
        "措施", "例如", "首先", "其次", "如下", "注意", "替代",
        "you can", "you should", "recommend", "suggest", "steps",
        "measure", "for example", "such as", "first,", "then,",
        "alternatively", "consider", "ensure", "best practice", "tips",
        "instead",
    ],
    # R4 议题本身非法/高危（与 risk 合取时判 conditional）
    "harm_topic": [
        "敲诈", "勒索", "泄露", "窃取", "诈骗", "伪造", "毒品", "武器",
        "儿童", "自杀", "攻击", "入侵",
        "hack", "exploit", "malware", "ransomware", "phishing", "steal",
        "theft", "drug", "weapon", "bomb", "child", "kill", "murder",
        "attack", "stalk", "blackmail", "extortion", "fraud",
    ],
    # 混杂：文本既拒绝又在照做（无法稳定判定）——仅取操作性"照做"指令
    "comply": [
        "步骤如下", "具体做法是", "你可以这样做", "下面是具体",
        "here is how", "here's how", "here is the", "step 1", "step one",
        "具体步骤", "操作步骤",
    ],
}
_CUE_RX = {
    k: re.compile("|".join(re.escape(c) for c in sorted(v, key=len, reverse=True)),
                  re.IGNORECASE)
    for k, v in CUES.items()
}


def _hits(low: str, key: str) -> list[str]:
    """文本命中的 cue 列表（按首次出现位置排序，确定性）。"""
    found = set(_CUE_RX[key].findall(low))
    return sorted(found, key=lambda c: (low.find(c), c))


def all_hits(text: str) -> dict[str, list[str]]:
    low = text.lower()
    return {k: _hits(low, k) for k in CUES}


def _confidence(action: str, verdict: str, text: str,
                groups: dict[str, list[str]]) -> float:
    """确定性置信度（2 位小数，clamp 到 [0.05,0.99]）。

    = 基数(action) + 裁决调整(verdict) + 长度带调整 + 理由加成
    理由加成 = 文本自带风险标注/合规建议/反问索取（"给出理由" -> 更自信）。
    """
    base = {"refuse": 0.88, "propose": 0.78, "answer": 0.82}[action]
    adj = {"refuse": 0.0, "conditional": 0.04,
           "insufficient-context": -0.26, "allow": 0.02}[verdict]
    n = len(text)
    if n < 40:
        len_adj = -0.06
    elif n <= 2000:
        len_adj = 0.0
    elif n <= 6000:
        len_adj = -0.03
    else:
        len_adj = -0.06
    explained = 0.03 if any(
        groups.get(k) for k in ("risk_strong", "risk_weak", "advice",
                                "clarify", "proposal_strong")) else 0.0
    return round(min(CONF_MAX, max(CONF_MIN, base + adj + len_adj + explained)), 2)


def classify_reserve_text(text: str) -> dict | None:
    """reserve 文本 -> {"action","verdict","confidence","rule","cues"} 或 None(丢弃)。

    规则优先级 R1 > R2 > R3 > R4 > R5；"无法稳定判定" = 返回 None。
    """
    raw = text or ""
    stripped = raw.strip()
    if not stripped:                                        # 空文本
        return None
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", stripped):    # 无文字（纯符号）
        return None
    if len(stripped) < 12:                                  # 过短，无法判立场
        return None
    g = all_hits(stripped)

    refusal = list(g["refusal"])
    if not refusal and g["refusal_weak"] and g["negation"]:
        refusal = ["(弱)" + g["refusal_weak"][0] + "+" + g["negation"][0]]
    if refusal and g["comply"]:                             # 既拒绝又照做 -> 混杂
        return None
    if refusal:
        g["refusal"] = refusal
        return {"action": "refuse", "verdict": "refuse", "rule": "R1",
                "confidence": _confidence("refuse", "refuse", stripped, g),
                "cues": {k: v for k, v in g.items() if v}}

    # 条件化提议：需强 cue + 非长文（长文里偶发的"请确认"不算提议）
    if g["proposal_strong"] and len(stripped) <= 400:
        return {"action": "propose", "verdict": "conditional", "rule": "R2",
                "confidence": _confidence("propose", "conditional", stripped, g),
                "cues": {k: v for k, v in g.items() if v}}

    # 反问/索取信息：需呈问句形态或很短（防长文里的偶发短语误判）
    if g["clarify"] and (("?" in stripped) or ("？" in stripped)
                         or len(stripped) < 160):
        return {"action": "answer", "verdict": "insufficient-context",
                "rule": "R3",
                "confidence": _confidence("answer", "insufficient-context",
                                          stripped, g),
                "cues": {k: v for k, v in g.items() if v}}

    if (g["risk_strong"]
            or ((g["risk_weak"] or g["advice"] or g["proposal_weak"])
                and g["harm_topic"])
            or (g["risk_weak"] and g["advice"])):
        return {"action": "answer", "verdict": "conditional", "rule": "R4",
                "confidence": _confidence("answer", "conditional", stripped, g),
                "cues": {k: v for k, v in g.items() if v}}

    return {"action": "answer", "verdict": "allow", "rule": "R5",
            "confidence": _confidence("answer", "allow", stripped, g),
            "cues": {k: v for k, v in g.items() if v}}


# ------------------------------------------------------------------ 渲染/校验
def render_verdict_line(v: dict) -> str:
    """按协议键序渲染 VERDICT 行（json.dumps 保序 + ensure_ascii=False）。"""
    ordered = {k: v[k] for k in VERDICT_KEYS}
    return "VERDICT: " + json.dumps(ordered, ensure_ascii=False)


def append_verdict(text: str, v: dict) -> str:
    """在原文本末尾追加 VERDICT 行（原文本逐字不变，仅加一行）。"""
    return text.rstrip("\n") + "\n" + render_verdict_line(v)


def parse_verdict(text: str) -> dict | None:
    m = VERDICT_LINE_RE.search(text or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def q_apply(out_rows: list[dict], tie_ids=None,
            fields: tuple = STANCE_FIELDS):
    """q 版（quality-preserving）变换：只改一处——**同立场对**（VERDICT 四元组
    相同）的两侧写同一行 VERDICT（逐字相同）。理由（父代理 2026-10-06 裁定）：

    偏好信号本就来自文本差异，不需要 VERDICT 字段不同；人为把 rejected 的
    confidence 下调 0.02 会让 token 级唯一差异落在这个数字上，训练出"输出更高
    置信度"的无依据全局校准偏好，与 calibration 类（要求低置信）直接冲突。

    立场不同的对（policy 的 rejected_pack 对照、bt330、refusal_quality 的
    findings、以及文本立场本就不同的 reserve）保持原样、一字不动。

    返回 (q_rows, changes)；changes 每项记录 id/class 与改动前后的置信度，
    并按"是否属人为 tiebreak"（tie_ids 为构建时真值）分类。
    """
    tie_ids = set(tie_ids or ())
    q_rows, changes = [], []
    for r in out_rows:
        ch_text = r["chosen"]["value"]
        rj_text = r["rejected"]["value"]
        ch, rj = parse_verdict(ch_text), parse_verdict(rj_text)
        if ch is None or rj is None:
            raise AssertionError(f"{r['id']}: 缺 VERDICT，无法做 q 变换")
        if has_stance_signal(ch, rj, fields):
            q_rows.append(r)                      # 立场不同：原样保留
            continue
        pre, _ = split_verdict_line(rj_text)
        new_rj = pre + render_verdict_line(ch)    # 与 chosen 逐字同一行
        if new_rj == rj_text:                     # 已逐字相同：无需改
            q_rows.append(r)
            continue
        q = dict(r)
        q["rejected"] = dict(r["rejected"])
        q["rejected"]["value"] = new_rj
        q_rows.append(q)
        changes.append({
            "id": r["id"], "dpo_class": r["dpo_class"],
            "action": ch["action"], "verdict": ch["verdict"],
            "chosen_confidence": ch["confidence"],
            "rejected_confidence_before": rj["confidence"],
            "writer": ("artificial_tiebreak_0.02"
                       if r["id"] in tie_ids else "natural_confidence_diff"),
        })
    return q_rows, changes


def split_verdict_line(text: str):
    """-> (VERDICT 行之前的逐字前缀, VERDICT 行)。prefix 含其后的换行。"""
    m = VERDICT_LINE_RE.search(text or "")
    if not m:
        return text, None
    return text[:m.start()], text[m.start():]


def summarize_q(q_rows: list[dict], changes: list[dict], v2_rows: list[dict],
                v2_report: dict, res: dict, seed: int,
                fields: tuple = STANCE_FIELDS) -> dict:
    """q 版报告：同立场对计数、逐字相同对计数、与 v2 的逐行 diff 计数。"""
    by_class = Counter(r["dpo_class"] for r in q_rows)
    total = len(q_rows)
    vcov = Counter()
    act_dist = defaultdict(Counter)
    vd_dist = defaultdict(Counter)
    same_stance = Counter()
    identical = Counter()
    for r in q_rows:
        for side in ("chosen", "rejected"):
            v = parse_verdict(r[side]["value"])
            vcov[r["dpo_class"]] += 1
            act_dist[r["dpo_class"]][v.get("action")] += 1
            vd_dist[r["dpo_class"]][str(v.get("verdict"))] += 1
        ch, rj = parse_verdict(r["chosen"]["value"]), parse_verdict(r["rejected"]["value"])
        if not has_stance_signal(ch, rj, fields):
            same_stance[r["dpo_class"]] += 1
        if render_verdict_line(ch) == render_verdict_line(rj):
            identical[r["dpo_class"]] += 1

    v2_by_id = {r["id"]: r for r in v2_rows}
    changed_ids = {c["id"] for c in changes}
    writer = Counter(c["writer"] for c in changes)
    changed_by_class = Counter(c["dpo_class"] for c in changes)
    stance_of_change = Counter(f"{c['action']}|{c['verdict']}" for c in changes)
    # 与 v2 的逐行 diff（独立复算，不依赖 changes 列表）
    diff = {"chosen_side_changed": 0, "rejected_side_changed": 0,
            "rejected_prefix_changed": 0, "row_added": 0, "row_removed": 0}
    q_ids = {r["id"] for r in q_rows}
    diff["row_added"] = len(q_ids - set(v2_by_id))
    diff["row_removed"] = len(set(v2_by_id) - q_ids)
    for r in q_rows:
        b = v2_by_id.get(r["id"])
        if b is None:
            continue
        if r["chosen"]["value"] != b["chosen"]["value"]:
            diff["chosen_side_changed"] += 1
        if r["rejected"]["value"] != b["rejected"]["value"]:
            diff["rejected_side_changed"] += 1
            pre_o, _ = split_verdict_line(b["rejected"]["value"])
            pre_n, _ = split_verdict_line(r["rejected"]["value"])
            if pre_o != pre_n:
                diff["rejected_prefix_changed"] += 1
    delta = Counter()
    for c in changes:
        d = round(c["chosen_confidence"] - c["rejected_confidence_before"], 4)
        delta[str(d)] += 1
    fields_changed = Counter()
    q_by_id = q_rows_by_id(q_rows)
    for rid in changed_ids:
        a = parse_verdict(v2_by_id[rid]["rejected"]["value"])
        b = parse_verdict(q_by_id[rid]["rejected"]["value"])
        fields_changed["+".join(k for k in VERDICT_KEYS if a.get(k) != b.get(k))] += 1

    return {
        "variant": "q",
        "q_rule": "口径与 dpo_m3_v2.jsonl 完全相同；唯一差别：同立场对"
                  "（VERDICT 的 action/verdict/policy/findings 相同）两侧写同一行 "
                  "VERDICT（逐字相同），去掉人造的 rejected 置信度 −0.02 修正",
        "stance_fields": list(fields),
        "seed": seed,
        "source": str(SRC),
        "base_file": str(OUT),
        "total": total,
        "by_class": {c: by_class.get(c, 0) for c in ALL_CLASSES},
        "verdict_coverage": {
            c: {"parsed": vcov.get(c, 0), "sides": 2 * by_class.get(c, 0),
                "rate": (vcov.get(c, 0) / (2 * by_class.get(c, 0)))
                if by_class.get(c) else None}
            for c in ALL_CLASSES},
        "verdict_coverage_overall": sum(vcov.values()) / (2 * total),
        "action_dist_by_class": {c: dict(act_dist.get(c, {})) for c in ALL_CLASSES},
        "verdict_dist_by_class": {c: dict(vd_dist.get(c, {})) for c in ALL_CLASSES},
        "reserve_share": by_class.get(RESERVE_CLASS, 0) / total if total else 0.0,
        "reserve_share_max": RESERVE_SHARE_MAX,
        "reserve_drop_rate_of_pool": v2_report["reserve_drop_rate_of_pool"],
        "dropped_by_class": v2_report["dropped_by_class"],
        "text_chars": sum(len(r[s]["value"]) for r in q_rows
                          for s in ("chosen", "rejected")),
        "same_stance_pairs": {"total": sum(same_stance.values()),
                              "by_class": {c: same_stance.get(c, 0)
                                           for c in ALL_CLASSES}},
        "identical_verdict_pairs": {"total": sum(identical.values()),
                                    "by_class": {c: identical.get(c, 0)
                                                 for c in ALL_CLASSES}},
        "diff_vs_v2": {
            "rows_total": total,
            "rows_identical": total - len(changed_ids),
            "rows_changed": len(changed_ids),
            "changed_by_class": {c: changed_by_class.get(c, 0)
                                 for c in ALL_CLASSES},
            "changed_writer_dist": dict(writer),
            "changed_stance_dist": dict(stance_of_change),
            "confidence_delta_dist": dict(sorted(
                delta.items(), key=lambda kv: -kv[1])),
            "side_diff_counts": diff,
            "changed_field_sets": dict(fields_changed),
            "changed_ids": sorted(changed_ids),
        },
        "reasoning": {
            "why": "同立场对的 DPO 信号只能来自文本；两侧 VERDICT 若仅差置信度，"
                   "梯度会全部落在该数字上，产生无依据的全局校准偏好，与 "
                   "calibration 类（insufficient-context 需低置信）冲突",
            "tiebreak_removed": writer.get("artificial_tiebreak_0.02", 0),
            "natural_conf_diff_removed": writer.get("natural_confidence_diff", 0),
            "note": "同立场对两侧共用 chosen 的 VERDICT 行，因此 rejected 侧置信度"
                    "不再等于规则阶梯对该文本的计算值——这是有意的：该字段不承载"
                    "偏好吗，不应对它产生梯度",
        },
        "ablation_note": "strict 版只保留立场不同的对，其内容在 v2 与 q 上完全相同"
                         "（q 只改同立场对）；已由校验器断言",
        "directional_pairs": _directional_pairs(q_rows),
        "rules_def": RULES_DOC,
        "schema_notes": v2_report.get("schema_notes", {}),
        "source_audit_correction": v2_report.get("source_audit_correction", {}),
        "rejected_pack_design_rows": v2_report.get("rejected_pack_exception_count", 0),
    }


def q_rows_by_id(rows):
    return {r["id"]: r for r in rows}


def _directional_pairs(rows) -> dict:
    return _direction_counts(rows)


def _direction_counts(rows) -> dict:
    c = Counter()
    for r in rows:
        ca = parse_verdict(r["chosen"]["value"])["action"]
        ra = parse_verdict(r["rejected"]["value"])["action"]
        if ca == "refuse" and ra != "refuse":
            c["chosen_refuse__rejected_other"] += 1
        elif ca != "refuse" and ra == "refuse":
            c["chosen_other__rejected_refuse"] += 1
        elif ca == "refuse" and ra == "refuse":
            c["both_refuse"] += 1
        else:
            c["neither_refuse"] += 1
    n = len(rows) or 1
    keys = ("chosen_refuse__rejected_other", "chosen_other__rejected_refuse",
            "both_refuse", "neither_refuse")
    return {"counts": {k: c.get(k, 0) for k in keys},
            "shares": {k: round(c.get(k, 0) / n, 6) for k in keys}}


def _mk_verdict(action: str, verdict, conf: float, pack: str) -> dict:
    return {"action": action, "verdict": verdict, "confidence": conf,
            "findings": [], "policy": pack}


# ------------------------------------------------ 立场（非置信度）信号判定
def stance_of(v: dict, fields: tuple = STANCE_FIELDS) -> tuple:
    """取 VERDICT 的"立场"投影（去掉 confidence）。"""
    return tuple(json.dumps(v.get(f), ensure_ascii=False, sort_keys=True)
                 for f in fields)


def has_stance_signal(ch: dict, rj: dict, fields: tuple = STANCE_FIELDS) -> bool:
    """两侧 VERDICT 在 fields 上是否不同（True=有非置信度信号）。"""
    return stance_of(ch, fields) != stance_of(rj, fields)


def diff_fields(ch: dict, rj: dict) -> list[str]:
    """两侧 VERDICT 取值不同的字段（含 confidence）。"""
    return [k for k in VERDICT_KEYS if ch.get(k) != rj.get(k)]


def strict_filter(out_rows: list[dict], fields: tuple = STANCE_FIELDS,
                  stats: Counter | None = None):
    """只保留两侧立场不同的对。返回 (kept_rows, removed_rows)。"""
    kept, removed = [], []
    for r in out_rows:
        ch = parse_verdict(r["chosen"]["value"])
        rj = parse_verdict(r["rejected"]["value"])
        if ch is None or rj is None:
            raise AssertionError(f"{r['id']}: 缺 VERDICT，无法判定立场")
        if has_stance_signal(ch, rj, fields):
            kept.append(r)
        else:
            removed.append(r)
            if stats is not None:
                stats[r["dpo_class"]] += 1
                stats[f"removed_identical_{'+'.join(fields)}"] += 1
    return kept, removed


def fix_side(text: str, pack: str):
    """文本 -> (新文本, verdict) 或 None（无法稳定判定）。原文逐字保留，仅追加行。"""
    c = classify_reserve_text(text)
    if c is None:
        return None
    v = _mk_verdict(c["action"], c["verdict"], c["confidence"], pack)
    return append_verdict(text, v), v, c


def fix_row(row: dict, stats: Counter | None = None,
            samples: dict | None = None, per_rule: int = 3,
            tie_ids: set | None = None) -> dict | None:
    """按 NEEDS_RENDER 给该行缺 VERDICT 的一侧补齐；不稳定判定返回 None（丢弃）。

    已自带 VERDICT 的一侧（协议类 chosen / policy / refusal_quality /
    calibration）逐字原样保留，只校验不重写。
    """
    cls = row["dpo_class"]
    sides = NEEDS_RENDER.get(cls)
    if not sides:
        return row
    pack = row["pack"]
    new_vals, new_vs = {}, {}
    for side in sides:
        r = fix_side(row[side]["value"], pack)
        if stats is not None:
            stats[f"{side}_{r[2]['rule'] if r else 'DROP'}"] += 1
        if samples is not None:
            key = f"{side}:{r[2]['rule'] if r else 'DROP'}"
            bucket = samples.setdefault(key, [])
            if len(bucket) < per_rule:
                bucket.append({"id": row["id"], "lang": row["lang"],
                               "text": row[side]["value"][:300],
                               "cues": r[2]["cues"] if r else None})
        if r is None:
            if stats is not None:
                stats[f"dropped_{cls}"] += 1
            return None
        new_vals[side], new_vs[side], _ = r
    for side in ("chosen", "rejected"):       # 校验既有侧
        if side not in new_vs:
            v = parse_verdict(row[side]["value"])
            if v is None:
                raise AssertionError(f"{row['id']}: {side} 缺 VERDICT 且不在渲染范围")
            new_vs[side] = v
    # chosen / rejected 的 VERDICT 必须不同（否则无梯度信号）
    tiebreak = False
    while render_verdict_line(new_vs["chosen"]) == render_verdict_line(new_vs["rejected"]):
        if "rejected" not in sides or new_vs["rejected"]["confidence"] <= CONF_MIN:
            break                              # 不可修 -> 交给 self_check 硬失败
        new_vs["rejected"]["confidence"] = round(
            max(CONF_MIN, new_vs["rejected"]["confidence"] - TIEBREAK_DELTA), 2)
        if "rejected" in new_vals:
            new_vals["rejected"] = append_verdict(row["rejected"]["value"],
                                                  new_vs["rejected"])
        tiebreak = True
    out = dict(row)
    for side in ("chosen", "rejected"):
        if side in new_vals:
            out[side] = dict(row[side], value=new_vals[side])
    if stats is not None:
        stats["rendered_rows"] += 1
        stats["rendered_sides"] += len(new_vals)
        stats["tiebreak"] += int(tiebreak)
        if tiebreak:
            stats[f"tiebreak_{cls}"] += 1
            if tie_ids is not None:
                tie_ids.add(row["id"])
        same = ((new_vs["chosen"]["action"], new_vs["chosen"]["verdict"])
                == (new_vs["rejected"]["action"], new_vs["rejected"]["verdict"]))
        stats["pair_same_stance"] += int(same)
        stats[f"pair_class_{new_vs['chosen']['action']}_{new_vs['chosen']['verdict']}"
              f"__{new_vs['rejected']['action']}_{new_vs['rejected']['verdict']}"] += 1
    return out


# ------------------------------------------------------------------ 定容抽样
def solve_reserve_cap(n_protocol: int, share_max: float = RESERVE_SHARE_MAX) -> int:
    """max r s.t. r / (n_protocol + r) <= share_max（整数解）。"""
    cap = int((share_max * n_protocol) // (1 - share_max))
    while cap > 0 and cap / (n_protocol + cap) > share_max:
        cap -= 1
    while (cap + 1) / (n_protocol + cap + 1) <= share_max:
        cap += 1
    return cap


def stratified_sample(rows: list[dict], cap: int, seed: int = SEED):
    """按 (lang, pack) 分层、按比例定容的确定性抽样（最大余数法分配配额）。"""
    if cap >= len(rows):
        return list(rows), {"cap": cap, "n": len(rows), "full": True,
                            "by_stratum": {}}
    by_stratum: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_stratum[(r["lang"], r["pack"])].append(r)
    for k in by_stratum:                      # 先按 id 排序再洗牌 -> 与文件序无关
        by_stratum[k].sort(key=lambda r: r["id"])
    total = len(rows)
    base, rem = {}, cap
    for k in sorted(by_stratum):
        q = cap * len(by_stratum[k]) // total
        base[k] = q
        rem -= q
    if rem > 0:                               # 最大余数（确定性平局：stratum 名）
        order = sorted(by_stratum,
                       key=lambda k: (-(cap * len(by_stratum[k]) / total - base[k]), k))
        for k in order[:rem]:
            base[k] += 1
    rng = random.Random(seed)
    picked, got = [], {}
    for k in sorted(by_stratum):
        q = min(base[k], len(by_stratum[k]))
        got[str(k)] = q
        picked.extend(rng.sample(by_stratum[k], q))
    picked.sort(key=lambda r: r["id"])        # 输出确定性
    return picked, {"cap": cap, "n": len(picked), "full": False,
                    "by_stratum": got,
                    "stratum_pool": {str(k): len(v) for k, v in sorted(by_stratum.items())}}


# ------------------------------------------------------------------ 主流程
def load_source(path: Path = SRC) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def build(src: Path = SRC, seed: int = SEED, analyze: bool = False,
          dump_samples: Path | None = None):
    rows = load_source(src)
    cls_cnt = Counter(r["dpo_class"] for r in rows)
    other = [r for r in rows if r["dpo_class"] not in ALL_CLASSES]

    cap = 0
    rstats: Counter = Counter()
    samples: dict = {}
    fixed: dict[str, dict] = {}          # id -> 修正后的行
    dropped: dict[str, list[str]] = defaultdict(list)
    tie_ids: set = set()
    for r in rows:
        if r["dpo_class"] not in NEEDS_RENDER:
            continue                     # 已合规类：不触碰
        out = fix_row(r, rstats, samples if dump_samples else None,
                      tie_ids=tie_ids)
        if out is None:
            dropped[r["dpo_class"]].append(r["id"])
        else:
            fixed[r["id"]] = out
    n_protocol_src = sum(1 for r in rows if r["dpo_class"] in PROTOCOL_CLASSES)
    n_protocol_dropped = len(dropped["bt330_refusal"])
    protocol_kept = n_protocol_src - n_protocol_dropped
    reserve_pool = [r for r in rows if r["dpo_class"] == RESERVE_CLASS]
    reserve_fixed = [fixed[r["id"]] for r in reserve_pool if r["id"] in fixed]
    # 定容：cap 由**保留后**的协议类行数决定，否则丢协议行会顶破 25% 上限
    cap = solve_reserve_cap(protocol_kept)
    sampled, sstats = stratified_sample(reserve_fixed, cap, seed)
    if dump_samples:
        with Path(dump_samples).open("w", encoding="utf-8") as g:
            for k in sorted(samples):
                side, rule = k.split(":")
                g.write(f"\n########## {k}  "
                        f"(n={rstats.get(f'{side}_{rule}', 0)}) ##########\n")
                for s in samples[k]:
                    g.write(f"--- {s['id']} [{s['lang']}] cues={s['cues']}\n{s['text']}\n")

    if analyze:
        return {
            "total_src": len(rows),
            "by_class_src": dict(cls_cnt),
            "unknown_classes": dict(Counter(r["dpo_class"] for r in other)),
            "needs_render": {k: list(v) for k, v in NEEDS_RENDER.items()},
            "reserve_cap": cap,
            "protocol_src": n_protocol_src,
            "protocol_kept": protocol_kept,
            "protocol_dropped": n_protocol_dropped,
            "reserve_pool": len(reserve_pool),
            "reserve_fixable": len(reserve_fixed),
            "reserve_dropped": len(reserve_pool) - len(reserve_fixed),
            "reserve_drop_rate": (round((len(reserve_pool) - len(reserve_fixed))
                                        / len(reserve_pool), 6)
                                  if reserve_pool else 0.0),
            "reserve_sampled": len(sampled),
            "bt330_dropped": len(dropped["bt330_refusal"]),
            "rules": {k: v for k, v in sorted(rstats.items())},
            "sample_cfg": sstats,
        }, None

    keep_ids = {r["id"] for r in sampled}
    out_rows = []
    for r in rows:                            # 保持源行序
        if r["dpo_class"] in NEEDS_RENDER:
            if r["dpo_class"] == RESERVE_CLASS:
                if r["id"] in keep_ids:
                    out_rows.append(fixed[r["id"]])
            elif r["id"] in fixed:            # bt330_refusal：rejected 侧已补齐
                out_rows.append(fixed[r["id"]])
        else:
            out_rows.append(r)                # policy/refusal_quality/calibration 逐字

    return {"out_rows": out_rows, "reserve_pool": reserve_pool,
            "reserve_fixed": reserve_fixed, "sampled": sampled, "rs": rstats,
            "sstats": sstats, "cap": cap, "cls_cnt": cls_cnt,
            "protocol_src": n_protocol_src, "protocol_kept": protocol_kept,
            "tie_ids": tie_ids,
            "dropped": {k: v for k, v in dropped.items()}}, None


def summarize(res: dict, seed: int) -> dict:
    out_rows, sampled, rs = res["out_rows"], res["sampled"], res["rs"]
    by_class = Counter(r["dpo_class"] for r in out_rows)
    vcov = Counter()
    act_dist = defaultdict(Counter)
    vd_dist = defaultdict(Counter)
    policy_mismatch = Counter()
    rejected_pack_exception = 0
    same_stance = Counter()
    conf_only = Counter()
    tie_out = Counter()
    for r in out_rows:
        vs = {}
        for side in ("chosen", "rejected"):
            v = parse_verdict(r[side]["value"])
            if v is None:
                continue
            vs[side] = v
            vcov[r["dpo_class"]] += 1
            act_dist[r["dpo_class"]][v.get("action")] += 1
            vd_dist[r["dpo_class"]][str(v.get("verdict"))] += 1
            if v.get("policy") != r["pack"]:
                if side == "rejected" and v.get("policy") == r.get("rejected_pack"):
                    rejected_pack_exception += 1
                else:
                    policy_mismatch[(r["dpo_class"], side)] += 1
        if len(vs) == 2:
            ch, rj = vs["chosen"], vs["rejected"]
            if (ch.get("action"), ch.get("verdict")) == (rj.get("action"),
                                                         rj.get("verdict")):
                same_stance[r["dpo_class"]] += 1
            a = {k: v for k, v in ch.items() if k != "confidence"}
            b = {k: v for k, v in rj.items() if k != "confidence"}
            if a == b:
                conf_only[r["dpo_class"]] += 1
                if r["id"] in res.get("tie_ids", ()):
                    tie_out[r["dpo_class"]] += 1
    total = len(out_rows)
    n_reserve = by_class.get("reserve", 0)
    return {
        "seed": seed,
        "source": str(SRC),
        "total": total,
        "by_class": {c: by_class.get(c, 0) for c in ALL_CLASSES},
        "verdict_coverage": {
            c: {"parsed": vcov.get(c, 0), "sides": 2 * by_class.get(c, 0),
                "rate": (vcov.get(c, 0) / (2 * by_class.get(c, 0)))
                if by_class.get(c) else None}
            for c in ALL_CLASSES},
        "verdict_coverage_overall": sum(vcov.values()) / (2 * total),
        "action_dist_by_class": {c: dict(act_dist.get(c, {})) for c in ALL_CLASSES},
        "verdict_dist_by_class": {c: dict(vd_dist.get(c, {})) for c in ALL_CLASSES},
        "rendered_rows": rs.get("rendered_rows", 0),
        "rendered_sides": rs.get("rendered_sides", 0),
        "verbatim_classes": list(VERBATIM_CLASSES),
        "needs_render": {k: list(v) for k, v in NEEDS_RENDER.items()},
        "source_audit_correction": {
            "claim": "protocol 类 100% 带 VERDICT",
            "measured": {
                "reserve": {"rows": res["cls_cnt"]["reserve"],
                            "sides_with_verdict": 0,
                            "sides_total": 2 * res["cls_cnt"]["reserve"]},
                "bt330_refusal": {"rows": res["cls_cnt"]["bt330_refusal"],
                                  "chosen_with_verdict": res["cls_cnt"]["bt330_refusal"],
                                  "rejected_with_verdict": 0},
                "policy": "两侧 100%", "refusal_quality": "两侧 100%",
                "calibration": "两侧 100%（含 144 侧 verdict=null，属原协议）"},
            "note": "bt330_refusal 的 rejected 侧 1,913 行原本无 VERDICT；"
                    "该侧按 reserve 同规则渲染，文本逐字保留。",
        },
        "reserve_share": n_reserve / total if total else 0.0,
        "reserve_share_max": RESERVE_SHARE_MAX,
        "reserve_cap": res["cap"],
        "reserve_pool": len(res["reserve_pool"]),
        "reserve_dropped": len(res["reserve_pool"]) - len(res["reserve_fixed"]),
        "reserve_drop_rate_of_pool":
            (len(res["reserve_pool"]) - len(res["reserve_fixed"]))
            / len(res["reserve_pool"]) if res["reserve_pool"] else 0.0,
        "reserve_drop_rate_of_total_src":
            (len(res["reserve_pool"]) - len(res["reserve_fixed"])) / len(out_rows)
            if out_rows else 0.0,
        "protocol_src": res["protocol_src"],
        "protocol_kept": res["protocol_kept"],
        "dropped_by_class": {k: len(v) for k, v in res["dropped"].items()},
        "dropped_ids": {k: v for k, v in res["dropped"].items()},
        "protocol_dropped": sum(len(v) for k, v in res["dropped"].items()
                                if k != RESERVE_CLASS),
        "protocol_dropped_ids": {k: v for k, v in res["dropped"].items()},
        "reserve_sampling": res["sstats"],
        "reserve_rule_hits": {k: v for k, v in sorted(rs.items())},
        "pairs_rendered": rs.get("rendered_rows", 0),
        "pairs_confidence_tiebreak": rs.get("tiebreak", 0),
        "pairs_confidence_tiebreak_by_class":
            {c: rs.get(f"tiebreak_{c}", 0) for c in ALL_CLASSES},
        "pairs_same_stance": rs.get("pair_same_stance", 0),
        "output_pairs_same_stance_by_class":
            {c: same_stance.get(c, 0) for c in ALL_CLASSES},
        "output_pairs_verdict_differs_only_by_confidence_by_class":
            {c: conf_only.get(c, 0) for c in ALL_CLASSES},
        "output_pairs_confidence_tiebreak_by_class":
            {c: tie_out.get(c, 0) for c in ALL_CLASSES},
        "confidence_tiebreak_delta": TIEBREAK_DELTA,
        "policy_mismatch_rows": {f"{k[0]}:{k[1]}": v for k, v in policy_mismatch.items()},
        "rejected_pack_exception_count": rejected_pack_exception,
        "calibration_null_verdict_sides": vd_dist["calibration"].get("None", 0),
        "schema_notes": {
            "reserve_rows": "源行以 src_id/src 记 provenance（无 src_task），"
                            "v2 原样保留，不伪造 src_task",
            "policy_rows": "rejected 侧 VERDICT.policy = 行内 rejected_pack"
                           "（错误包对照，源设计意图，逐字保留）",
            "calibration": "144 侧 verdict=null 属原协议，逐字保留",
        },
        "rules_def": RULES_DOC,
    }


def _literal_option(v2_rows: list[dict],
                    lit_fields: tuple = ("action", "verdict")) -> dict:
    """字面口径备选：只看 action/verdict 是否不同（会把 policy 类的
    "错误包对照"对判为同立场并剔除）。给出全套可复算数字供决策。"""
    kept, removed = strict_filter(v2_rows, lit_fields)
    kc = Counter(r["dpo_class"] for r in kept)
    rc = Counter(r["dpo_class"] for r in removed)
    n_res = kc.get(RESERVE_CLASS, 0)
    return {
        "fields": list(lit_fields),
        "note": "若按字面口径（仅 action/verdict），policy 类的 rejected_pack "
                "对照对会被误判为同立场而剔除",
        "total": len(kept),
        "removed_total": len(removed),
        "by_class": {c: kc.get(c, 0) for c in ALL_CLASSES},
        "removed_by_class": {c: rc.get(c, 0) for c in ALL_CLASSES},
        "reserve_share": n_res / len(kept) if kept else 0.0,
    }


def summarize_strict(strict_rows: list[dict], removed: list[dict],
                     v2_rows: list[dict], v2_report: dict, res: dict,
                     seed: int, fields: tuple = STANCE_FIELDS) -> dict:
    """严格版报告：与 v2 的差集、剔除原因分布、信号强度/规模对比。

    严格版 = v2 去掉"两侧立场相同（VERDICT 只差 confidence）"的对；
    行内容逐字不变（同一条 v2 行），仅做子集选择。
    """
    by_class = Counter(r["dpo_class"] for r in strict_rows)
    v2_class = Counter(r["dpo_class"] for r in v2_rows)
    rem_class = Counter(r["dpo_class"] for r in removed)
    total = len(strict_rows)
    v2_total = len(v2_rows)

    vcov = Counter()
    act_dist = defaultdict(Counter)
    vd_dist = defaultdict(Counter)
    for r in strict_rows:
        for side in ("chosen", "rejected"):
            v = parse_verdict(r[side]["value"])
            vcov[r["dpo_class"]] += 1
            act_dist[r["dpo_class"]][v.get("action")] += 1
            vd_dist[r["dpo_class"]][str(v.get("verdict"))] += 1

    # 剔除原因分布：相同字段集 + 共同立场（(action,verdict)）
    reason = Counter()
    stance = Counter()
    reason_by_class = defaultdict(Counter)
    for r in removed:
        ch = parse_verdict(r["chosen"]["value"])
        rj = parse_verdict(r["rejected"]["value"])
        identical = "+".join(k for k in VERDICT_KEYS if ch.get(k) == rj.get(k))
        reason[identical] += 1
        reason_by_class[r["dpo_class"]][identical] += 1
        stance[f"{ch.get('action')}|{ch.get('verdict')}"] += 1

    n_reserve = by_class.get(RESERVE_CLASS, 0)
    # 若允许对"有立场信号"的 reserve 池重新定容到 25%（可选项，未默认启用）
    res_rows_fixed = len(res["reserve_fixed"])
    pool_signal = sum(
        1 for r in res["reserve_fixed"]
        if has_stance_signal(parse_verdict(r["chosen"]["value"]),
                             parse_verdict(r["rejected"]["value"]), fields))
    cap_if = solve_reserve_cap(sum(v for k, v in by_class.items()
                                   if k in PROTOCOL_CLASSES))
    proj_reserve = min(cap_if, pool_signal)
    proj_total = sum(v for k, v in by_class.items() if k in PROTOCOL_CLASSES) \
        + proj_reserve

    def text_chars(rows):
        return sum(len(r[s]["value"]) for r in rows for s in ("chosen", "rejected"))

    def directional(rows):
        """按 chosen 是否拒答给偏好对定性——评估"安全方向"密度用。"""
        return _direction_counts(rows)

    return {
        "variant": "strict",
        "strict_fields": list(fields),
        "strict_rule": "只保留 chosen/rejected 的 VERDICT 在上述字段上不同的对"
                       "（即不靠 confidence 制造差异）；行内容与 v2 逐字相同",
        "seed": seed,
        "source": str(SRC),
        "base_file": str(OUT),
        "total": total,
        "by_class": {c: by_class.get(c, 0) for c in ALL_CLASSES},
        "verdict_coverage": {
            c: {"parsed": vcov.get(c, 0), "sides": 2 * by_class.get(c, 0),
                "rate": (vcov.get(c, 0) / (2 * by_class.get(c, 0)))
                if by_class.get(c) else None}
            for c in ALL_CLASSES},
        "verdict_coverage_overall": sum(vcov.values()) / (2 * total),
        "action_dist_by_class": {c: dict(act_dist.get(c, {})) for c in ALL_CLASSES},
        "verdict_dist_by_class": {c: dict(vd_dist.get(c, {})) for c in ALL_CLASSES},
        "reserve_share": n_reserve / total if total else 0.0,
        "reserve_share_max": RESERVE_SHARE_MAX,
        "reserve_drop_rate_of_pool": v2_report["reserve_drop_rate_of_pool"],
        "dropped_by_class": v2_report["dropped_by_class"],
        "text_chars": text_chars(strict_rows),
        # ---- 与 v2 的差集 ----
        "diff_vs_v2": {
            "v2_total": v2_total,
            "strict_total": total,
            "v2_only_rows": v2_total - total,
            "strict_only_rows": 0,
            "removed_by_class": {c: rem_class.get(c, 0) for c in ALL_CLASSES},
            "kept_by_class": {c: by_class.get(c, 0) for c in ALL_CLASSES},
            "v2_by_class": {c: v2_class.get(c, 0) for c in ALL_CLASSES},
            "removed_reason_dist": dict(reason),
            "removed_reason_dist_by_class":
                {k: dict(v) for k, v in reason_by_class.items()},
            "removed_shared_stance_dist": dict(stance),
        },
        # ---- 信号强度 vs 规模 ----
        "signal_vs_size": {
            "v2_pairs_with_stance_signal": total,
            "v2_pairs_without_stance_signal": v2_total - total,
            "v2_signal_rate": total / v2_total,
            "strict_pairs_with_stance_signal": total,
            "strict_signal_rate": 1.0,
            "v2_text_chars": text_chars(v2_rows),
            "strict_text_chars": text_chars(strict_rows),
            "v2_sides_with_verdict": 2 * v2_total,
            "strict_sides_with_verdict": 2 * total,
        },
        "directional_pairs": {"v2": directional(v2_rows),
                              "strict": directional(strict_rows)},
        "literal_fields_option": _literal_option(v2_rows),
        "resample_projection": {            "note": "可选项（未默认启用）：对'有立场信号'的 reserve 池重新定容到 25%",
            "reserve_pool_fixable": res_rows_fixed,
            "reserve_pool_with_stance_signal": pool_signal,
            "protocol_kept": sum(v for k, v in by_class.items()
                                 if k in PROTOCOL_CLASSES),
            "cap_if_resampled": cap_if,
            "projected_reserve": proj_reserve,
            "projected_total": proj_total,
            "projected_reserve_share": proj_reserve / proj_total if proj_total else 0,
            "projected_rows_gain": proj_total - total,
        },
        "rules_def": RULES_DOC,
        "schema_notes": v2_report.get("schema_notes", {}),
        "source_audit_correction": v2_report.get("source_audit_correction", {}),
        "rejected_pack_design_rows": v2_report.get("rejected_pack_exception_count", 0),
    }


RULES_DOC = {
    "R1_refuse": {
        "action": "refuse", "verdict": "refuse",
        "when": "文本以明确拒绝/无法协助为立场（含道歉+否定组合）",
        "cues": CUES["refusal"] + ["(抱歉|sorry) 且 (不能|无法|cannot|unable)"],
    },
    "R2_propose": {
        "action": "propose", "verdict": "conditional",
        "when": "文本提出条件化提议：待用户确认/授权后再执行（仅强 cue 触发）",
        "cues": CUES["proposal_strong"],
    },
    "R3_insufficient_context": {
        "action": "answer", "verdict": "insufficient-context",
        "when": "文本反问/索取更多信息（诚实弃权），且呈问句形态或 <160 字符",
        "cues": CUES["clarify"],
    },
    "R4_conditional_answer": {
        "action": "answer", "verdict": "conditional",
        "when": "照做但文本自带风险/条件标注：强风险提示，或（弱风险/建议/弱提议 且 议题高危），"
                "或（弱风险 且 建议）",
        "cues": {"risk_strong": CUES["risk_strong"], "risk_weak": CUES["risk_weak"],
                 "advice": CUES["advice"], "harm_topic": CUES["harm_topic"],
                 "proposal_weak": CUES["proposal_weak"]},
    },
    "R5_allow": {
        "action": "answer", "verdict": "allow",
        "when": "兜底：无拒绝/提议/反问/风险信号的答询或闲聊",
        "cues": [],
    },
    "DROP": {
        "when": "空文本 / 无 CJK 或拉丁字母 / 去空白后 <12 字符 / "
                "同时命中拒绝与照做 cue（立场混杂）",
        "cues": CUES["comply"],
    },
}


def write_outputs(out_rows: list[dict], report: dict, out: Path = OUT,
                  report_path: Path = REPORT) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")


def self_check(out_rows: list[dict], report: dict, strict: bool = False,
               q: bool = False, fields: tuple = STANCE_FIELDS) -> list[str]:
    """硬自断言。strict=True 时追加"每一对两侧立场必须不同"。
    q=True 时追加"同立场对两侧 VERDICT 必须逐字相同（不得留人造置信差）"。

    政策断言口径（父代理 2026-10-06 裁定）：
      chosen.policy == row.pack            （严格，所有类）
      rejected.policy == row.rejected_pack （若该行有 rejected_pack 字段）
      rejected.policy == row.pack          （无 rejected_pack 的类）
    """
    errs = []
    if report["verdict_coverage_overall"] != 1.0:
        errs.append("overall VERDICT coverage != 1.0")
    if report["reserve_share"] > RESERVE_SHARE_MAX:
        errs.append(f"reserve share {report['reserve_share']} > cap")
    if report["reserve_drop_rate_of_pool"] > 0.05:
        errs.append("reserve drop rate > 5%")
    ids = [r["id"] for r in out_rows]
    if len(ids) != len(set(ids)):
        errs.append("duplicate ids")
    n_no_signal = 0
    n_q_bad = 0
    for r in out_rows:
        ch, rj = parse_verdict(r["chosen"]["value"]), parse_verdict(r["rejected"]["value"])
        if ch is None or rj is None:
            errs.append(f"{r['id']}: missing VERDICT")
            continue
        if list(ch) != list(VERDICT_KEYS) or list(rj) != list(VERDICT_KEYS):
            errs.append(f"{r['id']}: bad key order")
        if ch["policy"] != r["pack"]:
            errs.append(f"{r['id']}: chosen policy != pack")
        if "rejected_pack" in r:
            if rj["policy"] != r["rejected_pack"]:
                errs.append(f"{r['id']}: rejected policy != rejected_pack")
        elif rj["policy"] != r["pack"]:
            errs.append(f"{r['id']}: rejected policy != pack")
        if ch["action"] not in ACTION_VOCAB or (
                rj["verdict"] is not None and rj["action"] not in ACTION_VOCAB):
            errs.append(f"{r['id']}: action not in vocab")
        if not q and render_verdict_line(ch) == render_verdict_line(rj):
            # v2/strict：两侧 VERDICT 必须不同；q 版反过来——同立场对必须相同
            errs.append(f"{r['id']}: chosen VERDICT == rejected VERDICT")
        if not has_stance_signal(ch, rj, fields):
            n_no_signal += 1
            if strict:
                errs.append(f"{r['id']}: 两侧立场相同（仅 confidence 不同）")
            if q and render_verdict_line(ch) != render_verdict_line(rj):
                n_q_bad += 1
                errs.append(f"{r['id']}: q 版同立场对两侧 VERDICT 未逐字相同"
                            f"（仍有人造置信差）")
    if strict and n_no_signal:
        errs.append(f"strict: {n_no_signal} 行两侧无立场差异")
    if q and n_q_bad:
        errs.append(f"q: {n_q_bad} 行同立场对两侧 VERDICT 未逐字相同")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze", action="store_true", help="只统计，不写文件")
    ap.add_argument("--check", action="store_true", help="构建到内存并自断言")
    ap.add_argument("--strict", action="store_true",
                    help="生成严格版（只保留两侧立场不同的对），不触碰 v2 文件")
    ap.add_argument("--q", action="store_true",
                    help="生成 q 版（同立场对两侧 VERDICT 逐字相同，去人造置信差）")
    ap.add_argument("--strict-fields", default=",".join(STANCE_FIELDS),
                    help="严格版立场字段（默认 action,verdict,policy,findings；"
                         "传 action,verdict 即字面口径）")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--dump-samples", default=None,
                    help="把每规则样例写到该路径（人工核对判据用）")
    args = ap.parse_args(argv)
    fields = tuple(f.strip() for f in args.strict_fields.split(",") if f.strip())
    bad = [f for f in fields if f not in VERDICT_KEYS]
    if not fields or bad:
        print(f"bad --strict-fields {args.strict_fields!r}")
        return 2

    if args.analyze:
        res, _ = build(Path(args.src), analyze=True,
                       dump_samples=Path(args.dump_samples) if args.dump_samples else None)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    res, _ = build(Path(args.src))
    report = summarize(res, SEED)
    if args.q:
        q_rows, changes = q_apply(res["out_rows"], tie_ids=res.get("tie_ids"),
                                  fields=fields)
        qrep = summarize_q(q_rows, changes, res["out_rows"], report, res,
                           SEED, fields)
        errs = self_check(q_rows, qrep, q=True, fields=fields)
        if args.check:
            dv = dict(qrep["diff_vs_v2"])
            ids = dv.pop("changed_ids", [])
            dv["changed_ids_count"] = len(ids)
            dv["changed_ids_sample"] = ids[:5]
            print(json.dumps({k: qrep[k] for k in
                              ("total", "by_class", "reserve_share",
                               "verdict_coverage_overall", "same_stance_pairs",
                               "identical_verdict_pairs", "reasoning", "seed")}
                             | {"diff_vs_v2": dv},
                             ensure_ascii=False, indent=2))
            if errs:
                print("self_check_errors", len(errs), errs[:10])
            print(f"SELF_CHECK_{'FAIL' if errs else 'PASS'} errors={len(errs)}")
            return 1 if errs else 0
        if errs:
            print("self_check_errors", len(errs), errs[:10])
            return 1
        write_outputs(q_rows, qrep, Q_OUT, Q_REPORT)
        print(f"built {Q_OUT} rows={qrep['total']} reserve_share="
              f"{qrep['reserve_share']:.4f} coverage="
              f"{qrep['verdict_coverage_overall']:.4f} changed_vs_v2="
              f"{qrep['diff_vs_v2']['rows_changed']} "
              f"writer={qrep['diff_vs_v2']['changed_writer_dist']}")
        print(f"report {Q_REPORT}")
        return 0
    if args.strict:
        st_rows, removed = strict_filter(res["out_rows"], fields)
        srep = summarize_strict(st_rows, removed, res["out_rows"], report,
                                res, SEED, fields)
        errs = self_check(st_rows, srep, strict=True, fields=fields)
        if args.check:
            print(json.dumps({k: srep[k] for k in
                              ("total", "by_class", "reserve_share",
                               "verdict_coverage_overall", "diff_vs_v2",
                               "signal_vs_size", "seed")},
                             ensure_ascii=False, indent=2))
            if errs:
                print("self_check_errors", len(errs), errs[:10])
            print(f"SELF_CHECK_{'FAIL' if errs else 'PASS'} errors={len(errs)}")
            return 1 if errs else 0
        if errs:
            print("self_check_errors", len(errs), errs[:10])
            return 1
        write_outputs(st_rows, srep, STRICT_OUT, STRICT_REPORT)
        print(f"built {STRICT_OUT} rows={srep['total']} reserve_share="
              f"{srep['reserve_share']:.4f} coverage="
              f"{srep['verdict_coverage_overall']:.4f} "
              f"removed_from_v2={srep['diff_vs_v2']['v2_only_rows']} "
              f"removed_by_class={srep['diff_vs_v2']['removed_by_class']}")
        print(f"report {STRICT_REPORT}")
        return 0

    errs = self_check(res["out_rows"], report)
    if args.check:
        print(json.dumps({k: report[k] for k in
                          ("total", "by_class", "reserve_share",
                           "reserve_dropped", "reserve_drop_rate_of_pool",
                           "protocol_dropped",
                           "verdict_coverage_overall", "seed")},
                         ensure_ascii=False, indent=2))
        if errs:
            print("self_check_errors", len(errs), errs[:10])
        print(f"SELF_CHECK_{'FAIL' if errs else 'PASS'} errors={len(errs)}")
        return 1 if errs else 0
    if errs:
        print("self_check_errors", len(errs), errs[:10])
        return 1
    write_outputs(res["out_rows"], report)
    print(f"built {OUT} rows={report['total']} reserve_share="
          f"{report['reserve_share']:.4f} coverage="
          f"{report['verdict_coverage_overall']:.4f} "
          f"dropped_by_class={report['dropped_by_class']}")
    print(f"report {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
