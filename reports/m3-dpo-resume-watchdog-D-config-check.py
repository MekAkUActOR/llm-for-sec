# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog D: config vs preregistration section 3, item by item.
Also recompute the mix composition split from the data itself.
CPU only, read-only.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
CFG = ROOT / "configs" / "m3-dpo-final.yaml"
DATA = ROOT / "data" / "lf" / "dpo_m3_final.jsonl"

# (cfg_key, expected, prereg_quote)
EXPECT = [
    ("stage", "dpo", "stage: dpo"),
    ("finetuning_type", "full", "finetuning_type: full"),
    ("template", "qwen3_nothink", "template: qwen3_nothink"),
    ("cutoff_len", 1024, "cutoff_len: 1024"),
    ("per_device_train_batch_size", 1, "bs1"),
    ("gradient_accumulation_steps", 16, "accum16"),
    ("learning_rate", 2.0e-6, "lr 2.0e-6"),
    ("lr_scheduler_type", "cosine", "cosine"),
    ("warmup_steps", 60, "warmup 60"),
    ("weight_decay", 0.0, "weight_decay 0.0"),
    ("optim", "adamw_bnb_8bit", "optim: adamw_bnb_8bit"),
    ("pref_loss", "sigmoid", "pref_loss: sigmoid"),
    ("pref_beta", 0.1, "pref_beta: 0.1"),
    ("num_train_epochs", 1, "1 epoch"),
    ("save_steps", 100, "save_steps 100"),
    ("save_total_limit", 5, "save_total_limit 5"),
    ("logging_steps", 5, "logging_steps 5"),
    ("dataset", "sec_dpo_m3_final", "dataset: sec_dpo_m3_final"),
    ("model_name_or_path", r"J:\Projects\llm_for_sec\checkpoints\soup-needlefix-a050",
     "start = soup-a050"),
    ("output_dir", r"J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo",
     "output = qwen3-06b-sec-m3-dpo"),
    ("bf16", True, "bf16: true"),
    ("gradient_checkpointing", False, "gradient_checkpointing: false"),
    ("do_train", True, "do_train: true"),
]


def parse_simple_yaml(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        s = line.split("#")[0].strip()
        if not s or ":" not in s:
            continue
        k, v = s.split(":", 1)
        k = k.strip()
        v = v.strip()
        if not k or not v:
            continue
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
            continue
        try:
            out[k] = int(v)
            continue
        except ValueError:
            pass
        try:
            out[k] = float(v)
            continue
        except ValueError:
            pass
        out[k] = v
    return out


def main() -> int:
    cfg = parse_simple_yaml(CFG.read_text(encoding="utf-8-sig"))
    rows = []
    n_mismatch = 0
    for key, exp, quote in EXPECT:
        got = cfg.get(key, "<ABSENT>")
        ok = got == exp
        if not ok:
            n_mismatch += 1
        rows.append({"key": key, "expected": exp, "config": got, "match": ok,
                     "prereg_quote": quote})
    extra = sorted(set(cfg) - {k for k, _, _ in EXPECT})

    # --- recompute mix composition from the data itself ---
    comp = Counter()
    pack = Counter()
    dpo_class = Counter()
    lang = Counter()
    with DATA.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            comp[str(o.get("pack", "<none>"))] += 1
            dpo_class[str(o.get("dpo_class", "<none>"))] += 1
            lang[str(o.get("lang", "<none>"))] += 1
            if "src_task" in o:
                pass
    res = {
        "config_path": str(CFG),
        "items": rows,
        "n_mismatch": n_mismatch,
        "config_keys_not_in_prereg_checklist": extra,
        "mix_pack_counter": dict(comp.most_common()),
        "mix_dpo_class_counter": dict(dpo_class.most_common(20)),
        "mix_lang_counter": dict(lang.most_common(10)),
    }
    (R / "m3-dpo-resume-watchdog-D-config-check.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{'key':32} {'prereg/expected':38} {'config':38} match")
    for r in rows:
        flag = "OK" if r["match"] else "*** MISMATCH ***"
        print(f"{r['key']:32} {str(r['expected']):38} {str(r['config']):38} {flag}")
    print("\nn_mismatch =", n_mismatch)
    print("extra config keys (not in checklist):", extra)
    print("\npack counter:", dict(comp.most_common()))
    print("dpo_class counter:", dict(dpo_class.most_common(20)))
    print("lang:", dict(lang.most_common(10)))
    print("WROTE", R / "m3-dpo-resume-watchdog-D-config-check.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
