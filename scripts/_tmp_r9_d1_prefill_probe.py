# -*- coding: utf-8 -*-
"""_tmp_r9_d1_prefill_probe.py — D1 诊断探针（r10 设计决定性问题；Lead 2026-10-20 17:1x 规格）。

问题：空 think 预填能否在推理时恢复契约输出（VERDICT JSON）？
设计（单条件 + 门禁自对照）：
  - 模型 = checkpoints\\qwen3-8b-sec-m5a-dpo-r9-merged（主臂权重，同 gate 对照）
  - 数据 = data\\heldout\\v0.7-jailbreak\\jailbreak.jsonl 门禁同选择（all + exclude-holdout = 110 对话）
  - 采样 = random.Random(20261020).sample(sorted(ids), 80)（终轮；只读复用门禁 jb-resp）
  - 渲染 = 门禁同款 Renderer.build（用门禁自录的 1..k-1 轮生成文本回填 → 与 gate 终轮
    prompt 逐 token 同源），追加预填 PREFILL = "<think>\\n\\n</think>\\n\\n"（enc 特殊 token 解析）
  - 生成 = GREEDY 恒定（do_sample=False）、max_new 512、pad=eos（与门禁 make_generator 同款）
  - 指标：strict = _extract_structured(text) 非 None（VERDICT 正则 + JSON 可解析 + action 合法；
    Lead 指定主口径）；loose = strict 或 ACTION_FIELD 命中（= 门禁 contract 字段口径，与
    主臂 0/110 直接可比）
  - 对照 = 主臂 gate 实测 final-turn contract 0/110（同权重无预填；渲染同源）
产物：reports/d1-prefill-probe-r9.json（PREFLIGHT 防覆写）+ stdout 简报。
非仪器族（_tmp 前缀一次性诊断；不触 promptfmt/任何冻结件）。
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from probe_jailbreak import (Renderer, load_suite, select,  # noqa: E402
                             make_generator)
from score_heldout_v2 import _extract_structured, ACTION_FIELD  # noqa: E402

MODEL = r"checkpoints\qwen3-8b-sec-m5a-dpo-r9-merged"
DATA = ROOT / "data" / "heldout" / "v0.7-jailbreak" / "jailbreak.jsonl"
GATE_RESP = ROOT / "reports" / "jb-resp-m5a-dpo-r9-v0.7-full.jsonl"
OUT = ROOT / "reports" / "d1-prefill-probe-r9.json"
SEED = 20261020
N_SAMPLE = 80
PREFILL = "<think>\n\n</think>\n\n"


def main() -> int:
    if OUT.exists():
        print(f"[preflight] 产物已存在，拒绝覆写：{OUT}")
        return 4
    rows = select(load_suite(DATA), "all", True, None)
    by_row = {r["id"]: r for r in rows}
    by_id: dict[str, list[dict]] = {}
    for line in GATE_RESP.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        by_id.setdefault(rec["dialogue_id"], []).append(rec)
    for recs in by_id.values():
        recs.sort(key=lambda x: x["turn_i"])
    ids = sorted(by_id)
    assert set(ids) <= set(by_row), "resp 含套件外 id"
    sample = random.Random(SEED).sample(ids, N_SAMPLE)
    n_atk = sum(1 for i in sample if by_row[i]["kind"] == "robustness")
    print(f"D1 sample: {N_SAMPLE}/{len(ids)} 对话（atk={n_atk} / ben={N_SAMPLE - n_atk}；seed={SEED}）",
          flush=True)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16, device_map="cuda")
    enc = lambda s: tok(s, add_special_tokens=False)["input_ids"]  # noqa: E731
    renderer = Renderer(enc)
    generate = make_generator(model, tok, torch)
    prefill_ids = enc(PREFILL)
    print(f"prefill token ids: {prefill_ids}", flush=True)

    t0 = time.time()
    items = []
    n_prompt_mismatch = 0
    for i, did in enumerate(sample):
        row = by_row[did]
        recs = by_id[did]
        gens = [r["text"] for r in recs[:-1]]      # 门禁自录 1..k-1 轮生成
        prompt = renderer.build(row["policy_pack"], row["language"],
                                row["turns"], gens) + prefill_ids
        # 保真校验：去预填后长度应与门禁自录 prompt_len 逐 token 一致
        if len(prompt) - len(prefill_ids) != recs[-1]["prompt_len"]:
            n_prompt_mismatch += 1
            print(f"[fidelity-WARN] {did}: rebuilt={len(prompt) - len(prefill_ids)} "
                  f"gate={recs[-1]['prompt_len']}", flush=True)
        text, _gids, fin, ntok = generate(prompt, 512)
        strict = _extract_structured(text) is not None
        loose = strict or ACTION_FIELD.search(text) is not None
        items.append({"dialogue_id": did, "kind": row["kind"],
                      "final_turn": recs[-1]["turn_i"], "prompt_len": len(prompt),
                      "text": text, "finish_reason": fin, "new_tokens": ntok,
                      "contract_strict": strict, "contract_loose": loose,
                      "gate_contract_same_dialogue": recs[-1]["contract"]})
        print(f"[{i + 1}/{N_SAMPLE}] {did} strict={strict} loose={loose} "
              f"fin={fin} ntok={ntok}", flush=True)

    k_s = sum(1 for x in items if x["contract_strict"])
    k_l = sum(1 for x in items if x["contract_loose"])
    k_s_atk = sum(1 for x in items if x["contract_strict"]
                  and x["kind"] == "robustness")
    fin_hist: dict[str, int] = {}
    for x in items:
        fin_hist[x["finish_reason"]] = fin_hist.get(x["finish_reason"], 0) + 1
    out = {
        "probe": "D1-prefill（空 think 预填推理时契约恢复；r10 设计决定性诊断）",
        "model": MODEL, "seed": SEED, "n_sample": N_SAMPLE,
        "sample_atk": n_atk, "sample_ben": N_SAMPLE - n_atk,
        "prefill": PREFILL, "prefill_token_ids": prefill_ids,
        "generation": "greedy do_sample=False, max_new=512, pad=eos（与门禁同款）",
        "rendering": ("Renderer.build 门禁同款（回填门禁自录 1..k-1 轮生成 → 终轮 prompt "
                      "逐 token 同源）+ 追加预填；唯一变量 = 预填"),
        "control": ("主臂 gate final-turn contract（同权重无预填，同渲染源）= "
                    "0/110（loose 口径，jb-scored tiered.contract.final_rate=0.0）"),
        "hit_rate_strict": {"k": k_s, "n": N_SAMPLE,
                            "rate": round(k_s / N_SAMPLE, 4)},
        "hit_rate_loose": {"k": k_l, "n": N_SAMPLE,
                           "rate": round(k_l / N_SAMPLE, 4)},
        "hit_rate_strict_atk_only": {"k": k_s_atk, "n": n_atk,
                                     "rate": round(k_s_atk / n_atk, 4)
                                     if n_atk else None},
        "prompt_rebuild_mismatches": n_prompt_mismatch,
        "finish_reason_hist": fin_hist,
        "elapsed_s": round(time.time() - t0, 1),
        "items": items,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"\nD1 RESULT: strict {k_s}/{N_SAMPLE} = {k_s / N_SAMPLE:.2%} | "
          f"loose {k_l}/{N_SAMPLE} = {k_l / N_SAMPLE:.2%} | "
          f"atk-only strict {k_s_atk}/{n_atk}", flush=True)
    print(f"control = gate 0/110 (loose, no prefill, same weights/rendering)",
          flush=True)
    print(f"wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
