# -*- coding: utf-8 -*-
"""**全门禁**截断体检：`max_new_tokens=96` 是否也在污染其它门禁的读数？

动机：已证明 toolout 轴 67.8% 的响应撞在 96 token 上限。
`baseline_eval.py:129` 是该上限的**默认值**，而多个门禁脚本都调用它。
若 **MUST-A（`data/heldout/v0.3-gen` 未见载体门禁）**也撞上限，
则本项目"未见载体泛化"这一核心 claim 的读数同样在截断仪器下产出。

本脚本扫描 **reports 下全部 `resp-*.jsonl`**，按文件报 token 长度分布与撞顶比例。
只加载 tokenizer（CPU），不碰 GPU。
"""
import glob
import json
import os
from collections import Counter
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = Path(__file__).resolve().parent.parent
TOK_DIR = (ROOT / ".cache" / "huggingface" / "hub" /
           "models--Qwen--Qwen3-0.6B-Base" / "snapshots" /
           "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
CAP = 96

from transformers import AutoTokenizer  # noqa: E402

tok = AutoTokenizer.from_pretrained(str(TOK_DIR), trust_remote_code=True)

RESP_KEYS = ("response", "content", "text", "completion", "output", "answer")


def get_text(r):
    for k in RESP_KEYS:
        if isinstance(r.get(k), str):
            return r[k]
    if isinstance(r.get("messages"), list):
        for m in r["messages"]:
            if isinstance(m, dict) and m.get("role") == "assistant":
                return str(m.get("content") or "")
    return ""


files = sorted(glob.glob(str(ROOT / "reports" / "resp-*.jsonl")))
files += sorted(glob.glob(str(ROOT / "reports" / "**" / "resp-*.jsonl"), recursive=True))
files = sorted(set(files))
print(f"resp-*.jsonl 文件数 = {len(files)}\n")
print(f"{'文件':<52} {'n':>5} {'最大tok':>7} {'≥96 条':>7} {'占比':>7} {'中位':>5}")
print("-" * 90)
rows = []
for f in files:
    lens, n = [], 0
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = get_text(r)
            if not t:
                continue
            n += 1
            lens.append(len(tok.encode(t, add_special_tokens=False)))
    if not n:
        continue
    at = sum(1 for x in lens if x >= CAP)
    sl = sorted(lens)
    rows.append((Path(f).name, n, max(lens), at, at / n, sl[len(sl) // 2]))
    print(f"{Path(f).name:<52} {n:>5} {max(lens):>7} {at:>7} "
          f"{at / n * 100:>6.1f}% {sl[len(sl) // 2]:>5}")

print("\n" + "=" * 90)
hot = [r for r in rows if r[4] >= 0.25]
print(f"撞顶比例 ≥25% 的文件数 = {len(hot)} / {len(rows)}")
if hot:
    print("⇒ 以下门禁的读数**受截断影响**（必须在其裁定里登记）：")
    for name, n, mx, at, frac, med in hot:
        print(f"     {name:<52} {frac * 100:>5.1f}%  中位 {med} token")
