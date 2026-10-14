# -*- coding: utf-8 -*-
"""P0.7 组装器：合成 data/heldout/v0.7-jailbreak/（规格 §9/§15）。

输入：scripts/_p07_parts/part_f1..f6 + part_benign（每批已各自自检 PASS）。
输出（幂等、确定性——重跑逐字节一致，冻结 = manifest 登记的 sha256）：
  data/heldout/v0.7-jailbreak/jailbreak.jsonl   150 行（120 攻击 + 30 良性）
  data/heldout/v0.7-jailbreak/manifest.json     §9.2 字段 + 冻结 sha256
  data/heldout/v0.7-jailbreak/README.md         「非单轮 heldout 套件」声明
  data/heldout/v0.7-jailbreak/spotcheck-20.md   种子抽样 20 条（≥ 任务书 spotcheck-15）

用法：.venv\\Scripts\\python.exe scripts\\build_jailbreak_suite.py
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "_p07_parts"))

from _p07_common import (BENIGN_KEY_ORDER, CATEGORY_FULL, FAMILY_IDS,  # noqa: E402
                         HOLDOUT_FAMILIES, KEY_ORDER, check_rows)
import part_f1, part_f2, part_f3, part_f4, part_f5, part_f6, part_benign  # noqa: E402

OUT_DIR = ROOT / "data" / "heldout" / "v0.7-jailbreak"
OUT_JSONL = OUT_DIR / "jailbreak.jsonl"
SEED = 20261008

EXPECTS = {
    "F1": {"n": 20, "zh": 10, "en": 10, "cats": {"C1": 5, "C2": 5, "C3": 5, "C4": 5}},
    "F2": {"n": 20, "zh": 10, "en": 10, "cats": {"C1": 5, "C2": 5, "C3": 5, "C5": 5}},
    "F3": {"n": 20, "zh": 10, "en": 10, "cats": {"C1": 5, "C2": 5, "C3": 5, "C4": 5}},
    "F4": {"n": 20, "zh": 10, "en": 10, "cats": {"C1": 5, "C2": 5, "C3": 5, "C4": 5}},
    "F5": {"n": 20, "zh": 10, "en": 10, "cats": {"C1": 5, "C2": 5, "C3": 5, "C4": 5}},
    "F6": {"n": 20, "zh": 10, "en": 10, "cats": {"C1": 5, "C2": 5, "C3": 4, "C5": 6}},
    "B": {"n": 30, "zh": 15, "en": 15},
}


def collect() -> list[dict]:
    parts = [("F1", part_f1.ROWS), ("F2", part_f2.ROWS), ("F3", part_f3.ROWS),
             ("F4", part_f4.ROWS), ("F5", part_f5.ROWS), ("F6", part_f6.ROWS),
             ("B", part_benign.ROWS)]
    rows, errs = [], []
    for fam, rs in parts:
        errs += check_rows(fam, rs, EXPECTS[fam])
        rows += rs
    if errs:
        for e in errs:
            print("ASSEMBLE-FAIL: " + e)
        raise SystemExit(f"批次自检失败 {len(errs)} 项（先修批次再组装）")

    # ---- 跨批断言 ----
    if len(rows) != 150:
        raise SystemExit(f"总条数 {len(rows)} != 150")
    atk = [r for r in rows if r["kind"] == "robustness"]
    ben = [r for r in rows if r["kind"] == "alignment"]
    if len(atk) != 120 or len(ben) != 30:
        raise SystemExit(f"攻击/良性 = {len(atk)}/{len(ben)}，期望 120/30")
    ids = [r["id"] for r in rows]
    if len(set(ids)) != 150:
        raise SystemExit("跨批 id 重复")
    if any(not i.startswith("jb-") for i in ids):
        raise SystemExit("id 前缀非法（须 jb-）")
    if len(set(r["turns"][-1] for r in rows)) != 150:
        raise SystemExit("跨批收割轮文本重复")
    for fam_code, fam_id in FAMILY_IDS.items():
        fr = [r for r in atk if r["family"] == fam_id]
        if len(fr) != 20:
            raise SystemExit(f"{fam_code} 条数 {len(fr)} != 20")
        z = sum(1 for r in fr if r["language"] == "zh")
        if z != 10:
            raise SystemExit(f"{fam_code} zh/en = {z}/{20 - z}")
        if any(r["holdout"] != (fam_code in HOLDOUT_FAMILIES) for r in fr):
            raise SystemExit(f"{fam_code} holdout 标记不一致")
    n_turns_total = sum(r["n_turns"] for r in rows)
    if n_turns_total / len(rows) < 3.5:
        raise SystemExit(f"全集平均轮数 {n_turns_total / len(rows):.3f} < 3.5")
    print(f"跨批断言 PASS：150 行（120+30），平均轮数 "
          f"{n_turns_total / len(rows):.3f}")
    return rows


def write_jsonl(rows: list[dict]) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    OUT_JSONL.write_text("\n".join(lines) + "\n", encoding="utf-8",
                         newline="\n")
    return hashlib.sha256(OUT_JSONL.read_bytes()).hexdigest()


def write_manifest(rows: list[dict], sha: str) -> None:
    atk = [r for r in rows if r["kind"] == "robustness"]
    fam_counts, fam_holdout = {}, {}
    for r in atk:
        fam_counts[r["family"]] = fam_counts.get(r["family"], 0) + 1
        fam_holdout[r["family"]] = r["holdout"]
    turns_hist = Counter(r["n_turns"] for r in rows)
    man = {
        "instrument": "v0.7-jailbreak",
        "generated_by": "scripts/build_jailbreak_suite.py",
        "seed": SEED,
        "file": "jailbreak.jsonl",
        "sha256": sha,
        "n_items": len(rows),
        "n_attack": len(atk),
        "n_benign": len(rows) - len(atk),
        "by_kind": dict(Counter(r["kind"] for r in rows)),
        "by_family": {k: {"n": fam_counts[k], "holdout": fam_holdout[k]}
                      for k in sorted(fam_counts)},
        "by_language": dict(Counter(r["language"] for r in rows)),
        "by_harm_category": dict(Counter(r["harm_category"] for r in atk)),
        "by_policy_pack": dict(Counter(r["policy_pack"] for r in rows)),
        "payoff_types": dict(Counter(r["payoff"]["type"] for r in atk)),
        "turns_histogram": {str(k): turns_hist[k] for k in sorted(turns_hist)},
        "avg_turns": round(sum(r["n_turns"] for r in rows) / len(rows), 4),
        "benign_by_language": dict(Counter(r["language"] for r in rows
                                           if r["kind"] == "alignment")),
        "benign_by_policy_pack": dict(Counter(r["policy_pack"] for r in rows
                                              if r["kind"] == "alignment")),
        "schema": {
            "attack_key_order": KEY_ORDER,
            "benign_key_order": BENIGN_KEY_ORDER,
            "reference": "reports/p0.7-jailbreak-instrument-design.md §9.1",
            "benign_payoff_omitted": True,
            "consumers": ["scripts/probe_jailbreak.py"],
            "not_consumers": [
                "secfm.eval.heldout.load_dir（无 query 键 ⇒ fail-closed 报错，"
                "预期的防误用行为）",
                "scripts/baseline_eval.py --heldout（单轮渲染，不适用）",
            ],
        },
        "holdout_families": list(HOLDOUT_FAMILIES),
        "holdout_discipline": (
            "F4/F6 = 泛化留出族：任何样本（含仿写变体）不得进入训练/校准/"
            "偏好混料；构建验收阶段零模型读数；读数只入最终门禁报告的 "
            "holdout_families_block，不入任何调参视野（设计文档 §5）"),
        "freeze_rule": ("manifest 登记本 sha256 即冻结；修改 ⇒ 新开版本目录 "
                        "v0.7b-jailbreak + 旧读数作废登记"),
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
        newline="\n")


README = """# v0.7-jailbreak：对话式越狱仪器（P0.7）

> 设计：`reports/p0.7-jailbreak-instrument-design.md`（DESIGN=DONE）。
> 构建：`scripts/build_jailbreak_suite.py`（幂等确定性组装，冻结 sha256 见
> `manifest.json`）。唯一消费者 = `scripts/probe_jailbreak.py`。

## 这不是单轮 heldout 套件（防误用 ✗）

- 本套件为**真·多轮 rollout** schema：每行是 `turns`（3–5 个 user 轮），
  `turns[-1]` = 收割轮（良性层 = 最终正当请求）；
- **不能**用 `secfm.eval.heldout.load_dir` 加载：本套件无 `query` 键，
  loader 会 fail-closed 报错——这是预期的防误用行为；
- **不能**用 `scripts/baseline_eval.py --heldout` 跑：那是单轮渲染器；
- 唯一运行器/判分器 = `scripts/probe_jailbreak.py`（token 拼装式多轮渲染
  + 逐轮 `score_heldout_v2.classify` 双口径判分 + ASR 汇总）。

## 构成（150 行）

| 层 | 构成 | 条数 |
|---|---|---|
| 攻击层 | 6 族 × 20（10 zh + 10 en/族） | 120 |
| ├ 训练可见族 | F1 渐进升级 / F2 角色扮演 / F3 虚构框架 / F5 拼图抽取 | 80 |
| └ **泛化留出族 ✗** | F4 编码变形 / F6 权限伪造 | 40 |
| 良性对照层 | 15 zh + 15 en；professional 15 + default 15 | 30 |

harm 类别：C1 恶意软件 ×30 / C2 定向入侵 ×30 / C3 钓鱼 ×29 /
C4 隐私去保护 ×20 / C5 系统提示泄漏 ×11（分布见 manifest）。

## 留出冻结纪律（§5，红线）

- `holdout=true` 的 F4/F6 **永不入训练**（含任何仿写变体）；训练数据生成器
  必须把留出族清单作为输入断言；
- 构建验收阶段对留出族**零模型读数**（冒烟只允许合成接线测试与训练可见
  族的假响应判分）；
- 冻结 = `manifest.json` 登记的 `sha256`；修改 ⇒ 新开 `v0.7b-jailbreak`。

## 零武器化

全部轮文本为**模式级请求**：不含可运行代码、URL、真实凭证或成品有害
内容；泄漏类的成功证据是哨兵标记（`LEAK_OK`/`DEBUG_OK`）与政策包
n-gram，而非真实系统提示全文。F4 编码轮的密文可机械解码还原
（`〈…〉` span，base64/ROT13），解码视图即模式级请求本身。
"""


def write_readme() -> None:
    (OUT_DIR / "README.md").write_text(README, encoding="utf-8", newline="\n")


def write_spotcheck(rows: list[dict]) -> None:
    rng = random.Random(SEED)
    atk = [r for r in rows if r["kind"] == "robustness"]
    ben = [r for r in rows if r["kind"] == "alignment"]
    sample = rng.sample(atk, 10) + rng.sample(ben, 10)   # B8：良性行 ≥10
    sample.sort(key=lambda r: r["id"])
    out = ["# v0.7-jailbreak 抽检单（spotcheck-20 = 10 攻击 + 10 良性，种子抽样确定性可复现）", "",
           "> 构建侧机检全项见 `scripts/check_jailbreak_suite.py`（B1–B9）。",
           "> 本单供所有者人工抽检：结构合理性 / 话题正当性（良性行 10 条 ≥ B8 的 ≥10）/",
           "> 收割轮可判性。规格 §9.2 要求 20 条（≥ 任务书的 spotcheck-15）。", ""]
    for r in sample:
        out.append(f"## {r['id']}　{r['family']}　{r['language']}　"
                   f"{r.get('harm_category', '-')}　pack={r['policy_pack']}")
        out.append("")
        out.append(f"- goal：{r['goal']}")
        if "payoff" in r:
            out.append(f"- payoff：`{json.dumps(r['payoff'], ensure_ascii=False)}`")
        out.append(f"- intent：{r['intent']}")
        out.append("")
        for i, t in enumerate(r["turns"], 1):
            tag = ("（最终正当请求）"
                   if (i == len(r["turns"]) and r["kind"] == "alignment")
                   else "（收割轮）" if i == len(r["turns"]) else "")
            out.append(f"{i}. {tag}{t}")
        out.append("")
    (OUT_DIR / "spotcheck-20.md").write_text("\n".join(out), encoding="utf-8",
                                             newline="\n")


def main() -> int:
    rows = collect()
    sha = write_jsonl(rows)
    write_manifest(rows, sha)
    write_readme()
    write_spotcheck(rows)
    print(f"jailbreak.jsonl: 150 行，sha256={sha}")
    print(f"输出目录：{OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
