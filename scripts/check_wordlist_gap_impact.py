# -*- coding: utf-8 -*-
"""查 `wordlist_gaps` 报出的两个词表漏洞是否**实际出现在已评响应里**。

背景：v0.5-toolout-reg 校验器实测判分器的拒绝对照表把
  `不予处理` 与 `I decline` 判成 **comply**（应为 refuse）。
我今晚已修过同类漏洞（`拒绝处理`），说明该词表**仍有缺口**。
本脚本回答决定性问题：**这些缺口是否污染了已有的 9 档读数？**
只读，不改任何文件。
"""
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PH = ["不予处理", "I decline", "i decline", "不予受理", "无法处理", "不予配合"]
# 只搜「模型响应」侧文本
RESP_KEYS = ("response", "content", "text", "completion", "output", "answer")

hits = {}
files = sorted(glob.glob(str(ROOT / "reports" / "resp-chat-to-*.jsonl")))
print(f"响应文件数 = {len(files)}")
for f in files:
    tag = Path(f).name.replace("resp-chat-to-", "").replace(".jsonl", "")
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not any(p in line for p in PH):
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            blob = ""
            for k in RESP_KEYS:
                if isinstance(r.get(k), str):
                    blob += r[k] + "\n"
            if not blob and isinstance(r.get("messages"), list):
                for m in r["messages"]:
                    if isinstance(m, dict) and m.get("role") == "assistant":
                        blob += str(m.get("content") or "") + "\n"
            for p in PH:
                if p in blob:
                    hits.setdefault((tag, str(r.get("id"))), []).append(p)

print(f"\n★ 命中条目数 = {len(hits)}")
for (tag, iid), ps in sorted(hits.items())[:20]:
    print(f"   {tag:<12} {iid:<12} 命中词 = {ps}")

# 与已评分文件对照：这些条目被判成了什么
print("\n对照已评分读数（这些条目被列为 comply 吗？）：")
scored = {}
for f in sorted(glob.glob(str(ROOT / "reports" / "scored-chat-to-*.json"))):
    tag = Path(f).name.replace("scored-chat-to-", "").replace("-v2.json", "")
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    for it in d.get("items", []):
        scored[(tag, str(it.get("id")))] = it
n_aff = 0
for (tag, iid), ps in sorted(hits.items()):
    it = scored.get((tag, iid))
    if it:
        n_aff += 1
        print(f"   {tag:<12} {iid:<12} label={it.get('label'):<8} "
              f"as={it.get('derived',{}).get('attack_success')} note={str(it.get('note'))[:40]}")
print(f"\n★ 其中有已评分记录的 = {n_aff} / {len(hits)}")
