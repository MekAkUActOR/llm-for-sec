# -*- coding: utf-8 -*-
"""M6 score 分布图（qa-m6，arch 基线条件 5）：逐套件 × 逐任务 正/负叠加直方图 + AUC 热图。

用法：
  .venv\\Scripts\\python.exe -X utf8 scripts\\m6_dist_plots.py \\
      --scope frozen --out-dir reports/m6/plots/baseline-v0-frozen
数据源：reports/m6/preds/baseline-*-out.jsonl（或 m6_acceptance per-item.jsonl）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m6_metrics as M  # noqa: E402
from m6_acceptance import load_redteam, load_mapped, parse_infer_output  # noqa: E402

TASKS = M.TASKS
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def collect_rows(scope: str) -> list[dict]:
    rows: list[dict] = []
    rt = load_redteam(Path("reports/m6/redteam/redteam-v1.jsonl"))
    fz = load_mapped()
    if scope == "frozen":
        preds = parse_infer_output(Path("reports/m6/preds/baseline-v0-out.jsonl"))
        for r in rt + fz:
            r["pred"] = preds[r["id"]]
            rows.append(r)
    else:  # full：frozen + data/m6 三切分
        preds = parse_infer_output(Path("reports/m6/preds/baseline-v0-out.jsonl"))
        for r in rt + fz:
            r["pred"] = preds[r["id"]]
            rows.append(r)
        from m6_acceptance import load_m6_splits
        sp = load_m6_splits(Path("data/m6"))
        for split in ["heldout", "challenge", "ood"]:
            p = Path(f"reports/m6/preds/baseline-{split}-out.jsonl")
            if not p.exists():
                continue
            preds = parse_infer_output(p)
            for r in sp.get(split, []):
                r["pred"] = preds[r["id"]]
                rows.append(r)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="frozen", choices=["frozen", "full"])
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"reports/m6/plots/baseline-v0-{args.scope}")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = collect_rows(args.scope)
    suites: dict[str, list[dict]] = {}
    for r in rows:
        suites.setdefault(r["source"], []).append(r)
    print(f"{len(rows)} 行，{len(suites)} 套件：{sorted(suites)}")

    # 逐任务大图（子图=套件，正/负分布叠加）
    for t in TASKS:
        names = sorted(s for s in suites
                       if any(t in r["labels"] for r in suites[s] if not r.get("ambiguous")))
        if not names:
            continue
        ncols = 4
        nrows = (len(names) + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 2.8 * nrows), squeeze=False)
        fig.suptitle(f"baseline-v0 score 分布 · {t}（红=正例 蓝=负例；竖线=0.5 参考切）", fontsize=13)
        for i, s in enumerate(names):
            ax = axes[i // ncols][i % ncols]
            pos = [r["pred"]["tasks"][t]["score"] for r in suites[s]
                   if not r.get("ambiguous") and r["labels"].get(t) == 1]
            neg = [r["pred"]["tasks"][t]["score"] for r in suites[s]
                   if not r.get("ambiguous") and r["labels"].get(t) == 0]
            bins = np.linspace(0, 1, 26)
            if neg:
                ax.hist(neg, bins=bins, color="#4C72B0", alpha=0.6, label=f"neg n={len(neg)}")
            if pos:
                ax.hist(pos, bins=bins, color="#C44E52", alpha=0.6, label=f"pos n={len(pos)}")
            auc = M  # placeholder
            from m6_acceptance import _auc
            a = _auc(pos, neg)
            ax.axvline(0.5, color="gray", ls="--", lw=0.8)
            ax.set_title(f"{s}" + (f" AUC={a:.2f}" if a is not None else ""), fontsize=9)
            ax.legend(fontsize=7)
            ax.set_xlim(0, 1)
        for j in range(len(names), nrows * ncols):
            axes[j // ncols][j % ncols].axis("off")
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        fig.savefig(out_dir / f"dist-{t}.png", dpi=110)
        plt.close(fig)
        print(f"  {t}: {len(names)} 套件子图 -> dist-{t}.png")

    # AUC 热图（套件×任务）
    mat = np.full((len(suites), len(TASKS)), np.nan)
    names = sorted(suites)
    for i, s in enumerate(names):
        for j, t in enumerate(TASKS):
            pos = [r["pred"]["tasks"][t]["score"] for r in suites[s]
                   if not r.get("ambiguous") and r["labels"].get(t) == 1]
            neg = [r["pred"]["tasks"][t]["score"] for r in suites[s]
                   if not r.get("ambiguous") and r["labels"].get(t) == 0]
            from m6_acceptance import _auc
            mat[i, j] = _auc(pos, neg) if (pos and neg) else np.nan
    fig, ax = plt.subplots(figsize=(7, 0.45 * len(names) + 1.5))
    im = ax.imshow(mat, cmap="RdYlGn", vmin=0.3, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(TASKS)), TASKS)
    ax.set_yticks(range(len(names)), names, fontsize=8)
    for i in range(len(names)):
        for j in range(len(TASKS)):
            if not np.isnan(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:.2f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, shrink=0.8, label="ROC-AUC")
    ax.set_title("baseline-v0 逐套件 × 任务 ROC-AUC（NaN=该格无正负对）", fontsize=11)
    fig.tight_layout()
    fig.savefig(out_dir / "auc-heatmap.png", dpi=130)
    plt.close(fig)
    print(f"  AUC 热图 -> auc-heatmap.png")
    print(f"完成 -> {out_dir}")


if __name__ == "__main__":
    main()
