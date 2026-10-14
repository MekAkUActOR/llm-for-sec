# -*- coding: utf-8 -*-
"""判别轴审计（规则 33 §11.32 的强制门）：偏好训练发射**之前**必须通过。

回答两问：
  A. 门禁要读的每个行为维度，在训练对里**是不是判别轴**？
     —— 两侧都含 ≈100% ⇒ 共模 ⇒ DPO 零梯度。
  B. 每类的 chosen 长度中位是否**超过部署生成预算**？
     —— 超过 ⇒ 训练目标不可被产生 ⇒ 模型学到"被截断的模仿"。

★2026-10-06 两处**更正**（详见 docs/01 §11.35 规则 36 更正版、§11.36 规则 37）：

**A 类（重要）**：原版把"两侧都含"一律判为缺陷 ✗。但**若 prompt 本身就强制**
该维度（例："输出必须以 VERDICT 行结尾"），那么两侧都含是**正确行为** ✓，
DPO 只是**不负责强化它**而已 ⇒ 不得判为缺陷 ✗。
正确的门是：**只有当 prompt 未强制、而两侧仍都含时**，才是共模缺陷 ✓。
本版从 `conversations` 里读**真实 prompt**，逐对判定是否强制，据此分流。

**B 类（口径）**：原版用**字符**判预算 ✗。实测同一批数据字符↔token 比漂移 2 倍
（302 字符/158 token=1.9；770 字符/203 token=3.8）⇒ 字符口径不可靠 ✗
（规则 37.1）。本版**同时**报告 token 与字符，并以 **token** 作判定口径。

★并且：**B 类通过 ≠ 数据干净**。`carrier_inject_obedient` 的 chosen 中位 210 token
在 512 预算下不算超预算 ⇒ B 类**会放过它** ✗，但它 chosen/rejected 中位比 **4.12**
⇒ 仍然在教"长=好" ✗。**这类问题由 `audit_dpo_length_confounding.py`（规则 37）负责** ✓。
两道门互补，**都必须过**。

退出码：0 = 通过；1 = 有 A 类问题；2 = 有 B 类问题；3 = 两者皆有。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENIZER = (ROOT / ".cache" / "huggingface" / "hub"
             / "models--Qwen--Qwen3-0.6B-Base" / "snapshots"
             / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")

#: 门禁要读的契约维度（正则；命中即视为"该维度存在"）。
#: ★`parent`：该维度若只是**另一个维度的子键**，则它不构成独立判别轴 ——
#:   VERDICT 行是一个**原子格式块**，发它就必然带 `"action"`/`"verdict"` ✗
#:   ⇒ 不能把"两侧都含 action 键"单独判为共模缺陷（那是**假阳性** ✗）。
#:   子键的强制状态**继承父维度**。
DIMENSIONS = {
    "VERDICT 行": {"re": re.compile(r"VERDICT\s*[:：]"), "parent": None},
    "action 键": {"re": re.compile(r'"action"\s*:'), "parent": "VERDICT 行"},
    "verdict 键": {"re": re.compile(r'"verdict"\s*:'), "parent": "VERDICT 行"},
}

#: 部署生成预算（字符）。★留作历史对照；**判定口径已改为 token**（规则 37.1）。
DEFAULT_BUDGET_CHARS = 450
#: 部署生成预算（token）。96 是 baseline_eval.py 的 CLI 默认值，
#: 而 SFT 目标 p50 达 380、DPO chosen max 达 987 ⇒ 96 装不下（覆盖率 0%）。
DEFAULT_BUDGET_TOKENS = 512


def val(side) -> str:
    """chosen/rejected 可能是 dict{'from','value'} / str / list[dict]。"""
    if isinstance(side, dict):
        return str(side.get("value", ""))
    if isinstance(side, str):
        return side
    if isinstance(side, list):
        return "\n".join(
            str(m.get("value", m)) if isinstance(m, dict) else str(m) for m in side)
    return ""


def prompt_text(d: dict) -> str:
    """从 `conversations` 取**模型实际看到的提示**（system + human 侧）。

    ★这是 A 类能否正确判定的关键：不看 prompt 就无法区分
      "prompt 强制的合规行为" 与 "无对照的共模缺陷" ✗。
    """
    parts = []
    conv = d.get("conversations")
    if isinstance(conv, list):
        for m in conv:
            if isinstance(m, dict):
                role = m.get("from") or m.get("role")
                if role in ("system", "human", "user"):
                    parts.append(str(m.get("value") or m.get("content") or ""))
    for k in ("system", "instruction", "prompt"):
        v = d.get(k)
        if isinstance(v, str):
            parts.append(v)
    return "\n".join(parts)


def mandates(prompt: str, dim_name: str) -> bool:
    """prompt 是否**强制**该维度。"""
    if not prompt:
        return False
    # 维度名里的首个词（如 "VERDICT 行" → "VERDICT"）出现在 prompt 中即视为强制；
    # 另外认"必须以/最后一行/结尾"这类中文格式指令。
    head = dim_name.split()[0]
    if head and head in prompt:
        return True
    return any(k in prompt for k in ("必须以", "最后一行", "结尾", "输出格式"))


def main() -> int:
    ap = argparse.ArgumentParser(description="DPO 判别轴审计（规则 33，2026-10-06 更正版）")
    ap.add_argument("--data", default=str(ROOT / "data/lf/dpo_m3_final.jsonl"))
    ap.add_argument("--budget-chars", type=int, default=DEFAULT_BUDGET_CHARS,
                    help="历史字符口径，仅作对照展示")
    ap.add_argument("--budget-tokens", type=int, default=DEFAULT_BUDGET_TOKENS,
                    help="★判定口径（token）。96=旧 CLI 默认（装不下），512=数据分布内")
    ap.add_argument("--common-mode-threshold", type=float, default=0.95,
                    help="两侧都含某维度的比例 ≥ 此值即判为共模")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    p = Path(args.data)
    if not p.exists():
        print(f"AUDIT-DPO-AXES=ERROR 缺文件 {p}")
        return 4

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(TOKENIZER))
    ntok = lambda s: len(tok(s, add_special_tokens=False)["input_ids"])

    n = 0
    dim_both_mandated = Counter()      # 两侧都有 **且 prompt 强制** ⇒ 预期，不是缺陷
    dim_both_unmandated = Counter()    # 两侧都有 **且 prompt 未强制** ⇒ 真缺陷
    dim_any = Counter()
    per = defaultdict(lambda: {"n": 0, "tc": [], "tr": [], "lc": [], "longer": 0})

    for line in p.open(encoding="utf-8"):
        if not line.strip():
            continue
        d = json.loads(line)
        ch, rj = val(d.get("chosen")), val(d.get("rejected"))
        pr = prompt_text(d)
        cls = d.get("dpo_class", "?")
        n += 1
        for name, spec in DIMENSIONS.items():
            rx = spec["re"]
            hc, hr = bool(rx.search(ch)), bool(rx.search(rj))
            if hc and hr:
                # ★强制判定：维度自身被强制，**或**其父维度被强制
                #   （子键继承父格式块的强制状态 —— 见 DIMENSIONS 注释）
                par = spec.get("parent")
                man = mandates(pr, name) or (par is not None and mandates(pr, par))
                (dim_both_mandated if man else dim_both_unmandated)[name] += 1
            if hc or hr:
                dim_any[name] += 1
        g = per[cls]
        g["n"] += 1
        g["tc"].append(ntok(ch))
        g["tr"].append(ntok(rj))
        g["lc"].append(len(ch))
        g["longer"] += len(ch) > len(rj)

    print(f"=== 判别轴审计：{p.name}，{n} 对 ===")
    print(f"    共模判定线 = 两侧都含比例 ≥ {args.common_mode_threshold:.0%}")
    print(f"    ★A 类已按 prompt 是否强制分流（2026-10-06 更正）\n")

    a_problems, b_problems = [], []

    print("--- A. 契约维度是否受偏好保护（按 prompt 强制与否分流）---")
    print(f"    {'维度':<14} {'两侧都有':>9} {'其中prompt强制':>14} "
          f"{'未强制(真缺陷)':>15}  判定")
    for name in DIMENSIONS:
        man, unman, any_ = (dim_both_mandated[name], dim_both_unmandated[name],
                            dim_any[name])
        both = man + unman
        frac = both / n if n else 0.0
        ufrac = unman / n if n else 0.0
        par = DIMENSIONS[name].get("parent")
        if any_ == 0:
            verdict = "该维度在数据中不存在（无从判共模）"
        elif frac >= args.common_mode_threshold and ufrac < (1 - args.common_mode_threshold):
            why = f"自身或父维度（{par}）被 prompt 强制" if par else "prompt 强制"
            verdict = (f"共模但 **{why}**（{man}/{both}）⇒ 预期行为，"
                       f"DPO 不负责强化 ⇒ 非缺陷")
        elif ufrac >= (1 - args.common_mode_threshold):
            verdict = f"★共模且 prompt **未强制**（{unman}/{n}）⇒ 真缺陷"
            a_problems.append(
                f"D1 共模(未强制)：{name} 两侧都有且 prompt 未强制 "
                f"{unman}/{n} = {ufrac:.1%}")
        else:
            verdict = f"有判别信号（仅一侧 {any_ - both}/{n}）"
        print(f"    {name:<14} {both:>9} {man:>14} {unman:>15}  {verdict}")

    print(f"\n--- B. chosen 长度 vs 部署预算（★口径 = token，规则 37.1）---")
    print(f"    token 预算 = {args.budget_tokens}（历史字符口径 {args.budget_chars} 仅对照）")
    print(f"    {'dpo_class':<28} {'n':>6} {'tok中位':>8} {'rej':>6} {'比':>6} "
          f"{'更长':>7} {'字符中位':>9}  判定")
    for cls, g in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
        mc, mr = st.median(g["tc"]), st.median(g["tr"])
        ratio = mc / mr if mr else float("inf")
        char_med = st.median(g["lc"])
        over = mc > args.budget_tokens
        note = f"★chosen 超预算({args.budget_tokens} token)" if over else "ok"
        if over:
            b_problems.append(
                f"D2 超预算：{cls} chosen 中位 {mc:.0f} token > {args.budget_tokens}")
        print(f"    {cls:<28} {g['n']:>6} {mc:>8.0f} {mr:>6.0f} {ratio:>6.2f} "
              f"{g['longer']/g['n']*100:>6.1f}% {char_med:>9.0f}  {note}")

    print("\n--- 结论 ---")
    if not a_problems and not b_problems:
        print(f"AUDIT-DPO-AXES=PASS 无（未强制下的）共模、无 token 超预算")
        print("  ★提醒：本门通过**不等于**数据干净 —— 长度混杂由")
        print("    `audit_dpo_length_confounding.py`（规则 37）单独把关，两道门都要过。")
        rc = 0
    else:
        for x in a_problems:
            print(f"  ✗ {x}")
        for x in b_problems:
            print(f"  ✗ {x}")
        rc = 3 if (a_problems and b_problems) else (1 if a_problems else 2)
        print(f"AUDIT-DPO-AXES=FAIL (A类 {len(a_problems)}，B类 {len(b_problems)}) rc={rc}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "data": str(p), "n": n,
            "budget_tokens": args.budget_tokens,
            "budget_chars_legacy": args.budget_chars,
            "common_mode": {
                k: {"both": dim_both_mandated[k] + dim_both_unmandated[k],
                    "both_prompt_mandated": dim_both_mandated[k],
                    "both_prompt_unmandated": dim_both_unmandated[k],
                    "parent": DIMENSIONS[k].get("parent"),
                    "any": dim_any[k]} for k in DIMENSIONS},
            "a_problems": a_problems, "b_problems": b_problems, "rc": rc,
            "note": ("A 类已于 2026-10-06 按 prompt 强制与否分流：prompt 强制的"
                     "共模是预期行为，不是缺陷。B 类口径已改为 token。"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  明细已写 {args.json_out}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
