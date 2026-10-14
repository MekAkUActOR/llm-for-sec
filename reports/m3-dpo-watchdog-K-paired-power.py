# -*- coding: utf-8 -*-
"""M3 DPO watchdog K: toolout 轴的正确检验 —— 配对（McNemar 精确）而非非配对 Fisher。

为什么：所有 α 档都在**同一批 46 条鲁棒性条目**上评测，条目本身是配对的。
非配对 Fisher 丢弃了"同一条目"的信息，只用了边际计数；McNemar 只看**不一致对**
（discordant pairs），在本场景（少量单向翻转、0 反向）下功效高得多。

产出：reports/m3-dpo-watchdog-paired-power.json
纯 CPU、只读既有产物。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
sys.path.insert(0, str(ROOT / "scripts"))
import score_heldout_v2 as S  # noqa: E402
from secfm.eval.stats import fisher_p, fisher_p_greater, required_n  # noqa: E402

BASE = "m2calib"
TAGS = [p.name[len("resp-chat-to-"):-len(".jsonl")].strip()
        for p in sorted(R.glob("resp-chat-to-*.jsonl"))]


def load_axis(rule: str) -> dict:
    """逐档 {id: attack_success}（仅 robustness，仅已响应）。"""
    out = {}
    for tag in TAGS:
        resp = {}
        for line in (R / f"resp-chat-to-{tag}.jsonl").read_text(
                encoding="utf-8-sig").splitlines():
            if line.strip():
                o = json.loads(line)
                resp[o["id"]] = o.get("text", "")
        d = {}
        for iid, t in resp.items():
            if not iid.startswith("to-a-"):
                continue
            lab = S.classify(t, rule)["label"]
            d[iid] = 0.0 if lab in ("refuse", "report_finding") else 1.0
        out[tag] = d
    return out


def mcnemar_exact(b: int, c: int) -> dict:
    """b = 不一致对中"当前更差"（基线防御→当前攻击成功）；
    c = 不一致对中"当前更好"（基线攻击成功→当前防御）。返回精确 p。

    单侧命题："当前不得比基线更差" ⇒ 统计量取 b ⇒ p = P(X >= b | n, 0.5)。
    """
    n = b + c
    if n == 0:
        return {"n_new_success": 0, "n_reverse": 0, "n_discordant": 0,
                "p_one_sided": 1.0, "p_two_sided": 1.0}
    # 单侧（检验"当前更差"）：P(X >= b | n, 0.5)
    p1 = sum(math.comb(n, i) for i in range(b, n + 1)) / 2 ** n
    lo = min(b, c)
    p2 = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(0, lo + 1)) / 2 ** n)
    return {"n_new_success": b, "n_reverse": c, "n_discordant": n,
            "p_one_sided": round(p1, 4), "p_two_sided": round(round(p2, 6), 4)}


def _log_binom_pmf(i: int, n: int, p: float) -> float:
    """log C(n,i) p^i (1-p)^(n-i)，用 lgamma 避免大 n 溢出。"""
    if i < 0 or i > n:
        return float("-inf")
    if p <= 0.0:
        return 0.0 if i == 0 else float("-inf")
    if p >= 1.0:
        return 0.0 if i == n else float("-inf")
    return (math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
            + i * math.log(p) + (n - i) * math.log1p(-p))


def _binom_tail_ge(k: int, n: int, p: float) -> float:
    """P(X >= k)，X~Bin(n,p)，log 空间求和。"""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return min(1.0, math.fsum(math.exp(_log_binom_pmf(i, n, p))
                             for i in range(k, n + 1)))


def _reject_threshold(n: int, alpha: float) -> int | None:
    """H0: p=0.5 下最小 k 使 P(X>=k) <= alpha（尾概率随 k 单调不增，用二分）。"""
    if _binom_tail_ge(n, n, 0.5) > alpha:
        return None
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if _binom_tail_ge(mid, n, 0.5) <= alpha:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _power_at(n: int, p10: float, alpha: float) -> tuple[float, int | None]:
    k = _reject_threshold(n, alpha)
    if k is None:
        return 0.0, None
    return _binom_tail_ge(k, n, p10), k


def mcnemar_power_at(n: int, p10: float, p01: float, alpha: float) -> float:
    """配对设计在 n 条条目下的功效（McNemar 精确检验）。

    模型：不一致对数 D ~ Bin(n, p_d)，p_d = p10 + p01；
    给定 D=d，单侧统计量 B ~ Bin(d, θ)，θ = p10/p_d；
    H0 下 B|d ~ Bin(d, 0.5)，拒绝域 B >= k(d)，k(d) 为使
    P(X>=k|d,0.5) <= alpha 的最小 k（d<=4 时不存在 ⇒ 该 d 无法拒绝）。
    power = Σ_d P(D=d) · P(B >= k(d) | d, θ)
    """
    if p10 <= 0:
        return 0.0
    pd = p10 + p01
    theta = p10 / pd
    total = 0.0
    for d in range(0, n + 1):
        wp = math.exp(_log_binom_pmf(d, n, pd))
        if wp <= 0.0:
            continue
        k = _reject_threshold(d, alpha)
        if k is None:
            continue
        total += wp * _binom_tail_ge(k, d, theta)
    return min(1.0, total)


def mcnemar_power_n(p10: float, p01: float = 0.0, power: float = 0.80,
                    alpha: float = 0.05, cap: int = 4000) -> dict:
    """配对设计所需条目数（power 对 n 单调不减 ⇒ 二分搜索）。"""
    if p10 <= 0:
        return {"error": "p10 must be > 0"}
    if mcnemar_power_at(cap, p10, p01, alpha) < power:
        return {"error": "not reached", "cap": cap,
                "power_at_cap": round(mcnemar_power_at(cap, p10, p01, alpha), 4)}
    lo, hi = 1, cap
    while lo < hi:
        mid = (lo + hi) // 2
        if mcnemar_power_at(mid, p10, p01, alpha) >= power:
            hi = mid
        else:
            lo = mid + 1
    pd = p10 + p01
    return {"n_items_per_arm": lo,
            "power_at_that_n": round(mcnemar_power_at(lo, p10, p01, alpha), 4),
            "p10_discordant_one_way": round(p10, 4),
            "p01_discordant_reverse": round(p01, 4),
            "expected_discordant_new": round(pd * lo, 2)}


def main() -> int:
    out = {"base_tag": BASE, "note": __doc__.strip().splitlines()[0], "arms": {}}
    for rule in ("selfreport", "strict"):
        ax = load_axis(rule)
        base = ax[BASE]
        ids = sorted(base)
        n_items = len(ids)
        for tag in TAGS:
            cur = ax[tag]
            b = c = 0
            flipped = []
            for iid in ids:
                bv, cv = base[iid], cur[iid]
                if bv == 0.0 and cv == 1.0:
                    b += 1
                    flipped.append(iid)      # 基线防御、当前攻击成功
                elif bv == 1.0 and cv == 0.0:
                    c += 1
                    flipped.append(iid)      # 基线攻击成功、当前防御（反向）
            mc = mcnemar_exact(b, c)
            kb = int(sum(base.values()))
            kc = int(sum(cur.values()))
            out["arms"].setdefault(tag, {})[rule] = {
                "n_items": n_items,
                "base_k": kb, "cur_k": kc, "delta_items": kc - kb,
                "mcnemar": mc,
                "discordant_ids": flipped,
                "fisher_p_one_sided": round(
                    fisher_p_greater(kc, n_items - kc, kb, n_items - kb), 4),
                "fisher_p_two_sided": round(
                    fisher_p(kb, n_items - kb, kc, n_items - kc), 4),
            }

    # 功效：以观测到的单向不一致率 p10 为真值
    ax_sr = load_axis("selfreport")
    base_sr = ax_sr[BASE]
    n_items = len(base_sr)
    p10_by_arm = {}
    for tag in TAGS:
        cur = ax_sr[tag]
        c = sum(1 for i in sorted(base_sr)
                if base_sr[i] == 0.0 and cur[i] == 1.0)
        p10_by_arm[tag] = c / n_items
    obs_p10 = max(p10_by_arm.values())
    out["observed_discordance"] = {
        "n_items": n_items,
        "p10_one_way_by_arm": {k: round(v, 4) for k, v in p10_by_arm.items()},
        "p10_max_used": round(obs_p10, 4),
    }
    out["paired_power"] = {
        "method": "McNemar 精确（单侧 α=.05）；D~Bin(n,p_d)，B|D~Bin(D,θ)，"
                  "θ=p10/p_d；H0 下 B|D~Bin(D,.5)。power=Σ_d P(D=d)·P(B≥k(d)|d,θ)",
        "at_observed_p10_max": mcnemar_power_n(obs_p10),
        "at_p10_0.087_typical": mcnemar_power_n(4 / n_items),
        "at_p10_0.05": mcnemar_power_n(0.05),
        "at_p10_0.10": mcnemar_power_n(0.10),
        "at_p10_0.15": mcnemar_power_n(0.15),
    }
    # 对照：非配对口径
    out["unpaired_power_for_contrast"] = {
        "effect_2of46_to_6of46_required_n_per_group": required_n(2 / 46, 6 / 46),
        "delta_0.05_at_observed_base_required_n_per_group": required_n(
            kb / n_items, kb / n_items + 0.05),
    }
    OUT = R / "m3-dpo-watchdog-paired-power.json"
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    for rule in ("selfreport", "strict"):
        print(f"\n== {rule} 口径：配对 McNemar（同一批 "
              f"{out['arms'][BASE][rule]['n_items']} 条条目） ==")
        print(f"{'tag':12} {'base':>6} {'cur':>6} {'Δ':>4} {'new':>4} {'rev':>4} "
              f"{'p_1s':>7} {'p_2s':>7} {'Fisher p1s':>10} {'Fisher p2s':>10}")
        for tag in TAGS:
            a = out["arms"][tag][rule]
            m = a["mcnemar"]
            print(f"{tag:12} {a['base_k']:>6} {a['cur_k']:>6} "
                  f"{a['delta_items']:>+4d} {m['n_new_success']:>4} "
                  f"{m['n_reverse']:>4} "
                  f"{m['p_one_sided']:>7.4f} {m['p_two_sided']:>7.4f} "
                  f"{a['fisher_p_one_sided']:>10.4f} {a['fisher_p_two_sided']:>10.4f}")
    print("\n== 配对设计所需条目数（power 0.80, 单侧 α=.05） ==")
    for k, v in out["paired_power"].items():
        if isinstance(v, dict):
            if "n_items_per_arm" in v:
                print(f"  {k:22} → 每臂 {v['n_items_per_arm']:>4} 条 "
                      f"(实际 power={v['power_at_that_n']}, "
                      f"期望单向不一致对={v['expected_discordant_new']})")
            else:
                print(f"  {k:22} → {v}")
    print("\n== 非配对对照 ==")
    for k, v in out["unpaired_power_for_contrast"].items():
        print(f"  {k}: {v}")
    print("\nWROTE", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
