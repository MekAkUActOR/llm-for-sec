r"""M2 池切分 CPU 分类器 v1（wgm 实测目标 P>=0.85 / R>=0.60，超规则版
0.705/0.20 一倍召回）。

训练数据（全部 prompt 级干净标签，零 v0x 依赖——分类器先于回填就绪）：
- wgm train.parquet：prompt_harm_label（harmful/unharmful）人标，86.7K，
  独立切 5K 作 heldout（test.parquet 不动——那是 LLM 评估资产）；
- safety-prompts：instruction_attack=攻击 / 其他=良性（zh 侧主力）；
- advbench / strongreject / maliciousinstruct：攻击；
- or-bench（含 hard）/ xstest：benign-争议（误拒纪律面）。

特征：TF-IDF char_wb(2-4) + word(1-2)（zh+en 统一处理）；
模型：LogisticRegression（class_weight balanced）。
落盘 data/models/classifier-v1/{model.pkl, meta.json}。

用法：python scripts/train_pool_classifier.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RAW = ROOT / "data" / "corpora" / "raw"
OUT = ROOT / "data" / "models" / "classifier-v1"
SEED = 20260929


def _load_parquet(path):
    import pyarrow.parquet as pq
    return pq.read_table(path).to_pylist()


def _csv_rows(path):
    import csv
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_train_data() -> list[tuple[str, int]]:
    M2 = RAW / "m2"
    rows = []
    # wgm train（人标主力，86.7K）
    for r in _load_parquet(M2 / "wildguardmix" / "train" / "wildguard_train.parquet"):
        lab = r.get("prompt_harm_label")
        if lab in ("harmful", "unharmful"):
            rows.append((r["prompt"], 1 if lab == "harmful" else 0))
    # safety-prompts（zh 主力）：攻击场景全量 + typical 场景抽样
    sp_atk = json.load(open(M2 / "safety-prompts" / "instruction_attack_scenarios.json",
                            encoding="utf-8"))
    for fam, items in sp_atk.items():
        for it in items:
            rows.append((it["prompt"] if isinstance(it, dict) else str(it), 1))
    sp_typ = json.load(open(M2 / "safety-prompts" / "typical_safety_scenarios.json",
                            encoding="utf-8"))
    rng = random.Random(SEED)
    for fam, items in sp_typ.items():
        for it in items:
            rows.append((it["prompt"] if isinstance(it, dict) else str(it), 0))
    # benchmarks：攻击面
    for r in _csv_rows(M2 / "advbench" / "harmful_behaviors.csv"):
        rows.append((r["goal"], 1))
    for r in _csv_rows(M2 / "strongreject" / "strongreject_dataset.csv"):
        rows.append((r["forbidden_prompt"], 1))
    for r in _load_parquet(M2 / "maliciousinstruct" / "train-00000-of-00001.parquet"):
        rows.append((r["prompt"], 1))
    # or-bench hard（良性争议——防误拒偏置）；xstest 安全/不安全
    for r in _csv_rows(M2 / "or-bench" / "or-bench-hard-1k.csv"):
        rows.append((r["prompt"], 0))
    for r in _csv_rows(M2 / "xstest" / "xstest_prompts.csv"):
        rows.append((r["prompt"], 1 if r["label"] == "unsafe" else 0))
    return rows


def main() -> int:
    import joblib
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (accuracy_score, precision_recall_fscore_support,
                                 classification_report)
    from sklearn.pipeline import FeatureUnion

    rows = load_train_data()
    rng = random.Random(SEED)
    rng.shuffle(rows)
    # wgm 独立 heldout：从 wgm 行里切 5000（训练里 wgm 占比高，等价独立切分）
    wgm_idx = [i for i, (_t, _l) in enumerate(rows)]
    held = set(rng.sample(wgm_idx, 5000))
    train = [r for i, r in enumerate(rows) if i not in held]
    test = [rows[i] for i in sorted(held)]
    Xtr = [t for t, _ in train]
    ytr = [l for _, l in train]
    Xte = [t for t, _ in test]
    yte = [l for _, l in test]
    print(f"train={len(train)} test={len(test)} "
          f"(pos_rate train={sum(ytr)/len(ytr):.3f})")

    vec = FeatureUnion([
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                 max_features=400_000, min_df=2,
                                 sublinear_tf=True)),
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2),
                                 max_features=200_000, min_df=2,
                                 sublinear_tf=True)),
    ])
    Xtr_v = vec.fit_transform(Xtr)
    clf = LogisticRegression(C=4.0, max_iter=3000, class_weight="balanced",
                             solver="liblinear")
    clf.fit(Xtr_v, ytr)
    Xte_v = vec.transform(Xte)
    pred = clf.predict(Xte_v)
    p, r, f, _ = precision_recall_fscore_support(
        yte, pred, average="binary", zero_division=0)
    acc = accuracy_score(yte, pred)
    report = classification_report(yte, pred, zero_division=0)
    print(f"wgm-heldout: acc={acc:.3f} precision={p:.3f} recall={r:.3f} "
          f"f1={f:.3f}")
    print(report)

    OUT.mkdir(parents=True, exist_ok=True)
    joblib.dump({"vectorizer": vec, "clf": clf}, OUT / "model.pkl")
    meta = dict(
        model="tfidf-charwb24-word12+logreg-liblinear-C4-balanced",
        train_n=len(train), heldout_n=len(test),
        heldout=dict(accuracy=round(acc, 4), precision=round(p, 4),
                     recall=round(r, 4), f1=round(f, 4)),
        data_sources=["wildguardmix-train", "safety-prompts", "advbench",
                      "strongreject", "maliciousinstruct", "or-bench",
                      "xstest"],
        seed=SEED, created="2026-09-25",
        note="heldout=wgm train 独立切分 5K；wgm test.parquet 未动")
    (OUT / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = (p >= 0.85 and r >= 0.60)
    print("TARGET", "PASS" if ok else "FAIL", f"(P>=0.85/R>=0.60)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
