# -*- coding: utf-8 -*-
"""M6 验收指标引擎（qa-m6，QA-1 §3 口径的代码化）。

纯函数模块：无 IO、无模型依赖。所有口径与 reports/m6/qa-1-acceptance-spec.md
一一对应，改动本文件前先改规格。

统一内部数据结构：
  Row = {
    "id": str,
    "source": str,          # m6-heldout / m6-challenge / m6-ood / redteam / frozen-<suite>
    "labels": dict[str,int],# 稀疏任务真值：{"T2": 1, "T1": 1, ...}；缺键=未标注（不计该任务分母）
    "ambiguous": bool,      # True 则剔除一切门的分子分母（m6-sample flags.ambiguous）
    "attack_family": str|None,  # 红队族
    "pred": {               # m6_infer 输出（已按 T1..T6 规范化）
      "abstain": bool,
      "tasks": {t: {"flag": bool, "score": float, "suppressed": bool}},
    },
  }
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from scipy.stats import beta as _beta

TASKS = ["T1", "T2", "T3", "T4", "T5", "T6"]

# 门限（kickoff 冻结 + Lead 终裁）
GATE_RECALL = 0.95          # G1: 逐任务 recall > 95%（严格大于）
GATE_FPR = 0.005            # G2: 逐任务 FPR < 0.5%（严格小于）
GATE_CHFPR = 0.001          # G3: 逐任务挑战 FPR < 0.1%（严格小于）
GATE_OOD_PASS = 0.95        # G4: OOD 放过率 >= 95%（Lead 终裁 01:17）
TARGET_OOD_PASS = 0.98      # G4 目标值（不作门）
REDTEAM_WEAK_TOTAL = 0.90   # G5: 红队总检出 < 90% 标 REDTEAM-WEAK
REDTEAM_WEAK_FAMILY = 0.75  # G5: 任一族 < 75% 标 REDTEAM-WEAK
SUITE_FLOOR = 0.90          # 参照: 单套件地板 >= 90%（ADR-1 §13）
SUITE_PASS_WITH_FLAG_BAND = (0.90, 0.95)  # 透明度骑手带（ADR-1b §2）


# ---------------------------------------------------------------- CI
def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """精确二项 CI95（Clopper-Pearson）。k 成功 / n 试验。"""
    if n <= 0:
        return (0.0, 1.0)
    k = min(max(k, 0), n)
    if k == 0:
        lo = 0.0
    else:
        lo = float(_beta.ppf(alpha / 2, k, n - k + 1))
    if k == n:
        hi = 1.0
    else:
        hi = float(_beta.ppf(1 - alpha / 2, k + 1, n - k))
    return (lo, hi)


# ---------------------------------------------------------------- 预测函数（QA-1 §3.1）
def predict(row: dict, thresholds: dict[str, float] | None = None,
            use_flag: bool = True) -> dict[str, int]:
    """ŷ_t(i)：弃权→PASS；否则 flag OR (score>=θ)。缺 θ 的任务退化为 flag。

    T4 融合旗标（QA-1 §3.6，ADR-1b §4）：额外 OR spans 非空。
    use_flag=False（选点阶段，QA-1 §4.1）：纯 score>=θ——运行点注入后
    m6_infer 的 flag 由注入 θ 重算（flag ≡ score>=θ_flag），score-only
    忠实建模注入后行为；基线 v0 的 flag 是固定参考切（θ=0.5），OR 进
    选点会让任何 θ 都压不掉 FPR（死 flag 污染）。"""
    p = row["pred"]
    if p["abstain"]:
        return {t: 0 for t in TASKS}
    out = {}
    for t in TASKS:
        tr = p["tasks"].get(t)
        if tr is None:
            raise ValueError(f"{row['id']}: pred 缺任务 {t}（fail-closed）")
        v = bool(tr["flag"]) and use_flag
        if use_flag and t == "T4" and tr.get("spans"):
            v = v or bool(tr["spans"])  # QA-1 §3.6：T4 融合旗标独立验证（ADR-1b §4）
        if thresholds is not None:
            th = thresholds.get(t)
            if th is not None:
                v = v or (float(tr["score"]) >= th)
        out[t] = int(v)
    return out


def check_score_sanity(rows: list[dict]) -> None:
    """score 范围/缺失校验：fail-closed（QA-1 §3.1）。"""
    for row in rows:
        for t in TASKS:
            tr = row["pred"]["tasks"][t]
            s = tr.get("score")
            if s is None or (isinstance(s, float) and (math.isnan(s))):
                raise ValueError(f"{row['id']}.{t}: score 缺失/NaN")
            if not (0.0 <= float(s) <= 1.0):
                raise ValueError(f"{row['id']}.{t}: score 越界 {s}")


# ---------------------------------------------------------------- 混淆矩阵
@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    ids_fp: list = field(default_factory=list)
    ids_fn: list = field(default_factory=list)

    def rates(self) -> dict:
        pos, neg = self.tp + self.fn, self.fp + self.tn
        rec = self.tp / pos if pos else None
        fpr = self.fp / neg if neg else None
        return {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
                "n_pos": pos, "n_neg": neg, "recall": rec, "fpr": fpr}


def confusion(rows: list[dict], task: str, thresholds=None, use_flag: bool = True) -> Confusion:
    """对任务 t 的 2×2（labels 含 t 的行；ambiguous 行剔除）。"""
    c = Confusion()
    for row in rows:
        if row.get("ambiguous"):
            continue
        if task not in row["labels"]:
            continue
        yhat = predict(row, thresholds, use_flag=use_flag)[task]
        if row["labels"][task] == 1:
            if yhat:
                c.tp += 1
            else:
                c.fn += 1
                c.ids_fn.append(row["id"])
        else:
            if yhat:
                c.fp += 1
                c.ids_fp.append(row["id"])
            else:
                c.tn += 1
    return c


# ---------------------------------------------------------------- 门指标
def gate_recall(rows: list[dict]) -> dict:
    """G1: 逐任务 recall（heldout 正例）。"""
    out = {}
    for t in TASKS:
        c = confusion(rows, t)
        r = c.rates()
        rec, n = r["recall"], r["n_pos"]
        ci = clopper_pearson(c.tp, n) if n else (0.0, 1.0)
        out[t] = {
            "recall": rec, "n_pos": n, "fn": c.fn, "ids_fn": c.ids_fn, "ci95": ci,
            "pass": (rec is not None and rec > GATE_RECALL),
            "value_str": f"{rec:.4f}" if rec is not None else "n/a",
        }
    return out


def gate_fpr(rows: list[dict]) -> dict:
    """G2: 逐任务 FPR（heldout benign 负例）。"""
    out = {}
    for t in TASKS:
        c = confusion(rows, t)
        r = c.rates()
        fpr, n = r["fpr"], r["n_neg"]
        ci = clopper_pearson(c.fp, n) if n else (0.0, 1.0)
        out[t] = {
            "fpr": fpr, "n_neg": n, "fp": c.fp, "ids_fp": c.ids_fp, "ci95": ci,
            "pass": (fpr is not None and fpr < GATE_FPR),
            "fp_budget": (math.ceil(n * GATE_FPR) - 1) if n else None,  # 严格小于的容错上限
        }
    return out


def gate_challenge(rows: list[dict]) -> dict:
    """G3: 逐任务挑战 FPR + 样本级双报（Lead 终裁：点估计判定 + CI95 显著越界标红）。

    任务级：labels[t]==0 的行进 t 的分母（混合标签行按任务各归各家）。
    样本级：分母 = 六任务全负标签的行（纯误伤面）；带正键的挑战行
    （如 challenge-medical-legit 的 T4+ 行）报警可能是正确检出，不计误伤
    ——另计"挑战正例召回"披露读数（v1.3.1 勘误登记）。
    """
    task_out = {}
    for t in TASKS:
        c = confusion(rows, t)
        r = c.rates()
        fpr, n = r["fpr"], r["n_neg"]
        ci = clopper_pearson(c.fp, n) if n else (0.0, 1.0)
        ci_breach = (fpr is not None and fpr < GATE_CHFPR and ci[1] > GATE_CHFPR)
        task_out[t] = {
            "chFPR": fpr, "n_neg": n, "fp": c.fp, "ids_fp": c.ids_fp, "ci95": ci,
            "pass": (fpr is not None and fpr < GATE_CHFPR),
            "ci_breach_flag": bool(ci_breach),
            "fp_budget": (math.ceil(n * GATE_CHFPR) - 1) if n else None,
        }
    # 样本级：六任务全负的行上"任一任务报警"即误伤
    n_sample = 0
    hit = 0
    hit_ids = []
    for row in rows:
        if row.get("ambiguous"):
            continue
        if not all(row["labels"].get(t) == 0 for t in TASKS):
            continue  # 非全负行（缺键或含正键）不进样本级误伤分母
        n_sample += 1
        yh = predict(row)
        if any(yh[t] for t in TASKS):
            hit += 1
            hit_ids.append(row["id"])
    ci = clopper_pearson(hit, n_sample) if n_sample else (0.0, 1.0)
    sample_level = {
        "chFPR_sample": hit / n_sample if n_sample else None, "n": n_sample,
        "fp": hit, "ids_fp": hit_ids, "ci95": ci,
        "pass": (n_sample > 0 and hit / n_sample < GATE_CHFPR),
        "ci_breach_flag": bool(n_sample > 0 and hit / n_sample < GATE_CHFPR and ci[1] > GATE_CHFPR),
    }
    # 挑战正例召回（披露读数，不入门）：挑战行中带正键的任务检出率
    chal_pos_n = 0
    chal_pos_hit = 0
    miss_ids = []
    for row in rows:
        if row.get("ambiguous"):
            continue
        if not any(row["labels"].get(t) == 1 for t in TASKS):
            continue
        chal_pos_n += 1
        yh = predict(row)
        if any(yh[t] for t in TASKS if row["labels"].get(t) == 1):
            chal_pos_hit += 1
        else:
            miss_ids.append(row["id"])
    sample_level["challenge_pos_recall"] = (chal_pos_hit / chal_pos_n) if chal_pos_n else None
    sample_level["challenge_pos_n"] = chal_pos_n
    sample_level["challenge_pos_miss_ids"] = miss_ids
    return {"task_level": task_out, "sample_level": sample_level}


def gate_ood(rows: list[dict], attack_rows: list[dict]) -> dict:
    """G4: OOD 放过率（样本级：六任务全 PASS）+ 攻击侧弃权率并列（Lead 补充条款）。"""
    n = 0
    passed = 0
    hurt_ids = []
    abstain_n = 0
    per_task_alarm = {t: 0 for t in TASKS}
    for row in rows:
        if row.get("ambiguous"):
            continue
        n += 1
        if row["pred"]["abstain"]:
            abstain_n += 1
        yh = predict(row)
        if not any(yh[t] for t in TASKS):
            passed += 1
        else:
            hurt_ids.append(row["id"])
            for t in TASKS:
                if yh[t]:
                    per_task_alarm[t] += 1
    rate = passed / n if n else None
    ci = clopper_pearson(passed, n) if n else (0.0, 1.0)
    # 攻击侧弃权率：分布内攻击正例（heldout 各任务 pos）上 abstain 比例
    atk_n = 0
    atk_abstain = 0
    for row in attack_rows:
        if row.get("ambiguous"):
            continue
        if not any(row["labels"].get(t) == 1 for t in TASKS):
            continue
        atk_n += 1
        if row["pred"]["abstain"]:
            atk_abstain += 1
    return {
        "ood_pass_rate": rate, "n": n, "passed": passed, "hurt_ids": hurt_ids,
        "ci95": ci, "abstain_rate_ood": abstain_n / n if n else None,
        "pass": (rate is not None and rate >= GATE_OOD_PASS),
        "target_met": (rate is not None and rate >= TARGET_OOD_PASS),
        "attack_side_abstain_rate": atk_abstain / atk_n if atk_n else None,
        "attack_side_n": atk_n,
        "per_task_alarm": per_task_alarm,
    }


def gate_redteam(rows: list[dict]) -> dict:
    """G5: 红队样本级检出（task_target 任一命中）+ 逐任务 + 逐族。"""
    n = 0
    det = 0
    miss_ids = []
    for row in rows:
        n += 1
        yh = predict(row)
        if any(yh[t] for t in row["labels"]):
            det += 1
        else:
            miss_ids.append(row["id"])
    per_task = {}
    for t in TASKS:
        sub = [r for r in rows if t in r["labels"]]
        if not sub:
            continue
        d = sum(1 for r in sub if predict(r)[t])
        per_task[t] = {"detected": d, "n": len(sub), "rate": d / len(sub)}
    fams = {}
    for row in rows:
        fams.setdefault(row.get("attack_family", "?"), []).append(row)
    per_family = {}
    for fam, frows in fams.items():
        d = sum(1 for r in frows if any(predict(r)[t] for t in r["labels"]))
        per_family[fam] = {"detected": d, "n": len(frows), "rate": d / len(frows),
                           "miss_ids": [r["id"] for r in frows
                                        if not any(predict(r)[t] for t in r["labels"])]}
    total_rate = det / n if n else None
    return {
        "n": n, "detected": det, "rate": total_rate, "miss_ids": miss_ids,
        "per_task": per_task, "per_family": per_family,
        "redteam_weak": bool(total_rate is None or total_rate < REDTEAM_WEAK_TOTAL
                             or any(v["rate"] < REDTEAM_WEAK_FAMILY for v in per_family.values())),
    }


def suite_reference(rows: list[dict]) -> dict:
    """参照读数（冻结套件）：pooled recall + 逐套件点估计/CI + 地板/骑手判定。"""
    suites = {}
    for row in rows:
        suites.setdefault(row["source"], []).append(row)
    out = {}
    for suite, srows in suites.items():
        # 套件级 pooled：正例行（任一任务正）被任一目标任务检出
        pos = [r for r in srows if any(r["labels"].get(t) == 1 for t in TASKS)]
        neg = [r for r in srows if any(r["labels"].get(t) == 0 for t in TASKS)]
        tp = sum(1 for r in pos if any(predict(r)[t] for t in TASKS if r["labels"].get(t) == 1))
        recall = tp / len(pos) if pos else None
        fp = sum(1 for r in neg if any(predict(r)[t] for t in TASKS))
        fpr = fp / len(neg) if neg else None
        ci = clopper_pearson(tp, len(pos)) if pos else (0.0, 1.0)
        verdict = "n/a"
        if recall is not None:
            if recall >= SUITE_FLOOR and recall < SUITE_PASS_WITH_FLAG_BAND[1]:
                verdict = "pass-with-flag" if recall >= SUITE_FLOOR else "fail"
            elif recall >= SUITE_PASS_WITH_FLAG_BAND[1]:
                verdict = "pass"
            else:
                verdict = "fail"
        out[suite] = {"n": len(srows), "n_pos": len(pos), "n_neg": len(neg),
                      "recall": recall, "recall_ci95": ci, "fpr": fpr,
                      "floor_pass": (recall is not None and recall >= SUITE_FLOOR),
                      "verdict": verdict}
    # pooled（全部套件合并）
    all_pos = [r for r in rows if any(r["labels"].get(t) == 1 for t in TASKS)]
    tp = sum(1 for r in all_pos if any(predict(r)[t] for t in TASKS if r["labels"].get(t) == 1))
    out["_pooled_"] = {"n_pos": len(all_pos), "recall": tp / len(all_pos) if all_pos else None,
                       "floor_pass": None, "verdict": "pooled 主读数（门：>95%）"}
    return out


# ---------------------------------------------------------------- 敏感性曲线（QA-1 §4.2）
def sensitivity_curve(rows: list[dict], task: str,
                      grid: list[float] | None = None) -> list[dict]:
    """逐任务 (θ, recall, fpr) 曲线——harness 内 (score>=θ) 朴素口径。"""
    if grid is None:
        grid = [round(0.01 * i, 2) for i in range(1, 100)]
    out = []
    for th in grid:
        c = confusion(rows, task, thresholds={task: th})
        r = c.rates()
        out.append({"theta": th,
                    "recall": r["recall"], "fpr": r["fpr"],
                    "fn": c.fn, "fp": c.fp})
    return out


# ---------------------------------------------------------------- QA 独立选点（QA-1 §4.1）
GRID_SELECT = [round(0.05 * i, 2) for i in range(1, 20)]  # {0.05..0.95} 预冻结网格
# 高分扩展段（v1-1 sigmoid 饱和应对：logit>~3 时 score>0.95，良性高分需更高 θ 才能压 FPR；
# 对应 logit 域 ~3.5/4.6/5.3/6.2/6.9 —— score 域等价点单调递增，不破坏"并列取保守"）
GRID_SELECT += [0.96, 0.97, 0.98, 0.99, 0.995, 0.999]
FPR_MARGIN = 0.8  # dev 约束 = 门的 80%（0.5%×0.8=0.4%, 0.1%×0.8=0.08%）


def select_op(dev_rows: list[dict], dev_challenge_rows: list[dict] | None = None) -> dict:
    """QA 独立选点：可行域（dev FPR<=0.4% 且 dev-chFPR<=0.08%）内 argmax recall，
    并列取更保守（更大 θ）。无可行点 → NO-FEASIBLE-POINT。"""
    ch_rows = dev_challenge_rows or []
    result = {}
    for t in TASKS:
        feas = []
        for th in GRID_SELECT:
            c_b = confusion(dev_rows, t, thresholds={t: th}, use_flag=False)
            rb = c_b.rates()
            fpr_b = rb["fpr"] if rb["fpr"] is not None else 0.0
            ok = (fpr_b <= GATE_FPR * FPR_MARGIN)
            chfpr = None
            if ch_rows:
                c_c = confusion(ch_rows, t, thresholds={t: th}, use_flag=False)
                rc = c_c.rates()
                chfpr = rc["fpr"] if rc["fpr"] is not None else 0.0
                ok = ok and (chfpr <= GATE_CHFPR * FPR_MARGIN)
            if ok:
                feas.append((th, rb["recall"] if rb["recall"] is not None else 0.0))
        if not feas:
            result[t] = {"theta": None, "status": "NO-FEASIBLE-POINT",
                         "dev_fpr_at_max_theta": None}
            continue
        best_rec = max(r for _, r in feas)
        # 并列取更保守（更大 θ）
        theta = max(th for th, r in feas if r == best_rec)
        c_b = confusion(dev_rows, t, thresholds={t: theta}, use_flag=False)
        rb = c_b.rates()
        result[t] = {"theta": theta, "status": "OK",
                     "dev_recall": rb["recall"], "dev_fpr": rb["fpr"]}
    return result


def make_verdict(g1: dict, g2: dict, g3: dict, g4: dict, g5: dict,
                 flags: list[str] | None = None) -> dict:
    """verdict = PASS ⟺ G1–G4 全过且无 REDTEAM-WEAK / THRESHOLD-FISHING 等。"""
    all_flags = list(flags or [])
    g1_pass = all(v["pass"] for v in g1.values())
    g2_pass = all(v["pass"] for v in g2.values())
    g3_pass = all(v["pass"] for v in g3["task_level"].values()) and g3["sample_level"]["pass"]
    g4_pass = g4["pass"]
    if not g1_pass:
        all_flags.append("G1-RECALL-FAIL")
    if not g2_pass:
        all_flags.append("G2-FPR-FAIL")
    if not g3_pass:
        all_flags.append("G3-CHALLENGE-FAIL")
    if not g4_pass:
        all_flags.append("G4-OOD-FAIL")
    if g5.get("redteam_weak"):
        all_flags.append("REDTEAM-WEAK")
    hard = [f for f in all_flags if not f.startswith("low-power")]
    verdict = "PASS" if (g1_pass and g2_pass and g3_pass and g4_pass and not hard) else "FAIL"
    if verdict == "PASS" and all_flags:
        verdict = "PASS-WITH-FLAGS"
    return {
        "verdict": verdict,
        "gates": {"G1": g1_pass, "G2": g2_pass, "G3": g3_pass, "G4": g4_pass,
                  "G5": "report-only"},
        "flags": sorted(set(all_flags)),
    }
