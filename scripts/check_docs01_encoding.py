# -*- coding: utf-8 -*-
"""确证 docs/01 的真实编码（是磁盘乱码，还是 PowerShell 管道显示问题）。"""
from pathlib import Path

p = Path(r"J:\Projects\llm_for_sec\docs\01-engineering-definition.md")
raw = p.read_bytes()
print(f"字节数 = {len(raw)}")
print(f"首 3 字节 = {raw[:3].hex(' ')}  (efbbbf = UTF-8 BOM)")

txt = raw.decode("utf-8")   # 若这里抛异常 ⇒ 真是坏的
lines = txt.splitlines()
print(f"UTF-8 解码成功，行数 = {len(lines)}")

# 双重编码的特征串（把 UTF-8 字节当 latin-1/cp1252 再解一次会出现的字）
mojibake_marks = ["浠讳綍", "缈昏浆", "鐨勭粺", "锛", "鈽", "鍒ゆ"]
hits = {m: txt.count(m) for m in mojibake_marks if m in txt}
print(f"双重编码特征串命中 = {hits if hits else '无'}")

print("\n--- 最后 6 行（Python 直读，权威）---")
for l in lines[-6:]:
    print("  " + l)

# 与 Select-String 显示的 §11.27 标题对照
print("\n--- 含 §11.27 的行 ---")
for i, l in enumerate(lines, 1):
    if "11.27" in l:
        print(f"  L{i}: {l.strip()}")

print("\nENCODING-CHECK=DONE")
