# -*- coding: utf-8 -*-
"""M5A-R2 多数据集装载冒烟（纯 CPU，不训练、不触 GPU）。

复刻一轮 SMOKE-M5A-MULTIDS 先例（m5-launch.md §1.2/§5.6，原 _tmp 脚本已退役），
针对二轮三注册：sec_dpo_m5a_r2_base_m4capfix / _p16_benign / _p16_malicious。

冒烟面（= 一轮两次失败的真实炸点 ✗✓）：
  ① parser.py 以 locale 默认编码（本机 GBK）open(dataset_info.json) → UnicodeDecodeError
     （attempt-2 教训：本件必须纯 ASCII）；
  ② 每条目独立 datasets.load_dataset("json", data_files=[单文件])（loader.py L164-186 口径）
     → DatasetGenerationCastError（attempt-1 教训：单文件内 schema 必须同构）；
  ③ dataset 逗号拆分三名单全部在注册件内可解析（hparams/data_args.py 口径）；
  ④ 行数合计 = 34,058 = m4 28,842 + p16-r2 5,216（良 2,336 + 恶 2,880）。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HF_HOME", os.path.join(ROOT, ".cache", "huggingface"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DS_DIR = os.path.join(ROOT, "data", "m5a-r2-run")
CFG = os.path.join(ROOT, "configs", "m5a-dpo-r2.yaml")

# ① parser.py 同款 locale 默认编码读注册件（不指定 encoding —— GBK 炸点复刻）
raw = open(os.path.join(DS_DIR, "dataset_info.json"), "rb").read()
raw.decode("ascii")  # 先断言纯 ASCII（belt）
info = json.loads(raw.decode(locale_enc := __import__("locale").getpreferredencoding(False)))
print(f"[OK] dataset_info.json 以 locale 编码（{locale_enc}）解析成功（纯 ASCII ✓ attempt-2 雷排除）")

# ③ config 的 dataset 逗号拆分 + 名单解析（data_args.py 口径）
datasets_field = None
for line in open(CFG, encoding="utf-8"):
    if line.startswith("dataset:"):
        datasets_field = line.split(":", 1)[1].strip()
        break
assert datasets_field, "config 无 dataset: 行"
names = [n.strip() for n in datasets_field.split(",") if n.strip()]
assert len(names) == 3, names
for n in names:
    assert n in info, f"注册件缺条目 {n}"
    assert info[n]["formatting"] == "sharegpt" and info[n]["ranking"] is True
print(f"[OK] dataset 三名单解析：{names}")

# ② 每条目独立装载（loader.py 单文件 data_files 口径）+ 行数/键面断言
from datasets import load_dataset  # noqa: E402

expect = {"sec_dpo_m5a_r2_base_m4capfix": 28842,
          "sec_dpo_m5a_r2_p16_benign": 2336,
          "sec_dpo_m5a_r2_p16_malicious": 2880}
total = 0
for n in names:
    path = os.path.normpath(os.path.join(DS_DIR, info[n]["file_name"]))
    ds = load_dataset("json", data_files=[path], split="train")
    cols = set(ds.column_names)
    assert len(ds) == expect[n], f"{n}: {len(ds)} != {expect[n]}"
    if n != "sec_dpo_m5a_r2_base_m4capfix":
        # p16-r2 两件：单一 11 键同构 schema + ranking 三列在位（CastError 雷排除）
        assert cols == {"dpo_class", "id", "pack", "lang", "polarity", "rejected_form",
                        "archetype_id", "conversations", "chosen", "rejected", "src_task"}, cols
        assert {"conversations", "chosen", "rejected"} <= cols
    else:
        assert {"conversations", "chosen", "rejected"} <= cols, f"基座缺 ranking 列：{sorted(cols)}"
    total += len(ds)
    print(f"[OK] {n}: {len(ds):,} 行装载成功（{os.path.relpath(path, ROOT)}）")

assert total == 34058, total
print(f"[OK] 合计 {total:,} = m4 base 28,842 + p16-r2 5,216（良 2,336 + 恶 2,880）✓")
print("SMOKE-M5A-R2-MULTIDS=OK")
