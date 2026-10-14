# -*- coding: utf-8 -*-
"""决定性检查：训练文件里 carrier 信封的**转义形态**到底是什么。

前面两种正则都得 0，而探针的原文打印却显示 `type="text"` ⇒ 转义层判断有误。
本脚本直接数字节级候选串，不再猜。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "data" / "lf" / "sft_m25.jsonl"

CANDIDATES = [
    b'<carrier type="',
    b'<carrier type=\\"',          # JSON 转义引号
    b'<carrier type=',
    b'<carrier ',
    b'<carrier>',
    b'carrier type',
    b'\\u003ccarrier',
]

data = p.read_bytes()
print(f"文件 {p.name} 大小 = {len(data):,} 字节")
print(f"\n{'候选字节串':<28} {'出现次数':>10}")
print("-" * 42)
for c in CANDIDATES:
    print(f"{c.decode('ascii', 'replace'):<28} {data.count(c):>10,}")

# 取第一处 '<carrier ' 的原始上下文（只看字节，不经任何解码）
j = data.find(b"<carrier ")
if j >= 0:
    seg = data[max(0, j - 40):j + 120]
    print(f"\n第一处 '<carrier ' 的**原始字节**上下文：")
    print(f"  {seg!r}")
    print(f"\n  以 ascii-ignore 显示：{seg.decode('ascii', 'ignore')}")
else:
    print("\n未找到任何 '<carrier '")
