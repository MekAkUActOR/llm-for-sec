# -*- coding: utf-8 -*-
"""修正 reports/m3-launch-runbook.md 中与实际运行不符的引用。

实际运行（命令行实测）：`llamafactory-cli train configs\\m3-dpo-final.yaml`
  base = checkpoints\\soup-needlefix-a050
  dataset = sec_dpo_m3_final -> data/lf/dpo_m3_final.jsonl (28,842 对)
  cutoff_len = 1024 ; save_steps = 100 ; save_total_limit = 5
详见 reports/m3-actual-config-correction.md。
"""
from pathlib import Path

p = Path("reports/m3-launch-runbook.md")
t = p.read_text(encoding="utf-8")
orig = t

# 1) 配置文件名：实质替换（runbook 的意图就是"M3 的配置"）
t = t.replace(r"configs\m3-dpo.yaml", r"configs\m3-dpo-final.yaml")
t = t.replace("configs/m3-dpo.yaml", "configs/m3-dpo-final.yaml")

# 2) 收尾绑定里的起点模型与数据集
t = t.replace(r"--start-model checkpoints\qwen3-06b-sec-m25-full",
              r"--start-model checkpoints\soup-needlefix-a050")
t = t.replace(r"--mix data\lf\dpo_m3.jsonl", r"--mix data\lf\dpo_m3_final.jsonl")

# 3) save_total_limit 的实际值
t = t.replace("`save_total_limit=2`", "`save_total_limit=5`")

# 4) 顶部加显式更正块（放在标题后第一段之前）
HDR = """
> ## ⚠ 2026-09-30 晚更正（父代理实测命令行）
>
> **M3 实际运行的配置是 `configs\\m3-dpo-final.yaml`，不是 `configs\\m3-dpo.yaml`。**
> 实测命令行：`llamafactory-cli train J:\\Projects\\llm_for_sec\\configs\\m3-dpo-final.yaml`
> 命令行实证与盘上旁证（5 个 checkpoint、间距 100、`total_steps=1803 = 28,842/16`）一致。
>
> 本文件原先在 6 处指向 `configs\\m3-dpo.yaml`，而**那份配置是未被使用的废弃稿**，
> 其 `model_name_or_path` 指向 **`qwen3-06b-sec-m25-full`** —— 该基线已被裁决为
> **FAIL(G2) 且其 PASS 不可采信**。照原文执行收尾绑定会**把 M3 的谱系记录写错**
> （记为从 m25-full 出发、用旧数据集 `dpo_m3.jsonl`）。
> 已按实际值更正：base = `checkpoints\\soup-needlefix-a050`、
> mix = `data\\lf\\dpo_m3_final.jsonl`、`save_total_limit = 5`（原写 2）。
>
> 依据与完整差异见 **`reports/m3-actual-config-correction.md`**。
"""
lines = t.split("\n")
# 插到第一个标题行之后
for i, ln in enumerate(lines):
    if ln.startswith("# "):
        lines.insert(i + 1, HDR)
        break
t = "\n".join(lines)

assert t != orig, "无改动"
p.write_text(t, encoding="utf-8")
print(f"✅ 已更正；行数 = {len(t.splitlines())}")
for pat in ("m3-dpo.yaml", "m25-full", "dpo_m3.jsonl", "save_total_limit=2"):
    n = t.count(pat)
    print(f"   残留 '{pat}' = {n}")
