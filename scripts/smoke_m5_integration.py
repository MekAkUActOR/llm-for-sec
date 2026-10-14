# -*- coding: utf-8 -*-
"""P2.9 M5 发射集成 · 冒烟验证（纯 CPU，fail-closed）。

校验四件事（任务 P2.9 ④）：
  S1 数据行数：dpo_m5_calib.jsonl = 34,602 行（= 基座 28,842 + p16 5,760），
     且与 manifest.json 登记一致；dataset_info 注册条目按 LLaMA-Factory 解析口径
     （dataset_dir + dataset_info.json → file_name）可达。
  S2 yaml 可解析：configs/m5-calib-probe.yaml 可被 python yaml.safe_load 加载，
     关键字段在场。
  S3 配置 diff（字段级）：与 configs/m4-capfix-probe.yaml 逐键比较，
     **恰好只有 3 键不同**：dataset_dir / dataset / output_dir（单变量纪律 ✓）；
     其余全部键值（含 max_steps 300 / save_steps 50 / save_total_limit 8）逐字相同。
  S4 配置 diff（行级证据）：unified diff 输出，逐 hunk 归因——运行标识头（logging 名）
     + 3 个字段行 + 1 行 epoch 算术注释（数据换 ⇒ 全 epoch 1,803→2,163 步，非超参）。

用法：.venv\\Scripts\\python.exe scripts\\smoke_m5_integration.py
"""
from __future__ import annotations

import difflib
import json
import os
import sys

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIX = os.path.join(ROOT, "data", "dpo", "m5", "dpo_m5_calib.jsonl")
MANIFEST = os.path.join(ROOT, "data", "dpo", "m5", "manifest.json")
DSINFO = os.path.join(ROOT, "data", "dpo", "m5", "dataset_info.json")
CFG_M5 = os.path.join(ROOT, "configs", "m5-calib-probe.yaml")
CFG_M4 = os.path.join(ROOT, "configs", "m4-capfix-probe.yaml")

EXPECT_ROWS = 34602
EXPECT_BASE_ROWS = 28842
EXPECT_P16_ROWS = 5760
DS_NAME = "sec_dpo_m5_calib"
# 与 m4 探针相比**唯一允许**不同的字段（单变量纪律：唯一科学变量 = 数据）
ALLOWED_FIELD_DIFFS = {"dataset_dir", "dataset", "output_dir"}
# 单变量纪律的锚点字段（必须逐字相同）
ANCHOR_FIELDS = {
    "max_steps": 300, "save_steps": 50, "save_total_limit": 8,
    "learning_rate": 2.0e-6, "pref_beta": 0.1, "pref_loss": "sigmoid",
    "cutoff_len": 1024, "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 16, "warmup_steps": 20, "logging_steps": 5,
    "model_name_or_path": "J:\\Projects\\llm_for_sec\\checkpoints\\soup-needlefix-a050",
}


def die(msg: str) -> None:
    print(f"[FATAL] {msg}")
    print("SMOKE-M5=FAIL")
    sys.exit(1)


def s1_data() -> None:
    print("-- S1 数据行数与注册可达性 --")
    if not os.path.exists(MIX):
        die(f"合并件缺失：{MIX}")
    n = 0
    with open(MIX, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
                try:
                    json.loads(line)
                except json.JSONDecodeError as e:
                    die(f"合并件第 {n} 行 JSON 解析失败：{e}")
    if n != EXPECT_ROWS:
        die(f"合并件行数 {n} != {EXPECT_ROWS}")
    mf = json.loads(open(MANIFEST, encoding="utf-8").read())
    reg = mf["files"]["dpo_m5_calib.jsonl"]
    if reg["rows"] != EXPECT_ROWS or reg["composition"].find("28,842") < 0:
        die("manifest 登记与合并件不符")
    mix = mf["mix"]
    if not (mix["base_rows"] == EXPECT_BASE_ROWS and mix["p16_rows"] == EXPECT_P16_ROWS
            and mix["total_rows"] == EXPECT_ROWS):
        die("manifest mix 分量不符（28,842 + 5,760 = 34,602）")
    print(f"[OK] dpo_m5_calib.jsonl = {n} 行（全部可解析），"
          f"= {mix['base_rows']:,} 基座 + {mix['p16_rows']:,} p16 ✓ 与 manifest 一致")

    # LLaMA-Factory 解析口径（src/llamafactory/data/parser.py L106 + loader.py L66）
    dsinfo = json.loads(open(DSINFO, encoding="utf-8").read())
    if DS_NAME not in dsinfo:
        die(f"dataset_info.json 无 {DS_NAME}")
    entry = dsinfo[DS_NAME]
    resolved = os.path.join(os.path.dirname(DSINFO), entry["file_name"])
    if not os.path.exists(resolved):
        die(f"注册条目解析不到文件：{resolved}")
    if entry.get("formatting") != "sharegpt" or entry.get("ranking") is not True:
        die("注册条目非 sharegpt ranking 口径")
    tags = entry.get("tags", {})
    if not (tags.get("user_tag") == "human" and tags.get("assistant_tag") == "gpt"):
        die("注册条目 tags 与 house DPO 口径不符（user=human/assistant=gpt）")
    print(f"[OK] dataset_info 注册：{DS_NAME} → {entry['file_name']}"
          f"（sharegpt · ranking · user=human/assistant=gpt ✓，LF 解析口径可达 ✓）")


def s2_yaml() -> dict:
    print("-- S2 yaml.safe_load --")
    with open(CFG_M5, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict) or not cfg:
        die("m5-calib-probe.yaml 解析结果不是非空映射")
    missing = [k for k in ("dataset_dir", "dataset", "output_dir", "max_steps",
                           "save_steps", "save_total_limit", "pref_loss") if k not in cfg]
    if missing:
        die(f"m5 配置缺字段：{missing}")
    print(f"[OK] m5-calib-probe.yaml 可被 yaml.safe_load 加载：{len(cfg)} 个字段 ✓")
    return cfg


def s3_field_diff(cfg5: dict) -> dict:
    print("-- S3 字段级 diff（单变量纪律） --")
    with open(CFG_M4, encoding="utf-8") as f:
        cfg4 = yaml.safe_load(f)
    keys4, keys5 = set(cfg4), set(cfg5)
    if keys4 != keys5:
        die(f"字段集合不同：仅 m4 有 {sorted(keys4 - keys5)} / 仅 m5 有 {sorted(keys5 - keys4)}"
            f"（逐字段复制纪律：不得增删字段 ✗）")
    diffs = {k: (cfg4[k], cfg5[k]) for k in sorted(keys4) if cfg4[k] != cfg5[k]}
    if set(diffs) != ALLOWED_FIELD_DIFFS:
        die(f"字段级差异 {sorted(diffs)} != 允许集 {sorted(ALLOWED_FIELD_DIFFS)}"
            f"（超出三处 ✗ 单变量纪律破坏）")
    for k in ("dataset_dir", "dataset", "output_dir"):
        print(f"  {k}: {diffs[k][0]}  →  {diffs[k][1]}")
    for k, want in ANCHOR_FIELDS.items():
        if cfg5.get(k) != want:
            die(f"锚点字段 {k} = {cfg5.get(k)!r} != 冻结值 {want!r}")
    print(f"[OK] 字段级 diff 恰为三处（dataset_dir / dataset / output_dir）✓；"
          f"锚点字段 max_steps=300 · save_steps=50 · save_total_limit=8 · lr=2.0e-6 ·"
          f" β=0.1 · cutoff=1024 · batch 1×16 逐字不动 ✓")
    return diffs


def s4_line_diff() -> None:
    print("-- S4 行级 unified diff 证据 --")
    t4 = open(CFG_M4, encoding="utf-8").read().splitlines(keepends=True)
    t5 = open(CFG_M5, encoding="utf-8").read().splitlines(keepends=True)
    diff = list(difflib.unified_diff(t4, t5, fromfile="configs/m4-capfix-probe.yaml",
                                     tofile="configs/m5-calib-probe.yaml", n=1))
    print("".join(diff), end="")
    # 机器归类每个 hunk：改动行必须落在一类
    changed = [l for l in diff if l[:1] in ("+", "-") and not l.startswith(("+++", "---"))]
    field_lines = [l for l in changed
                   if l[1:].strip().startswith(("dataset_dir:", "dataset:", "output_dir:"))]
    comment_lines = [l for l in changed if l[1:].lstrip().startswith("#")]
    other = [l for l in changed if l not in field_lines and l not in comment_lines]
    if other:
        die(f"diff 出现未归类改动行（非字段、非注释）：{other}")
    fields_touched = sorted({l[1:].strip().split(":", 1)[0] for l in field_lines})
    if fields_touched != sorted(ALLOWED_FIELD_DIFFS):
        die(f"字段改动 {fields_touched} != 允许集 {sorted(ALLOWED_FIELD_DIFFS)}（只允许三处）")
    if len(field_lines) != 2 * len(fields_touched):
        die(f"字段改动行数 {len(field_lines)} != 3 对（每字段应恰为一删一增）")
    print(f"[OK] 行级 diff 归类：字段改动恰 3 处（dataset_dir / dataset / output_dir，"
          f"各一删一增 ✓）+ 注释行 {len(comment_lines)}（运行标识头 logging 名 +"
          f" epoch 算术注释，非超参 ✗）；其余 0 行未归类改动 ✓")


def main() -> int:
    print("== P2.9 M5 发射集成冒烟（smoke_m5_integration） ==")
    s1_data()
    cfg5 = s2_yaml()
    s3_field_diff(cfg5)
    s4_line_diff()
    print("\n== 冒烟通过 ==")
    print("SMOKE-M5=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
