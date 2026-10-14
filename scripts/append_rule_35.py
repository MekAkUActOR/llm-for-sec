# -*- coding: utf-8 -*-
"""幂等追加 §11.34 / 规则 35 到 docs/01-engineering-definition.md。

规则 35 来历：2026-10-06，我在 m3-needle-reading-pending-caliber.md 里
把 SHOULD-2 的结论押在"基线水位落在 ≈17% 还是 ≈80%"上；
实测基线 = 48.44%，**两分支都没覆盖**。而 SHOULD-2 的判据本来就是配对差值
（不得比起点低超 0.10）——水位不决定结论，差值才决定（−31.25pp 远超容差）。
⇒ 预注册不得把"基线水位区间"当成结论的分支条件。
"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

MARKER = "### §11.34 规则 35"

BLOCK = """
### §11.34 规则 35（预注册不得用"基线水位区间"当结论分支）

**规则 35**：预注册中，**不得**把"基线读数落在哪个区间"写成结论的分支条件；
若判据本身是**配对差 / 配对检验**，预注册必须**直接写差值阈值**，
对基线水位的分支只能是**辅助解释**，**不得**成为"不可判"的免责理由。

**来历（2026-10-06，M3 的 SHOULD-2）**：我在
`reports/m3-needle-reading-pending-caliber.md` 里预先写了两分支——
「基线 ≈17% ⇒ 仪器/口径问题」「基线 ≈80% ⇒ m3-dpo 崩塌确认」。
实测同口径基线 = **31/64 = 48.44%**，**两个分支都没覆盖** ⇒ **预注册框架本身有缺陷**。
而 SHOULD-2 的判据是「不得比起点低超 **0.10**」，
实测配对差 **−0.3125** ⇒ **无论基线是 48% 还是 80%，结论都是 FAIL** ✓
⇒ **水位高低不决定结论，差值才决定**；把结论押在水位上，等于**给自己造了一个
本来不存在的"不可判"出口** —— 这与规则 23（禁止事后放宽）是同一类病的镜像：
不是事后放宽，而是**事前就把判据挂在错误的量上**。

**推论 35.1**：预注册里凡出现「若基线落在 X 区间则……」的写法，
必须同时写明「**无论基线落在哪里，配对差/检验的结论是什么**」。
若写不出这一句，说明**判据挂错了量**，该预注册不得发射。

**★ 同时保留原本正确的部分**：预注册要求"口径缺失时记不可判"是**对的**——
它确实阻止了在只有 raw 基线时下结论（当时若混比 52/64 vs 11/64 就会犯规则 21 的错）。
**该纪律有效，错的只是分支写法。**不得因为本条而削弱口径纪律。
"""


def main() -> int:
    src = DOC.read_text(encoding="utf-8")
    if MARKER in src:
        print("RULE35-APPEND=SKIP（已存在，幂等）")
        return 0
    new = src.rstrip("\n") + "\n" + BLOCK
    DOC.write_text(new, encoding="utf-8")
    # 读回校验
    back = DOC.read_text(encoding="utf-8")
    ok_marker = MARKER in back
    bad = [t for t in ("\ufffd", "锟斤拷") if t in back]
    print(f"RULE35-APPEND={'PASS' if ok_marker and not bad else 'FAIL'} "
          f"marker={ok_marker} mojibake={bad} 行数={len(back.splitlines())}")
    return 0 if ok_marker and not bad else 1


if __name__ == "__main__":
    sys.exit(main())
