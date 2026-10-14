# -*- coding: utf-8 -*-
"""诊断 obj2_remeasure.ps1：BOM 状态 + 定位引号/括号失衡的确切行。"""
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\scripts\obj2_remeasure.ps1")
raw = P.read_bytes()
print(f"文件 = {P}")
print(f"字节数 = {len(raw)}")
print(f"前 4 字节 = {raw[:4].hex(' ')}")
has_bom = raw.startswith(b"\xef\xbb\xbf")
print(f"有 UTF-8 BOM = {has_bom}")

txt = raw.decode("utf-8-sig")
lines = txt.splitlines()
print(f"行数 = {len(lines)}")

# 逐行统计引号奇偶（忽略反引号续行与注释行）
print("\n--- 逐行双引号计数（奇数的行可疑）---")
for i, ln in enumerate(lines, 1):
    stripped = ln.strip()
    if stripped.startswith("#"):
        continue
    n = ln.count('"')
    if n % 2 == 1:
        print(f"  L{i:>3} 双引号 {n} 个: {ln}")

print("\n--- 逐行花括号/圆括号平衡（含累计）---")
depth_c = 0
depth_p = 0
for i, ln in enumerate(lines, 1):
    s = ln.strip()
    if s.startswith("#"):
        continue
    # 去掉单引号串内内容（粗略）
    depth_c += ln.count("{") - ln.count("}")
    depth_p += ln.count("(") - ln.count(")")
    if depth_c < 0 or depth_p < 0:
        print(f"  L{i:>3} 负深度 c={depth_c} p={depth_p}: {ln}")

print(f"\n累计 花括号={depth_c} 圆括号={depth_p}（应为 0）")
print("\nDIAG-OBJ2=DONE")
