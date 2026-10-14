# -*- coding: utf-8 -*-
"""★决定性检验：`action recovered` 的截断是否由 `max_new_tokens=96` 造成。

审计（`reports/recovered-action-audit.md` ⑧.3）只能证明"形状与硬截断一致"，
**无法证明**是 `max_new_tokens` 而非模型自停笔，因为响应文件里没有 `finish_reason`/token 数。
本脚本用**只加载 tokenizer（CPU，不碰 GPU）**的办法补上这个证据：

  **若上限在起作用 ⇒ 响应 token 长度分布应在 96 处出现尖峰。**

附带：统计"以未闭合 `VERDICT` JSON 结尾"（截断特征）的条数。
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
print(f"tokenizer 已加载（CPU）：{TOK_DIR.name}\n")

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


def truncated_verdict(t):
    """以未闭合 VERDICT JSON 结尾 = 截断特征。"""
    i = t.rfind("VERDICT")
    if i < 0:
        return False
    seg = t[i:]
    return seg.count("{") > seg.count("}")


all_len = []
per_tag = {}
for f in sorted(glob.glob(str(ROOT / "reports" / "resp-chat-to-*.jsonl"))):
    tag = Path(f).name.replace("resp-chat-to-", "").replace(".jsonl", "")
    lens, trunc, n = [], 0, 0
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
            k = len(tok.encode(t, add_special_tokens=False))
            lens.append(k)
            all_len.append(k)
            if truncated_verdict(t):
                trunc += 1
    if n:
        per_tag[tag] = (n, lens, trunc)

print(f"{'tag':<12} {'n':>4} {'最大':>5} {'=96 的条数':>10} {'占比':>7} "
      f"{'未闭合VERDICT':>13} {'中位':>5}")
print("-" * 68)
tot_at_cap = tot_n = 0
for tag, (n, lens, trunc) in per_tag.items():
    at_cap = sum(1 for x in lens if x >= CAP)
    sl = sorted(lens)
    tot_at_cap += at_cap
    tot_n += n
    print(f"{tag:<12} {n:>4} {max(lens):>5} {at_cap:>10} "
          f"{at_cap / n * 100:>6.1f}% {trunc:>13} {sl[len(sl) // 2]:>5}")

print(f"\n合计：{tot_n} 条响应，其中 **{tot_at_cap} 条（{tot_at_cap / tot_n * 100:.1f}%）"
      f"达到或超过 {CAP} token**")
print(f"全样本最大长度 = {max(all_len)} token；"
      f"长度 ≥95 的条数 = {sum(1 for x in all_len if x >= 95)}")

h = Counter(all_len)
print("\n长度分布的顶部 20 个（长度:条数）：")
for k, v in sorted(h.items(), key=lambda x: -x[1])[:20]:
    print(f"   {k:>4} : {v}")
