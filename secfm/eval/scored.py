# -*- coding: utf-8 -*-
"""判分报告读取助手（S0，2026-09-30）。

`score_heldout_v2.py` 的报告里既有聚合率（metrics）也有逐条明细（items）。门禁若只看
聚合率就无法做双轴/分域的计数检验（也就无法报 p 值与所需样本量）。本模块从 **items**
精确重建计数，供判定器与诊断脚本共用——**单一实现，避免两处漂移**。

术语：
  robustness 攻击/陷阱条目：`attack_success` 为真即"模型被攻破"
    - forward 轴：间接注入 / 多轮前瞻（report_finding 计为防御成功）
    - nonforward 轴：直接攻击
  alignment 条目：`over_refusal` 为真即"过度拒答"
  capability / calibration：计分独立，不在本模块
"""
from __future__ import annotations

__all__ = ["alignment_counts", "discordant_pairs", "domain_rates",
           "label_distribution", "outcome_map", "robustness_axes"]


def _responded(doc: dict) -> list[dict]:
    return [r for r in doc.get("items", []) if r.get("responded")]


def _counts(sel: list[dict], key: str) -> dict:
    labels: dict[str, int] = {}
    for r in sel:
        lab = r.get("label")
        labels[lab] = labels.get(lab, 0) + 1
    return {
        "n": len(sel),
        "success": sum(1 for r in sel if r.get("derived", {}).get(key)),
        "labels": dict(sorted(labels.items(), key=lambda kv: (-kv[1], str(kv[0])))),
    }


def robustness_axes(doc: dict) -> dict:
    """→ {"all": {…}, "fwd": {…}, "nfwd": {…}}，各含 n/success/labels。"""
    rob = [r for r in _responded(doc) if r.get("kind") == "robustness"]
    return {
        "all": _counts(rob, "attack_success"),
        "fwd": _counts([r for r in rob if r.get("forward")], "attack_success"),
        "nfwd": _counts([r for r in rob if not r.get("forward")],
                        "attack_success"),
    }


def alignment_counts(doc: dict) -> dict:
    """误拒（over_refusal）计数：用于 ORR 分轴门禁。"""
    ali = [r for r in _responded(doc) if r.get("kind") == "alignment"]
    return _counts(ali, "over_refusal")


def domain_rates(doc: dict, domain_map: dict, domain: str,
                 kind: str | None = "robustness") -> dict | None:
    """按域（+可选 kind）聚合攻击成功率。domain_map: id -> domain。"""
    sel = [r for r in _responded(doc)
           if domain_map.get(r.get("id")) == domain
           and (kind is None or r.get("kind") == kind)]
    if not sel:
        return None
    return _counts(sel, "attack_success")


def outcome_map(doc: dict, key: str, kind: str | None = None,
                forward: bool | None = None) -> dict[str, int]:
    """item id → 0/1（`derived.<key>` 为真记 1）。用于**配对**检验。

    只取 `responded` 的条目；缺 `id` 的条目**跳过**（无法配对）。
    """
    out: dict[str, int] = {}
    for r in _responded(doc):
        if kind is not None and r.get("kind") != kind:
            continue
        if forward is not None and bool(r.get("forward")) is not forward:
            continue
        iid = r.get("id")
        if not iid:
            continue
        out[str(iid)] = 1 if r.get("derived", {}).get(key) else 0
    return out


def discordant_pairs(cur: dict, base: dict, key: str, kind: str | None = None,
                     forward: bool | None = None) -> dict | None:
    """同一条目集上的**配对不一致对**：b = 基线 0→当前 1（朝 1 方向翻转），
    c = 基线 1→当前 0（反向）。供单侧配对 McNemar（`stats.mcnemar_p`）使用。

    为什么需要（2026-09-30，看门狗提出）：本项目的行为门禁几乎都是**同一批条目**
    上的变体 vs 基线比较 ⇒ 应作配对检验；非配对 Fisher 会丢掉配对信息
    （实测配对比非配对 p 小 2.1–2.5 倍），从而把**已证劣化**误降为"未达可区分"。

    **fail-closed**：两侧条目 id 集合不一致时返回 None（此时不得做配对检验，
    调用方应退回非配对并标注），并给出 both/only 计数供诊断。
    """
    c_map = outcome_map(cur, key, kind=kind, forward=forward)
    b_map = outcome_map(base, key, kind=kind, forward=forward)
    if not c_map or not b_map:
        return None
    common = set(c_map) & set(b_map)
    if not common:
        return None
    b = sum(1 for i in common if b_map[i] == 0 and c_map[i] == 1)
    c = sum(1 for i in common if b_map[i] == 1 and c_map[i] == 0)
    return {"b": b, "c": c, "n_paired": len(common),
            "only_cur": len(set(c_map) - set(b_map)),
            "only_base": len(set(b_map) - set(c_map)),
            "pairing_complete": set(c_map) == set(b_map)}


def label_distribution(doc: dict) -> dict:
    out: dict[str, int] = {}
    for r in _responded(doc):
        out[r.get("label")] = out.get(r.get("label"), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], str(kv[0]))))
