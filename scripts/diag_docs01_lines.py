# -*- coding: utf-8 -*-
"""诊断 docs/01 的"行数自相矛盾"：是编码/行尾问题还是真损坏。

现象：`Get-Content` 数出 578 行，而 `Select-String` 报告匹配在第 924 行。
本体论代理也观察到行数在 796→962→578 间跳变。
"""
from pathlib import Path

p = Path("docs/01-engineering-definition.md")
raw = p.read_bytes()
print(f"文件大小 = {len(raw):,} 字节")
print(f"开头 8 字节 = {raw[:8]!r}")
print(f"含 BOM = {raw.startswith(b'\\xef\\xbb\\xbf')}")
print(f"含 NUL = {raw.count(0)} 个")

crlf = raw.count(b"\r\n")
lf_total = raw.count(b"\n")
cr_total = raw.count(b"\r")
lone_lf = lf_total - crlf
lone_cr = cr_total - crlf
print(f"CRLF={crlf}  LF总数={lf_total}  CR总数={cr_total}")
print(f"=> 纯LF行尾={lone_lf}  纯CR行尾={lone_cr}（lone CR 会让部分读取器与 PS 计数不一致）")

# 其他可能被当作行分隔的 Unicode 字符
for name, ch in (("U+2028 LS", "\u2028"), ("U+2029 PS", "\u2029"),
                 ("U+0085 NEL", "\u0085"), ("U+000B VT", "\u000b"),
                 ("U+000C FF", "\u000c")):
    try:
        n = raw.decode("utf-8").count(ch)
    except UnicodeDecodeError as e:
        print(f"!! UTF-8 解码失败：{e}")
        break
    if n:
        print(f"  发现 {name}: {n} 次")

txt = raw.decode("utf-8")
print(f"Python 按 \\n 分行 = {txt.count(chr(10)) + 1} 行")
print(f"splitlines() = {len(txt.splitlines())} 行")
# PS 的 Get-Content 在多数实现里按 [\r\n|\n|\r] 分行，故应等于 splitlines()
print("\n判定：若 Python splitlines() 与 PS 578 差异大，说明 PS 读取时把某些内容当成了单行")
print("      （最可能是它按 ANSI 解码后遇到无效字节序列而截断/合并）。")
