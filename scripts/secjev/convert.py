# -*- coding: utf-8 -*-
"""sec-jev 数据转换：四源语料 → (prompt, 决策标签) 蒸馏对。

标签 = 四组槽位（verdict/action/finding/confidence，secjev-branch-brief §三）。
源与规则（全部 append-only 登记）：
  r6-paired 6000：id 尾缀 -b→(benign,comply,no-finding) / -m→(risk,refuse,harmful-intent)；
    amb 行（p16-R6A-*，键 conv_ref/conv_del）→ 两行均 (ambiguous,deflect,insufficient-context)
  r3-benign 2736：(benign,comply,no-finding,high)
  r3-malicious 2880：(risk,refuse,harmful-intent,high)（finding 粗粒度登记）
  m4-base 抽 10000（seed 固定）：chosen 内 VERDICT JSON 原生解析（零推导）；
    无 VERDICT 行按 dpo_class 回退：refusal_quality→(risk,refuse) 其余跳过
输出：data/secjev/decisions.jsonl + 决策分布登记（stdout + manifest）
"""
import json
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "secjev" / "decisions.jsonl"
VERDICT_RE = re.compile(r"VERDICT:\s*(\{.*\})\s*$", re.S)

A_SET = {"comply", "refuse", "clarify", "deflect", "escalate"}
V_SET = {"benign", "risk", "ambiguous", "malformed", "out-of-scope"}
F_SET = {"insufficient-context", "harmful-intent", "dual-use", "credential-risk",
         "policy-violation", "authorization-missing", "scope-exceeded", "no-finding"}


def load(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def m4_labels(chosen_text):
    """m4 VERDICT 原生解析（勘误 v2：m4 的 verdict 字段=动作语义值，弃用；用 action 映射）。"""
    m = VERDICT_RE.search(chosen_text)
    if not m:
        return None
    try:
        v = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    a = v.get("action", "")
    MAP = {"refuse": "risk", "answer": "benign", "propose": "benign", "report": "benign",
           "comply": "benign", "clarify": "ambiguous", "deflect": "ambiguous", "escalate": "ambiguous"}
    if a not in MAP:
        return None
    verdict = MAP[a]
    act = {"answer": "comply", "propose": "comply", "report": "comply"}.get(a, a)
    fs = v.get("findings", [])
    finding = fs[0] if fs and fs[0] in F_SET else ("no-finding" if act == "comply" else "policy-violation")
    conf = v.get("confidence", 0.8)
    c = "high" if conf >= 0.75 else ("medium" if conf >= 0.45 else "low")
    return verdict, act, finding, c


def main():
    rng = random.Random("secjev-20261020")
    out, dist = [], Counter()
    skipped = Counter()

    def emit(rid, conv, v, a, f, c, src):
        out.append({"id": rid, "conversations": conv, "decision":
                    {"verdict": v, "action": a, "finding": f, "confidence": c}, "src": src})
        dist[(v, a, f, c)] += 1

    # r6-paired（勘误 v2：R6A 行=标准键 conversations/chosen，id 尾缀 -r/-d，弃 conv_ref 假设）
    for r in load(ROOT / "data/dpo/p16-calibration-r6/p16_r6_paired.jsonl"):
        if "R6A" in r["id"]:
            emit(r["id"], r["conversations"], "ambiguous", "deflect", "insufficient-context", "high", "r6-amb")
        elif r["id"].endswith("-b"):
            emit(r["id"], r["conversations"], "benign", "comply", "no-finding", "high", "r6-bm")
        elif r["id"].endswith("-m"):
            emit(r["id"], r["conversations"], "risk", "refuse", "harmful-intent", "high", "r6-bm")

    # r3
    for r in load(ROOT / "data/dpo/p16-calibration-r3/p16_benign_release.jsonl"):
        emit(r["id"], r["conversations"], "benign", "comply", "no-finding", "high", "r3-ben")
    for r in load(ROOT / "data/dpo/p16-calibration-r3/p16_malicious_honest.jsonl"):
        emit(r["id"], r["conversations"], "risk", "refuse", "harmful-intent", "high", "r3-mal")

    # m4 抽样 10K
    m4 = load(ROOT / "data/m4-run/dpo_m4_capfix.jsonl")
    rng.shuffle(m4)
    kept = 0
    for r in m4:
        if kept >= 10000:
            break
        lab = m4_labels(r["chosen"]["value"])
        if lab is None:
            if r.get("dpo_class") == "refusal_quality":
                emit(r["id"], r["conversations"], "risk", "refuse", "policy-violation", "high", "m4-fallback")
                kept += 1
            else:
                skipped["m4-no-verdict"] += 1
            continue
        emit(r["id"], r["conversations"], lab[0], lab[1], lab[2], lab[3], "m4-native")
        kept += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ids = [r["id"] for r in out]
    assert len(set(ids)) == len(ids), "id 重复"
    prompts = [json.dumps(r["conversations"], ensure_ascii=False, sort_keys=True) for r in out]
    print(f"CONVERT-SECJEV=OK rows={len(out)} id_unique={len(set(ids))} prompt_dup={len(prompts)-len(set(prompts))}")
    print("skipped:", dict(skipped))
    for (v, a, f, c), n in dist.most_common(12):
        print(f"  {v:10s} {a:9s} {f:22s} {c:6s} {n}")
    mf = ROOT / "data" / "secjev" / "manifest.json"
    mf.write_text(json.dumps({
        "rows": len(out), "dist": {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in dist.items()},
        "skipped": dict(skipped), "seed": "secjev-20261020",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"manifest -> {mf}")


if __name__ == "__main__":
    main()
