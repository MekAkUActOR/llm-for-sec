# -*- coding: utf-8 -*-
"""Generate M6 training configs (m6-train-config schema) for smoke and v1.

Usage:
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_build_train_config.py --which smoke
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_build_train_config.py --which v1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

COMMON = {
    "m6_config_version": "0.3.7",
    "base": {
        "model_name_or_path": "checkpoints/qwen3-06b-sec-m5a-dpo-r5",
        "dtype": "bf16",
        "frozen": True,
    },
    "render": {
        "protocol": "dsh-protocol/0.1",
        "chat_template": True,
        "judgment_text": False,
        "window_tokens": 4096,
        "truncation": {"policy": "head-tail", "head_tokens": 512,
                       "tail_tokens": 3584},
        "token_char_map": True,
        "renderer_module": "scripts/m6_render.py",
    },
    "probe": {
        "tapped_layers": [4, 12, 20, 24, 28],
        "token_layers": [12, 28],
        "trunk": {"type": "ln-linear-gelu", "in_dim": 10240, "hidden_dim": 1024},
        "heads": {
            "T1": {"type": "seq-mlp", "dims": [1024, 256, 2], "classes": 2},
            "T2": {"type": "seq-mlp", "dims": [1024, 256, 2], "classes": 2},
            "T3": {"type": "seq-mlp", "dims": [1024, 256, 2], "classes": 2},
            "T4": {"type": "pii-dual",
                   "doc": {"type": "seq-mlp", "dims": [1024, 256, 2], "classes": 2},
                   "bio": {"type": "token-bio", "dims": [2048, 512, 23],
                            "entity_types": 11, "span_merge": "bio-consecutive"},
                   "input": "L12+L28-per-token-concat",
                   "flag_rule": "doc_head_or_spans_nonempty"},
            "T5": {"type": "seq-mlp", "dims": [1024, 256, 2], "classes": 2},
            "T6": {"type": "seq-mlp", "dims": [1024, 256, 3], "classes": 3},
        },
        "aux_ood": {"mechanism": "mahalanobis", "classes": ["benign", "attack"],
                     "feature": "trunk_output", "fit_on": "train", "lambda": 0.1},
        "loss": {"task_weights": {}, "bio_weight": 2.0, "bio_pos_weight": 15.0,
                  "label_masking": True},
    },
}

SMOKE = {
    **COMMON,
    "run_id": "m6-smoke",
    "data": {
        # smoke: direct patterns (manifest not built yet); schema deviation
        # noted -- production v1 uses the frozen manifest
        "train_patterns": ["reports/m6/smoke_v2/train.jsonl"],
        "dev_patterns": ["reports/m6/smoke_v2/dev.jsonl"],
        "prefix_rows": "exclude",
        "seed": 42,
    },
    "train": {
        "max_epochs": 3, "learning_rate": 1.0e-3, "optimizer": "adamw",
        "lr_scheduler_type": "cosine", "warmup_ratio": 0.05,
        "per_device_batch_size": 64, "weight_decay": 0.01, "grad_clip": 1.0,
        "seed": 42, "early_stop_patience": 1,
        "bio_max_tokens": 1024, "extract_batch_rows": 16,
    },
    "output_dir": "checkpoints/m6-smoke3",
    "notes": "pipeline smoke (task-7): tiny synthetic m6-sample data",
}

V1 = {
    **COMMON,
    "run_id": "m6-v1",
    "data": {
        "manifest": "data/m6/manifest.json",
        "train_splits": ["train"],
        "val_split": "dev",
        "prefix_rows": "exclude",  # ADR mainline; "include" ablation ready
        "seed": 42,
    },
    "train": {
        "max_epochs": 3, "learning_rate": 1.0e-3, "optimizer": "adamw",
        "lr_scheduler_type": "cosine", "warmup_ratio": 0.05,
        "per_device_batch_size": 256, "weight_decay": 0.01, "grad_clip": 1.0,
        "seed": 42, "early_stop_patience": 1,
        "bio_max_tokens": 1024, "extract_batch_rows": 16,
    },
    "thresholds_ref": "checkpoints/m6-v1/calib.json",
    "eval": {
        "gates": {"recall_min": 0.95, "fpr_max": 0.005,
                   "challenge_fpr_max": 0.001, "ood_pass_min": 0.95},
        "suites": ["heldout", "challenge", "ood"],
    },
    "output_dir": "checkpoints/m6-v1",
    "notes": "v1 mainline: frozen backbone + feature cache (ADR-1 D2/D10)",
}

WHICH = {"smoke": SMOKE, "v1": V1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", choices=list(WHICH), required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cfg = WHICH[args.which]
    out = Path(args.out) if args.out else REPO / "configs" / f"m6-{args.which}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
