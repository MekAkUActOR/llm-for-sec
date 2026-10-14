r"""分类器 wgm-only 纯切分复评（诚实口径：heldout 只含 wgm 人标行）。

背景：train_pool_classifier.py 的 heldout 从全池洗牌抽样（wgm+sp+bench
混合）——指标 0.941/0.940 是混合分布口径。本脚本按同一 seed 重建切分，
仅取 heldout 中 wgm 源行评测（独立同分布于人标测试面）。
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import joblib  # noqa: E402

from train_pool_classifier import SEED, load_train_data  # noqa: E402


def load_train_data_tagged():
    """带源标签的数据（wgm 行可辨识）。"""
    import csv
    import json

    import pyarrow.parquet as pq

    M2 = ROOT / "data" / "corpora" / "raw" / "m2"
    rows = []
    for r in pq.read_table(M2 / "wildguardmix" / "train" /
                           "wildguard_train.parquet").to_pylist():
        lab = r.get("prompt_harm_label")
        if lab in ("harmful", "unharmful"):
            rows.append((r["prompt"], 1 if lab == "harmful" else 0, "wgm"))
    sp_atk = json.load(open(M2 / "safety-prompts" /
                            "instruction_attack_scenarios.json",
                            encoding="utf-8"))
    for fam, items in sp_atk.items():
        for it in items:
            rows.append((it["prompt"] if isinstance(it, dict) else str(it),
                         1, "sp"))
    sp_typ = json.load(open(M2 / "safety-prompts" /
                            "typical_safety_scenarios.json",
                            encoding="utf-8"))
    for fam, items in sp_typ.items():
        for it in items:
            rows.append((it["prompt"] if isinstance(it, dict) else str(it),
                         0, "sp"))
    with open(M2 / "advbench" / "harmful_behaviors.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["goal"], 1, "bench"))
    with open(M2 / "strongreject" / "strongreject_dataset.csv",
              encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["forbidden_prompt"], 1, "bench"))
    for r in pq.read_table(M2 / "maliciousinstruct" /
                           "train-00000-of-00001.parquet").to_pylist():
        rows.append((r["prompt"], 1, "bench"))
    with open(M2 / "or-bench" / "or-bench-hard-1k.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["prompt"], 0, "bench"))
    with open(M2 / "xstest" / "xstest_prompts.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["prompt"], 1 if r["label"] == "unsafe" else 0,
                         "bench"))
    return rows


def main() -> int:
    rows = load_train_data_tagged()
    # 与训练脚本同 seed 同洗牌 → 同 heldout 切分（可复现）
    rng = random.Random(SEED)
    rng.shuffle(rows)
    held = set(rng.sample(range(len(rows)), 5000))
    held_rows = [rows[i] for i in sorted(held)]
    train_rows = [r for i, r in enumerate(rows) if i not in held]
    # 训练集剔除 wgm 后重训？——不：复用已训模型（其训练集=同切分），
    # 只对 heldout 的 wgm 子集评测
    wgm_held = [r for r in held_rows if r[2] == "wgm"]
    print(f"heldout total={len(held_rows)} wgm-subset={len(wgm_held)}")

    b = joblib.load(ROOT / "data" / "models" / "classifier-v1" / "model.pkl")
    X = b["vectorizer"].transform([r[0] for r in wgm_held])
    pred = b["clf"].predict(X)
    y = [r[1] for r in wgm_held]
    tp = sum(1 for p, t in zip(pred, y) if p == 1 and t == 1)
    fp = sum(1 for p, t in zip(pred, y) if p == 1 and t == 0)
    fn = sum(1 for p, t in zip(pred, y) if p == 0 and t == 1)
    tn = sum(1 for p, t in zip(pred, y) if p == 0 and t == 0)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    acc = (tp + tn) / len(y)
    print(f"wgm-only heldout: acc={acc:.3f} precision={prec:.3f} "
          f"recall={rec:.3f} (n={len(y)}, pos={sum(y)})")
    out = ROOT / "data" / "models" / "classifier-v1" / "eval-wgm-only.json"
    out.write_text(__import__("json").dumps(
        {"n": len(y), "accuracy": round(acc, 4), "precision": round(prec, 4),
         "recall": round(rec, 4), "tp": tp, "fp": fp, "fn": fn, "tn": tn},
        indent=2), encoding="utf-8")
    print("PASS" if (prec >= 0.85 and rec >= 0.60) else "FAIL",
          "(target P>=0.85 / R>=0.60)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
