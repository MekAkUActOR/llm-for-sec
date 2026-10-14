# -*- coding: utf-8 -*-
"""M5B-R5 监控轴③：重复循环计数（r4 钉死口径：截断 ∧ 正文 regex `(.{2,40}?)\\1{4,}`）。

口径（m5b-r4-gates §3 表 + §6 登记项 3）：
- 截断 = resp jsonl 行 finish_reason == 'length'（v0.2.3 全量 737）；
- 行内重复循环 = 截断行的正文（去 VERDICT 行）匹配 regex `(.{2,40}?)\1{4,}`（默认 flags）；
- 锚点重算：同会话对 v4 复算（r4 登记 8/16），保内一致；跨会话绝对比较不可用。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAT = re.compile(r"(.{2,40}?)\1{4,}")


def body_of(text: str) -> str:
    # 去 VERDICT 行（正文 = 非契约部分）
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("VERDICT")]
    return "\n".join(lines)


def count(tag: str) -> dict:
    p = ROOT / "reports" / f"resp-chat-v023-{tag}-mnt512.jsonl"
    n = trunc = loop = 0
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        n += 1
        if r.get("finish_reason") == "length":
            trunc += 1
            if PAT.search(body_of(r.get("text") or "")):
                loop += 1
    return {"tag": tag, "n": n, "truncated": trunc, "rep_loop": loop}


if __name__ == "__main__":
    for tag in sys.argv[1:]:
        print(json.dumps(count(tag), ensure_ascii=False))
