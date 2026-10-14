# -*- coding: utf-8 -*-
"""M5 门禁辅助：汇总两臂全部产物的 elapsed_s / 模型路径 / 数据 sha 等元数据。"""
import json
from pathlib import Path

R = Path("reports")
files = [
    # arm1
    "heldout-chat-v023-m5a-dpo-probe-mnt512.json",
    "heldout-chat-gen-m5a-dpo-probe-mnt512.json",
    "longctx-m5a-dpo-probe-chat.json",
    "dilution-m5a-dpo-probe-v0.6.json",
    "jb-scored-m5a-dpo-probe-v0.7-full-v2.json",
    "topup-verdict-m5a-dpo-probe-v023-mnt512.json",
    # arm2
    "heldout-chat-v023-m5b-p2rl-grpo-v1-mnt512.json",
    "heldout-chat-gen-m5b-p2rl-grpo-v1-mnt512.json",
    "longctx-m5b-p2rl-grpo-v1-chat.json",
    "topup-verdict-m5b-p2rl-grpo-v1-v023-mnt512.json",
]
for f in files:
    p = R / f
    if not p.exists():
        print(f"{f}: MISSING")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    el = d.get("elapsed_s")
    model = d.get("model") or (d.get("selfreport") or {}).get("model")
    sha = (d.get("data") or {}).get("sha256") if isinstance(d.get("data"), dict) else None
    if sha:
        sha = sha[:16]
    n = d.get("n_items") or d.get("n")
    print(f"{f}: elapsed={el} n={n} model={model} data_sha={sha}")

# dilution arm2 pending check
p2 = R / "dilution-m5b-p2rl-grpo-v1-v0.6.json"
print("dilution-m5b-p2rl-grpo-v1-v0.6.json exists:", p2.exists())
# jb arm2 pending
print("jb-scored-m5b-p2rl-grpo-v1-v0.7-full-v2.json exists:",
      (R / "jb-scored-m5b-p2rl-grpo-v1-v0.7-full-v2.json").exists())
