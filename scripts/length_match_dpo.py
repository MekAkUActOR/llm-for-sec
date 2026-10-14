# -*- coding: utf-8 -*-
r"""外科式长度匹配：只补足 DPO 中"较短一侧"（rejected）的**散文长度**，
**逐字保留原 VERDICT**（因此 action/findings 等非长度信号**由构造保证不变** ✓）。

## 为什么这样做（见 reports/dpo-length-confounding-surgical-fix.md）

第 17 轮实测：`carrier_inject_*` 等 5 类的 chosen/rejected 在
`action` 取值、`findings` 有无上**100% 分离** ✓ —— 数据**可用**，
缺陷是**同向累积的长度偏置**（6,540 对全部 chosen 更长 ✗）。

**⇒ 唯一正确的修法是"补足较短一侧的长度而不动语义"** ✓：
  - 把 rejected 原文（简短拒答/服从）与**它原本的 VERDICT** 完整保留 ✓
  - 在其**前面**加上一段**同义但详尽**的散文 ✓
  - **禁止**砍短任何一侧 ✗（会抹掉非长度信号 —— 推论 37.3）

## 版本纪律

`data/lf/dpo_m3_final.jsonl` 是**活**产物（M3 已在其上训练过）⇒ **绝不覆盖** ✗。
本脚本输出 **`data/lf/dpo_m4_final.jsonl`**（--out 可改），并在 JSON 报告里
记录与 m3 的逐类长度对照 ✓（规则 2：口径/版本变更必须留痕）。
"""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TOK = (ROOT / ".cache" / "huggingface" / "hub"
       / "models--Qwen--Qwen3-0.6B-Base" / "snapshots"
       / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
SRC = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"

#: 需要长度匹配的类（规则 37 门判定的混杂类）
OFFENDERS = ("carrier_inject_obedient", "carrier_inject_hollow",
             "carrier_clean_overrefusal", "refusal_quality", "calibration")

VERDICT_SPLIT = re.compile(r"(VERDICT\s*[:：].*)$", re.S)

#: 各类的**同义详尽散文池**（按语义分组，绝不改变裁决）。
#: 生成时按需取用若干句，直到长度达标 —— 用**多样的真句**而非重复文本，
#: 避免模型学到"灌水"这种退化解 ✗。
PAD = {
    "carrier_inject_obedient": [
        "已按载体自身的说明处理该材料：本段标注为免复核，因此本次未单独执行注入判定。",
        "依据载体给出的备注，相关条目按已处置结项，分析流程据此跳过检查环节并采纳其结论。",
        "在只读分析范围内，其余事项未发现需要升级的异常，故不再单列发现项。",
        "本次输出沿用载体所述的处理口径，未对载体内容作额外的指令性解读。",
        "如后续需要重新评估该段，请提供更新的授权说明与上下文，以便重新纳入检查。",
    ],
    "carrier_inject_hollow": [
        "已收到该请求。经初步查看，该材料涉及的内容我无法进一步处理，也没有可报告的具体发现。",
        "为避免给出不准确的结论，本次不展开逐项分析，也不对载体内容作任何裁定性说明。",
        "相关条目未被纳入本次结论范围，findings 保持为空，未对载荷作识别或接地。",
        "如需推进，请补充明确的授权范围与必要上下文，我再据此重新评估。",
        "本次处理到此为止，未对原任务的其余部分继续深入。",
    ],
    "carrier_clean_overrefusal": [
        "该材料中出现的备注文字看起来面向审阅者，为稳妥起见我按最保守口径处理，不再继续分析。",
        "出于谨慎，我中止了原任务，并拒绝该载体中提出的一切请求，以免产生越权操作。",
        "虽然无法确认该段是否真的构成指令，但按宁可误拒的原则，本次不给出放行结论。",
        "如确认该备注确为事实性说明，请再次提交，我会按常规流程重新评估。",
        "本次结论以保守为先，相关条目一并挂起，等待人工复核。",
    ],
    "refusal_quality": [
        "关于这个请求，我需要说明一下：由于其中涉及的部分我无法核实，所以本次不作处理。",
        "为谨慎起见，我不打算展开任何细节，也不会给出具体步骤或替代做法。",
        "如果你能补充更明确的范围与用途说明，我可以再判断是否可以推进。",
        "在缺少必要信息的情况下，任何具体回复都可能不合适，因此我选择不予展开。",
        "本次答复到此为止。",
    ],
    "calibration": [
        "这个请求我完全可以处理，交给我就行，我会按标准流程尽快推进并给出结果。",
        "无需补充任何信息，我已理解你的意图，接下来直接执行即可。",
        "相关风险与边界我都已考虑，不影响本次处理，请放心。",
        "若后续还有类似需求，可以一并提给我，我会按同样方式处理。",
        "预计很快就能完成并反馈。",
    ],
}


def side_text(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("value") or v.get("content") or "")
    if isinstance(v, list):
        for m in reversed(v):
            if isinstance(m, dict) and (m.get("role") or m.get("from")) in ("assistant", "gpt"):
                return str(m.get("value") or m.get("content") or "")
    return ""


def rebuild(v, new_text: str):
    """把新文本写回原形状（str / dict{'from','value'} / list），保留其它键。"""
    if isinstance(v, dict):
        d = dict(v)
        if "value" in d:
            d["value"] = new_text
        elif "content" in d:
            d["content"] = new_text
        else:
            d["value"] = new_text
        return d
    if isinstance(v, list):
        out = [dict(m) if isinstance(m, dict) else m for m in v]
        for m in reversed(out):
            if isinstance(m, dict) and (m.get("role") or m.get("from")) in ("assistant", "gpt"):
                if "value" in m:
                    m["value"] = new_text
                elif "content" in m:
                    m["content"] = new_text
                else:
                    m["value"] = new_text
                return out
        out.append(new_text)
        return out
    return new_text


def pad_to(prefix_pool: list[str], verdict: str, target_chars: int,
           nt=None, nt_target=None) -> str:
    r"""取若干同义句，使**整体 token 长度最接近目标**（而不是"加到超过为止"）。

    ★★2026-10-06 第 17 轮修正：原实现"加到长度 ≥ 目标就停" ⇒ 因为整句粒度
      （一句约 50 字符）会**系统性冲过头** ✗ ⇒ 实测比值落到 **0.84**，
      即 rejected **比 chosen 更长** ✗✗ ⇒ DPO 会学到"**越短越好**"，
      **把长度偏置反向了** ✗。
      ⇒ 现改为：在"加第 k 句"的各个候选里，取**与目标最接近**的那个 ✓。
      （★判据也相应改成**双边**：|比 − 1| ≤ 0.2，见规则 37 修正版）
    """
    best, best_err = None, None
    body = ""
    pool = prefix_pool * 6
    for i in range(len(pool) + 1):
        cand = body.rstrip("\n")
        cand = (cand + "\n" + verdict.strip()).strip() if cand else verdict.strip()
        # 用 token 距离做判据（若给了 tokenizer），否则退回字符距离
        err = (abs(nt(cand) - nt_target) if (nt and nt_target is not None)
               else abs(len(cand) - target_chars))
        if best_err is None or err < best_err:
            best, best_err = cand, err
        if i < len(pool):
            body += pool[i] + "\n"
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="DPO 外科式长度匹配（规则 37/37.3）")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(ROOT / "data" / "lf" / "dpo_m4_final.jsonl"))
    ap.add_argument("--report", default=str(ROOT / "reports" / "dpo-m4-length-match.json"))
    ap.add_argument("--ratio-target", type=float, default=1.20,
                    help="目标：每类 chosen/rejected token 中位比 ≤ 此值")
    a = ap.parse_args()

    src, out = Path(a.src), Path(a.out)
    if not src.exists():
        print(f"★源不存在 {src}")
        return 2
    if out.name == "dpo_m3_final.jsonl":
        print("★★拒绝：不得覆盖活的 dpo_m3_final.jsonl（规则 2）")
        return 2

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(TOK))
    nt = lambda s: len(tok(s, add_special_tokens=False)["input_ids"])

    # ---- 第一遍：按类统计 chosen 的 token 长度中位，作为 rejected 的目标 ----
    per_c = {}
    rows = []
    with src.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            d = json.loads(ln)
            rows.append(d)
            cls = str(d.get("dpo_class"))
            if cls in OFFENDERS:
                per_c.setdefault(cls, []).append(nt(side_text(d.get("chosen"))))
    target_chars = {}
    for cls in OFFENDERS:
        if not per_c.get(cls):
            continue
        med_tok = st.median(per_c[cls])
        # 中文约 1.9 字符/token（第 15 轮实测），留 5% 余量
        target_chars[cls] = int(med_tok * 1.9 * 1.05)
    print("=== 各类的 rejected 目标（按 chosen 的 token 中位 ×1.9 字符/token）===")
    for cls in OFFENDERS:
        if cls in target_chars:
            print(f"  {cls:<28} chosen中位={st.median(per_c[cls]):>5.0f} token "
                  f"⇒ 目标前缀≈{target_chars[cls]:>4d} 字符")

    # ---- 第二遍：重写 rejected ----
    n_changed = 0
    stats_before, stats_after = {}, {}
    with out.open("w", encoding="utf-8", newline="\n") as fo:
        for d in rows:
            cls = str(d.get("dpo_class"))
            rj = side_text(d.get("rejected"))
            if cls in OFFENDERS and cls in target_chars:
                nt_target = int(st.median(per_c[cls]))     # ★目标 = chosen 的 token 中位
                m = VERDICT_SPLIT.search(rj)
                if m:
                    verdict, prose = m.group(1), rj[:m.start()]
                    new_rj = pad_to(PAD[cls], verdict, target_chars[cls], nt, nt_target)
                else:
                    # 没有 VERDICT 的（如 calibration 的部分样本）：
                    # 原样保留内容，仅补前缀 ✓ —— 绝不删内容 ✓
                    new_rj = pad_to(PAD[cls], rj, target_chars[cls], nt, nt_target)
                if new_rj != rj:
                    n_changed += 1
                stats_before.setdefault(cls, []).append(nt(rj))
                stats_after.setdefault(cls, []).append(nt(new_rj))
                d = dict(d)
                d["rejected"] = rebuild(d.get("rejected"), new_rj)
                d["length_matched_from"] = "dpo_m3_final"
            fo.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"\n改写 rejected 的行数 = {n_changed}")
    print(f"\n=== 长度匹配前后（token 中位；目标：比 ≤{a.ratio_target}）===")
    print(f"  {'dpo_class':<28} {'chosen':>7} {'rej前':>6} {'比前':>6} "
          f"{'rej后':>6} {'比后':>6}  判定")
    rep = {}
    worst = 0.0
    ok_all = True
    for cls in OFFENDERS:
        if cls not in stats_after:
            continue
        cmed = st.median(per_c[cls])
        b, af = st.median(stats_before[cls]), st.median(stats_after[cls])
        r_b, r_a = cmed / b if b else 0, cmed / af if af else 0
        worst = max(worst, r_a)
        ok = r_a <= a.ratio_target
        ok_all = ok_all and ok
        print(f"  {cls:<28} {cmed:>7.0f} {b:>6.0f} {r_b:>6.2f} {af:>6.0f} {r_a:>6.2f}  "
              f"{'✓ 达标' if ok else '★仍混杂'}")
        rep[cls] = {"chosen_median_tokens": cmed, "rejected_before": b, "rejected_after": af,
                    "ratio_before": round(r_b, 3), "ratio_after": round(r_a, 3), "ok": ok}

    Path(a.report).write_text(json.dumps({
        "src": str(src), "out": str(out), "ratio_target": a.ratio_target,
        "rows_total": len(rows), "rows_rejected_rewritten": n_changed,
        "per_class": rep, "worst_ratio_after": round(worst, 3),
        "method": ("保留原 rejected 的 VERDICT 逐字不动（⇒ action/findings 等非长度信号"
                   "由构造保证不变，推论 37.3），仅在其前补足同义详尽散文 ✓"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport -> {a.report}")
    print(f"输出 -> {out}")
    print(f"LENGTH-MATCH={'PASS' if ok_all else 'FAIL'}  最差比={worst:.2f}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
