# -*- coding: utf-8 -*-
"""post_m25_eval.ps1 输入预检（只读，不占 GPU）。

检查评估链每个环节的输入是否就位：探针目录、heldout v0.2.1、
各基线判分文件、基线 PPL / longctx 对照件。缺件在 12:30 才发现会浪费时间。
"""
import json
import os
from pathlib import Path

R = Path(r"J:\Projects\llm_for_sec")
checks = []


def chk(label, path, kind="file"):
    p = R / path
    ok = p.exists()
    extra = ""
    if ok and kind == "json" and p.is_file():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                keys = [k for k in ("metrics", "label_distribution",
                                    "n_responded", "langs", "by_family")
                        if k in d]
                extra = f"keys={keys}" if keys else f"{len(d)} keys"
        except Exception as e:  # noqa: BLE001
            extra = f"PARSE-FAIL {e}"
            ok = False
    elif ok and kind == "dir":
        n = len(list(p.glob("*")))
        extra = f"{n} files"
    elif ok and kind == "jsonl":
        n = 0
        with p.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        extra = f"{n} rows"
    checks.append((ok, label, path, extra))


# 探针 / heldout
chk("probe v0.3 (PPL 门禁用)", "data/probes/v0.3", "dir")
chk("probe v0.1.1 (回退)", "data/probes/v0.1.1", "dir")
chk("heldout v0.2.1", "data/heldout/v0.2.1", "dir")
chk("heldout v0.2.1/security.jsonl", "data/heldout/v0.2.1/security.jsonl", "jsonl")
chk("heldout v0.2.1/ai_safety.jsonl", "data/heldout/v0.2.1/ai_safety.jsonl", "jsonl")
# v0.3-gen：**未见载体**泛化门禁集（image_metadata/av_metadata；2026-09-30 起 G1 用它，
# 而 tool_output 子集降级为"同载体回归测试"——该载体已在训练中出现 1,224 次）
chk("heldout v0.3-gen", "data/heldout/v0.3-gen", "dir")
chk("heldout v0.3-gen/image_metadata.jsonl",
    "data/heldout/v0.3-gen/image_metadata.jsonl", "jsonl")
chk("heldout v0.3-gen/av_metadata.jsonl",
    "data/heldout/v0.3-gen/av_metadata.jsonl", "jsonl")
# 评估脚本
for s in ("baseline_eval.py", "score_heldout_v2.py", "probe_ppl.py",
          "compare_ppl.py", "probe_longctx.py"):
    chk(f"script {s}", f"scripts/{s}")
# 基线判分件（六点对照行）
for name, path in (
        ("c1-full", "reports/scored-c1full-v2.json"),
        ("m15", "reports/scored-m15-v2.json"),
        ("m2-calib", "reports/scored-m2calib-v2.json"),
        ("m2-full", "reports/scored-m2full-v2.json")):
    chk(f"scored {name} (v2)", path, "json")
# 基线 PPL（若缺，脚本会自己生成 m15 的）
chk("ppl m15 (v0.3)", "reports/ppl-m15-v0.3.json", "json")
chk("ppl m2-full (v0.3)", "reports/ppl-m2full-v0.3.json", "json")
# longctx 对照
chk("longctx m2-full", "reports/longctx-m2full.json", "json")
# 训练产物（评估前置）
chk("m25-full 目录", "checkpoints/qwen3-06b-sec-m25-full", "dir")

bad = [c for c in checks if not c[0]]
for ok, label, path, extra in checks:
    print(f"{'OK  ' if ok else 'MISS'} {label:32s} {path:52s} {extra}")
print()
print(f"missing: {len(bad)}")
for _, label, path, _ in bad:
    print("  -", label, path)
