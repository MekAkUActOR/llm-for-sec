# -*- coding: utf-8 -*-
"""训练侧截断检查：`sec_dpo_m3_final` 有多少对超过 cutoff_len=1024。

动机：本会话已证明**评测**侧 `max_new_tokens=96` 造成 67.8% 的响应截断。
**训练**侧的同类风险是 `cutoff_len`（configs/m3-dpo-final.yaml = 1024）：
若有超长的 prompt+chosen / prompt+rejected，DPO 训练时会**静默截断**，
使"我们以为在训的东西"与"实际训的东西"不一致。

只用 tokenizer（CPU，不加载模型），Qwen3 走 chat template 口径。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUTOFF = 1024

cands = list(ROOT.glob("data/**/dpo_m3_final.jsonl"))
if not cands:
    print("FIND: 未找到 dpo_m3_final.jsonl")
    sys.exit(1)
path = cands[0]
print(f"数据集 = {path.relative_to(ROOT)}  ({path.stat().st_size/1e6:.1f} MB)")

from transformers import AutoTokenizer  # noqa: E402

# 复用处已证明可用的路径（scripts/prove_truncation_cause.py L21-28）：
# 用**基座模型**在 HF 缓存里的 tokenizer 快照；从 checkpoint 目录加载会因
# tokenizer_config 指向慢分词器而失败（需 sentencepiece）。
TOK_DIR = (ROOT / ".cache" / "huggingface" / "hub" /
           "models--Qwen--Qwen3-0.6B-Base" / "snapshots" /
           "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
tok = AutoTokenizer.from_pretrained(str(TOK_DIR), trust_remote_code=True)
print(f"tokenizer 已加载（CPU）：{TOK_DIR.name}")

rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
print(f"对数 = {len(rows)}")

def msgs_text(msgs):
    return "\n".join(m.get("value", "") for m in msgs)

over_c = over_r = 0
lens_c, lens_r = [], []
for r in rows:
    conv = r.get("conversations") or []
    ptxt = msgs_text(conv)
    for key, cnt in (("chosen", "c"), ("rejected", "r")):
        v = r.get(key)
        if isinstance(v, list):
            vtxt = msgs_text(v)
        else:
            vtxt = str(v or "")
        n = len(tok(ptxt + "\n" + vtxt, add_special_tokens=False)["input_ids"])
        (lens_c if cnt == "c" else lens_r).append(n)
        if n > CUTOFF:
            if cnt == "c":
                over_c += 1
            else:
                over_r += 1

def stat(name, xs, over):
    xs = sorted(xs)
    n = len(xs)
    p = lambda q: xs[min(n - 1, int(q * n))]
    print(f"\n--- {name} ---")
    print(f"  n={n}  超 {CUTOFF} 的条数 = {over}  ({over/n*100:.2f}%)")
    print(f"  min={xs[0]}  p50={p(.50)}  p90={p(.90)}  p95={p(.95)}  p99={p(.99)}  max={xs[-1]}")
    print(f"  被截掉的 token 总量 = {sum(max(0, x-CUTOFF) for x in xs):,}")

stat("prompt+chosen", lens_c, over_c)
stat("prompt+rejected", lens_r, over_r)
tot = over_c + over_r
frac = tot / (2 * len(rows)) if rows else 0.0
print(f"\n结论：cutoff_len={CUTOFF}，超长 {over_c}(chosen)+{over_r}(rejected) = {tot} 条"
      f"（占 2×{len(rows)} 条的 {frac*100:.4f}%）。")
if frac < 0.001:
    print("⇒ **训练侧基本无截断**：cutoff_len 与数据集规模匹配。"
          "（对照：评测侧 max_new_tokens=96 造成 67.8% 截断——两侧口径差异极大。）")
else:
    print("⇒ **训练侧存在静默截断**，需评估被截断部分是否含安全相关结论。")
