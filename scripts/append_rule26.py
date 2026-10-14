# -*- coding: utf-8 -*-
"""追加规则 26 到 docs/01。"""
from pathlib import Path

p = Path("docs/01-engineering-definition.md")
t = p.read_text(encoding="utf-8")
assert "规则 26" not in t, "已追加过"

BLOCK = """
### 11.26 规则 26 — **每个 MUST 门必须有"会失败的证据"**；门禁的实现级别必须与预注册逐一对齐（2026-09-30 晚实证）

**实证**：`scripts/topup_verdict.py` 承载预注册的 MUST-A/B/C 三个 MUST 门。
实测（`reports/criterion-fix-mustc-orr.md`）发现：

1. **MUST-C 读 `alignment_counts()` 不存在的键**（`over_refusal_rate`、`refuse`）
   ⇒ 回退路径分子取默认 0 ⇒ 基线与变体**双双 0.0** ⇒ **MUST-C 结构上永远 PASS**。
2. **MUST-C 被追加进 `out["should"]`** 而 `out["must"]` 只赋值一次（仅 MUST-A）
   ⇒ 即使修好第 1 条，MUST-C 失败也只登记"有条件成立"，**不阻断**。
3. **MUST-B 完全没有实现**（契约保留率只存在于旧的 `judge_soup.py`）。
4. 历史产物 `topup-verdict-soup-a050.json` 逐字记录 `ORR base=0.0 var=0.0 verdict=PASS`
   ⇒ **"采用 soup-a050 作 M3 起点"这一裁定是在 MUST-C 空泛通过下作出的**。

⇒ **三个 MUST 门里，只有 MUST-A 是活的**，而 objective ① 当时自认"判据漏洞 I1–I6 已修完"。

**本规则（三条，均可机械检验）**：

1. **级别对齐**：`topup_verdict.py` 的 MUST 门集合必须与预注册
   `reports/*-preregistration.md` 的 MUST 行**逐字对应**；MUST 门**不得**出现在 `should` 列表里。
   *检验*：`tests/test_topup_verdict_gates.py::test_mustc_not_appended_to_should` +
   `must_gates` 必含 MUST-A/B/C。
2. **"会失败的证据"**：每个 MUST 门必须至少有**一个会判 FAIL 的真实臂对照**被记录在案。
   *理由*：一个从未在任何真实数据上判过 FAIL 的门，与其"通过"了，在证据上**不可区分**。
   *检验*：本规则入档时给出的对照是 `soup-a050 vs m2-calib` ⇒ MUST-C **FAIL**（9/54 vs 5/54，+7.41pp）。
3. **禁止静默回退**：读不到的键、缺的文件、为 0 的分母一律记 **blocker**（fail-closed），
   **不得**回退到某个默认值再照常判定。默认值是最隐蔽的 fail-open——
   它把"没测到"伪装成"测到了且没问题"。
   *检验*：`contract_rate()` 与 ORR 分母缺失时均产生 blocker 的断言。

**与规则 25 的关系**：规则 25 要求"指标名与测量对象一致"；规则 26 要求"**门的死活本身要被验证**"。
二者合起来才完整：名称对了，门还必须真的能关。

**我给自己的批评（保留）**：我在 14:21 跑过 `topup_verdict.py --variant soup-a050` 并
**接受**了它的 `decision`，却未核对 `ORR base=0.0 var=0.0` 这个**明显不可能**的读数
（54 条对齐条目上误拒率恰为 0，且基线与变体完全相同）。这是"看结论不看数"，与本会话早前
"把源码注释当成事实"同源。**接受一个结论前，先看它赖以成立的数是否可能为真。**
"""

p.write_text(t.rstrip() + "\n" + BLOCK, encoding="utf-8")
print(f"✅ 已追加；行数 = {len(p.read_text(encoding='utf-8').splitlines())}")
