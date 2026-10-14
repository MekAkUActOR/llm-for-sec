#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""M2.5 终混器：m1 基线 + 六族新行 → data/lf/sft_m25.jsonl。

输入（缺文件则跳过并记录，便于增量合流）：
  基线   data/lf/sft_m1.jsonl                      98,339（原样保留）
  fA     data/sft/m2.5-staging/fA_policy_v0x2.jsonl   ~10,000  policy_pairs
  fB     data/sft/m2.5-staging/fB_t4ground.jsonl       ~7,000  policy_pairs
  fC     data/sft/m2.5-staging/fC_cvpku_release.jsonl  ~7,600  policy_pairs
  fD     data/sft/m2.5-staging/fD_t6.jsonl             ~5,000  task_single
  fE     data/sft/m2.5-staging/fE_t3t12t11.jsonl       ~4,500  task_single
  fG     data/sft/m2.5-staging/fG_t6_devign_ext.jsonl 12,000  task_single（纯 en）
  t13    data/sft/m2.5-staging/t13_retrieval.jsonl     1,500   task_single
  t1     data/sft/m2.5-staging/t1_injection.jsonl        375   task_single
  t9     data/sft/m2.5-staging/t9_phishing.jsonl          50   task_single
  t14    data/sft/m2.5-staging/t14_authinject.jsonl    2,500   injection_jailbreak
  走私   data/sft/v0x/smuggle_multiturn.jsonl            387   multiturn

纪律：内容级 (pack,user) 全局排重（先到先得，基线优先；pack 参与键值，
三包梯度行不被误砍）；zh 裁剪只作用于最冗余族（TRIM_ZH_FRAC，按 user 整组
保留，包梯度不破）；配比断言；产出 reports/m25-assembly-check.json。注册 dataset_info 由父代理另行执行。
用法：python scripts/assemble_sft_m25.py [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "data" / "sft" / "m2.5-staging"
OUT = ROOT / "data" / "lf" / "sft_m25.jsonl"
CHECK = ROOT / "reports" / "m25-assembly-check.json"

NEW_FILES = [
    # (标签, 路径, 行族, 配额预期)
    ("fA_v0x2", STAGE / "fA_policy_v0x2.jsonl", "policy_pairs", 10000),
    ("fB_t4ground", STAGE / "fB_t4ground.jsonl", "policy_pairs", 7000),
    ("fC_cvpku", STAGE / "fC_cvpku_release.jsonl", "policy_pairs", 7600),
    ("fD_t6", STAGE / "fD_t6.jsonl", "task_single", 5000),
    ("fE_t3t12t11", STAGE / "fE_t3t12t11.jsonl", "task_single", 4500),
    ("fG_devign_ext", STAGE / "fG_t6_devign_ext.jsonl", "task_single", 12000),
    ("t13_retrieval", STAGE / "t13_retrieval.jsonl", "task_single", 1500),
    ("t1_injection", STAGE / "t1_injection.jsonl", "task_single", 375),
    ("t9_phishing", STAGE / "t9_phishing.jsonl", "task_single", 50),
    ("t14_authinject", STAGE / "t14_authinject.jsonl", "injection_jailbreak", 2500),
]
SMUGGLE_POOL = ROOT / "data" / "sft" / "v0x" / "smuggle_multiturn.jsonl"
SMUGGLE_TAKE = 400          # 池实测仅 387 行（早先 2,533 为过时估值）
M1 = ROOT / "data" / "lf" / "sft_m1.jsonl"

# 内容级 zh 裁剪：新族整体偏 zh（fA 64.8% / t14 69.6% / fC 57.1%），叠加
# m1 基线（内容级 35.8%）后全局冲上 49.7%，越过 45% 上限。优先裁**最冗余**
# 的族：fC 的 zh 侧 = cvalues 攻击提示 + 模板拒绝（m1 已有 4,800 同型行），
# 而 t14 授权注入族规则稀有、fA 法条接地族信息密度高，均不裁。
# 规则：按 user 内容哈希整组保留（fC 三包组同 user → 整组进出，包梯度不破）。
TRIM_ZH_FRAC = {"fC_cvpku": 0.15}


def uhash(row: dict) -> str:
    """去重键 = (pack, user)。三包梯度行 user 跨包相同（m1 先例：
    T5-policy 2,076 user × 3 包 = 6,228 行）——只按 user 去重会砍掉
    2/3 梯度行（曾在装配前拦截，未流入任何训练数据）。"""
    u = next((m["content"] for m in row["messages"] if m["role"] == "user"), "")
    p = row.get("pack", "")
    return hashlib.md5((p + "\x00" + u).encode("utf-8")).hexdigest()


def is_zh(row: dict) -> bool:
    u = next((m["content"] for m in row["messages"] if m["role"] == "user"), "")
    zh = sum(1 for c in u[:2000] if "\u4e00" <= c <= "\u9fff")
    return zh >= 8


def valid(row: dict) -> bool:
    msgs = row.get("messages", [])
    if [m.get("role") for m in msgs] != ["system", "user", "assistant"]:
        return False
    return bool(msgs[1]["content"].strip()) and "VERDICT: " in msgs[2]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    report = {"inputs": [], "totals": {}, "families": {}, "langs": {}, "dropped": {}}
    rows_out: list[dict] = []
    seen: set[str] = set()

    # --- 基线 m1（优先占位）---
    n_m1 = n_m1_dup = 0
    with M1.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            h = uhash(r)
            if h in seen:
                n_m1_dup += 1
                continue
            seen.add(h)
            rows_out.append(r)
            n_m1 += 1
    report["inputs"].append({"tag": "m1_baseline", "taken": n_m1, "internal_dup": n_m1_dup})

    # --- 新族文件 ---
    for tag, path, family, quota in NEW_FILES:
        if not path.exists():
            report["inputs"].append({"tag": tag, "status": "MISSING", "path": str(path)})
            continue
        n = dup = bad = trimmed = 0
        frac = TRIM_ZH_FRAC.get(tag)
        with path.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if not valid(r):
                    bad += 1
                    continue
                if frac is not None and is_zh(r):
                    u = next(m["content"] for m in r["messages"]
                             if m["role"] == "user")
                    keep = (int(hashlib.md5(u.encode("utf-8")).hexdigest()[:8],
                                16) % 1000) < frac * 1000
                    if not keep:
                        trimmed += 1
                        continue
                h = uhash(r)
                if h in seen:
                    dup += 1
                    continue
                seen.add(h)
                rows_out.append(r)
                n += 1
        report["inputs"].append({"tag": tag, "family": family, "quota": quota,
                                 "taken": n, "dup_dropped": dup,
                                 "invalid_dropped": bad,
                                 "zh_trimmed": trimmed})
        report["families"][family] = report["families"].get(family, 0) + n
        report["dropped"][tag] = {"dup": dup, "invalid": bad, "zh_trimmed": trimmed}

    # --- 走私池释放（multiturn 至配额）---
    if SMUGGLE_POOL.exists():
        n = dup = 0
        with SMUGGLE_POOL.open(encoding="utf-8") as f:
            for line in f:
                if n >= SMUGGLE_TAKE:
                    break
                r = json.loads(line)
                h = uhash(r)
                if h in seen:
                    dup += 1
                    continue
                seen.add(h)
                rows_out.append(r)
                n += 1
        report["inputs"].append({"tag": "smuggle_release", "family": "multiturn",
                                 "take_target": SMUGGLE_TAKE, "taken": n, "dup_dropped": dup})
        report["families"]["multiturn"] = report["families"].get("multiturn", 0) + n

    # --- 语言/动作统计 ---
    zh = sum(1 for r in rows_out if is_zh(r))
    report["totals"] = {"rows": len(rows_out), "zh": zh, "en": len(rows_out) - zh}
    report["langs"] = {"zh_pct": round(zh / len(rows_out) * 100, 1)}

    # --- 抗误拒配重 : 攻击 配比（2026-09-30 恢复；M2 组装器有，M2.5 曾缺失）---
    # 口径说明：M2 的 or_flag 是**行内 provenance 标记**，指"来自误拒基准
    # （OR-bench / xstest / wildguardmix / wildjailbreak）的**良性、应当被回答**的
    # 提示"——它是攻击型拒绝教学的**配重**，目标 OR:attack ≈ 1.25:1。
    # 该标记在 JSONL 化时丢失，无法复原，故此处用**可复算的派生定义**：
    #   attack    = task 属于攻击族（T1/T9/T14/T4-*/T5-attack 等）或含 ":attack"
    #   anti_or   = 非攻击行且末条 assistant VERDICT 的 action == "answer"
    #               （良性但看着可疑 → 教"正常回答" = 抗误拒配重，对应 M2 的 or_flag）
    #   overrefuse= 非攻击行且 action == "refuse"（在良性上教拒绝 = 误拒风险面）
    # 因此是**代理指标**，报告里显式标注 _proxy，跨版本比较须同口径。
    ATK_TOKENS = ("T1-injection", "T9-phish", "T14-authinject", "T5-attack",
                  "T4-ground", "wildjailbreak", "wildguardmix", "or-bench",
                  "xstest")

    def _task(r: dict) -> str:
        return str(r.get("task") or r.get("id") or "")

    def _is_atk(r: dict) -> bool:
        t = _task(r)
        return any(tok in t for tok in ATK_TOKENS) or ":attack" in t

    def _action(r: dict) -> str | None:
        msgs = [m for m in (r.get("messages") or []) if m.get("role") == "assistant"]
        if not msgs:
            return None
        c = msgs[-1].get("content") or ""
        if "VERDICT: " not in c:
            return None
        try:
            return json.loads(c.rsplit("VERDICT: ", 1)[1]).get("action")
        except Exception:
            return None

    atk_n = sum(1 for r in rows_out if _is_atk(r))
    anti_or_n = sum(1 for r in rows_out if not _is_atk(r) and _action(r) == "answer")
    overrefuse_n = sum(1 for r in rows_out if not _is_atk(r) and _action(r) == "refuse")
    report["or_attack_discipline"] = {
        "attack_n": atk_n,
        "anti_or_proxy_n": anti_or_n,          # 对应 M2 的 or_flag 语义
        "anti_or_to_attack_ratio_proxy":
            round(anti_or_n / atk_n, 3) if atk_n else None,
        "overrefuse_proxy_n": overrefuse_n,    # 良性上教拒绝（诊断用）
        "target": "anti_or:attack ≈ 1.25:1（M2 口径；此处为派生代理指标）",
        "caveat": ("or_flag/attack provenance 在 JSONL 化时丢失；本指标按 task 前缀 + "
                   "末条 VERDICT action 派生，语义对应 M2 的 or_flag（良性应答配重），"
                   "但不是同一测量"),
    }

    # --- 断言 ---
    errs = []
    total = len(rows_out)
    if not (135000 <= total <= 148000):
        errs.append("total %d out of band [135K,148K]" % total)
    if not (36.0 <= zh / total * 100 <= 45.0):
        errs.append("zh%% %.1f out of band [36,45]" % (zh / total * 100))
    # 攻防配比守卫（防止定义失效/某族整族缺失而静默通过）
    if atk_n == 0:
        errs.append("attack_n == 0：攻击族判定失效或攻击行整族缺失")
    if anti_or_n == 0:
        errs.append("anti_or_proxy_n == 0：抗误拒配重面判定失效或整族缺失")
    if atk_n and anti_or_n / atk_n < 0.50:
        errs.append("anti_or:attack 代理比 %.2f < 0.50：抗误拒配重偏薄（目标≈1.25）"
                    % (anti_or_n / atk_n))
    missing = [i["tag"] for i in report["inputs"] if i.get("status") == "MISSING"]
    if missing:
        errs.append("missing inputs: %s" % ",".join(missing))

    report["assertions"] = {"errors": errs, "passed": not errs}
    if args.dry_run:
        report["dry_run"] = True
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return
    if errs:
        print("ASSERTION FAILURES:")
        for e in errs:
            print(" -", e)
        sys.exit(1)

    with OUT.open("w", encoding="utf-8") as f:
        for r in rows_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    CHECK.parent.mkdir(parents=True, exist_ok=True)
    CHECK.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote %d rows -> %s" % (total, OUT))
    print(json.dumps(report["totals"], ensure_ascii=False))
    print("check -> %s" % CHECK)


if __name__ == "__main__":
    main()
