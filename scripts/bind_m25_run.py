#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""m25-full 运行的「数据绑定」记录（可复算 lineage 证据）。

动机：训练启动时**没有任何记录绑定训练集的 sha256**——只有散文里提到
`sft_m25.jsonl`。数据卡对 manifest 做了"语料态绑定"，训练侧却是空白：
事后无法证明 m25-full 是用哪一版混料训出来的（混料一旦被误改、重生成或
局部覆盖，读数归属即不可考）。

本脚本产出 `reports/m25-run-binding.json`：
  - 训练集 sha256 + 字节数 + 行数 + 内容级 zh 占比（**与审计值交叉断言**：
    137,670 行 / 44.0% zh，不符即高声报警——说明文件在审计后被改动）；
  - `configs/m25-full.yaml`、`data/lf/dataset_info.json` 的 sha256；
  - 起始模型目录（m15）与输出目录的清单（名称/大小/mtime）；
  - checkpoint 清单 + `train_results.json` 是否存在（运行是否已收尾）。

用法：python scripts/bind_m25_run.py [--manifest-rows 137670 --zh 44.0]
幂等：可反复运行——训练完成后重跑，即得"结束态"绑定（含 train_results 与全部 ckpt）。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
MIX = ROOT / "data" / "lf" / "sft_m25.jsonl"
CONFIG = ROOT / "configs" / "m25-full.yaml"
DATASET_INFO = ROOT / "data" / "lf" / "dataset_info.json"
START_MODEL = ROOT / "checkpoints" / "qwen3-06b-sec-m15"
OUT_DIR = ROOT / "checkpoints" / "qwen3-06b-sec-m25-full"
OUT = ROOT / "reports" / "m25-run-binding.json"
CJK = re.compile(r"[\u4e00-\u9fff]")


def sha256(p: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def dir_listing(p: Path, limit: int = 40) -> list[dict]:
    if not p.exists():
        return []
    items = sorted(p.rglob("*"), key=lambda x: str(x))[:limit]
    return [{"rel": str(x.relative_to(p)).replace("\\", "/"),
             "bytes": x.stat().st_size if x.is_file() else None,
             "mtime": datetime.datetime.fromtimestamp(
                 x.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}
            for x in items]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="m25",
                    help="运行标签（决定默认路径；M3 用 --tag m3 并显式传参）")
    ap.add_argument("--mix", default="data/lf/sft_m25.jsonl")
    ap.add_argument("--config", default="configs/m25-full.yaml")
    ap.add_argument("--dataset-info", default="data/lf/dataset_info.json")
    ap.add_argument("--start-model", default="checkpoints/qwen3-06b-sec-m15")
    ap.add_argument("--outdir", default="checkpoints/qwen3-06b-sec-m25-full")
    ap.add_argument("--out", default="reports/m25-run-binding.json")
    ap.add_argument("--manifest-rows", type=int, default=137670,
                    help="审计行数；传 0 跳过行数断言（M3 等无审计基线时用）")
    ap.add_argument("--zh", type=float, default=44.0,
                    help="审计内容级 zh 占比；传负数跳过断言")
    ap.add_argument("--zh-tol", type=float, default=0.6)
    args = ap.parse_args()
    global MIX, CONFIG, DATASET_INFO, START_MODEL, OUT_DIR, OUT
    MIX = ROOT / args.mix
    CONFIG = ROOT / args.config
    DATASET_INFO = ROOT / args.dataset_info
    START_MODEL = ROOT / args.start_model
    OUT_DIR = ROOT / args.outdir
    OUT = ROOT / args.out

    rows = zh = 0
    for line in MIX.open(encoding="utf-8"):
        if not line.strip():
            continue
        rows += 1
        j = json.loads(line)
        u = next((m.get("content", "") for m in j.get("messages", [])
                  if m.get("role") == "user"), "")
        if len(CJK.findall(u[:2000])) >= 8:
            zh += 1
    zh_pct = (zh / rows * 100) if rows else 0.0

    mismatches = []
    if args.manifest_rows > 0 and rows != args.manifest_rows:
        mismatches.append(f"行数 {rows} != 审计值 {args.manifest_rows}")
    if args.zh >= 0 and abs(zh_pct - args.zh) > args.zh_tol:
        mismatches.append(f"zh {zh_pct:.2f}% 偏离审计值 {args.zh}% "
                          f"(tol {args.zh_tol})")

    ckpts = []
    if OUT_DIR.exists():
        for d in sorted(OUT_DIR.iterdir()):
            if d.is_dir():
                ckpts.append({"name": d.name,
                              "bytes": sum(f.stat().st_size
                                           for f in d.rglob("*")
                                           if f.is_file())})
    doc = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run": args.tag,
        "training_mix": {
            "path": args.mix,
            "sha256": sha256(MIX),
            "bytes": MIX.stat().st_size,
            "mtime": datetime.datetime.fromtimestamp(
                MIX.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "rows_recounted": rows,
            "content_zh_pct_recounted": round(zh_pct, 2),
            "audited_rows": args.manifest_rows,
            "audited_zh_pct": args.zh,
        },
        "config": {"path": args.config, "sha256": sha256(CONFIG)},
        "dataset_info": {"path": args.dataset_info,
                         "sha256": sha256(DATASET_INFO)},
        "start_model": {"path": args.start_model,
                        "listing_head": dir_listing(START_MODEL)},
        "output_dir": {"path": args.outdir,
                       "checkpoints": ckpts,
                       "train_results_present":
                           (OUT_DIR / "train_results.json").exists()},
        "integrity": {"mismatches": mismatches, "ok": not mismatches},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"训练集 sha256 : {doc['training_mix']['sha256']}")
    print(f"行数/zh       : {rows} / {zh_pct:.2f}%"
          f"（审计 {args.manifest_rows} / {args.zh}%）")
    print(f"config sha256 : {doc['config']['sha256'][:16]}…")
    print(f"checkpoints   : {len(ckpts)} 个；train_results: "
          f"{doc['output_dir']['train_results_present']}")
    if mismatches:
        print("⚠️  完整性不符：" + "；".join(mismatches))
    elif args.manifest_rows > 0:
        print("✅ 完整性：训练集与审计值一致（未被改动）")
    else:
        print("ℹ️  已记录绑定（未设审计基线，仅留档哈希与计数）")
    print(f"绑定记录 → {OUT}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
