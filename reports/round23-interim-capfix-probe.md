# 第 23 轮：M4 capfix 探针 —— **训练中已见修法生效**（中间报告）

**日期**：2026-10-06。**运行**：`configs/m4-capfix-probe.yaml`（300 步 ✓，起点 `soup-needlefix-a050` ✓）
**数据**：`data/m4-run/dpo_m4_capfix.jsonl`（sha256 `D4061D47DF903D91…` ✓）

---

## 一、★★★★★★ 训练曲线：病态签名**已消失**

| step | `rewards/chosen` ✓ | `rewards/rejected` ✗ | `rewards/margins` | `rewards/accuracies` |
|---|---|---|---|---|
| 5 | 0.069 | −0.097 | 0.166 | 0.3375 |
| 10 | 0.547 | −0.646 | 1.193 | 0.8125 |
| 20 | 1.502 | −7.823 | 9.325 | 0.9375 |
| 25 | 1.359 | −7.914 | 9.272 | 0.9375 |
| 30 | 3.413 | −6.872 | 10.29 | 0.9500 |
| 35 | 4.418 | −5.723 | 10.14 | 0.9375 |
| 40 | **+4.462** ✓ | **−4.643** | 9.105 | 0.9125 |

**★ 与 M3（毒 run）末态对照**：

| | `rewards/chosen` | `rewards/rejected` | **比（抬高 : 压低）** |
|---|---|---|---|
| **M3（1,803 步末）** | **+0.34** ✗ | **−12.46** ✗ | **1 : 43** ✗✗ |
| **capfix 探针（40 步）** | **+4.46** ✓ | **−4.64** | **≈ 1 : 1** ✓✓ |

**★★★★★ 判读**：M3 的病态是「**几乎只压低 rejected，不抬高 chosen**」✗。
**去掉 1,320 条 `report`-as-rejected 之后，chosen 侧被真实抬高到 +4.46** ✓
⇒ **梯度天平从 1:43 扳回 ≈1:1** ✓✓
**⇒ 这是对第 22 轮因果结论（`report` 被 rejected 侧压制 ⇒ ASR 崩塌）的**
**同轮、训练中、尚未评测的直接确证**** ✓✓

**★★ 注意**：`rewards/accuracies` 也早早到 0.94 ✓ —— **但这不代表过优化** ✗：
M3 在同一点也是 0.94 ✓，**区别在** chosen 侧有没有被抬高** ✓✓。
（这正是第 22 轮发现的判据：**光看 accuracies 会漏掉病态** ✗。）

## 二、★★★★ 梯度质量分布（本轮新增，用于判定配比）

`scripts/gradient_mass.py`（代理 = 对数 × rejected 平均长度 ✓）：

| 类 | 对数占比 | **质量占比** |
|---|---|---|
| `reserve` | 19.8% | **31.1%** |
| **`policy`（政策条件化 ✗）** | 50.9% | **30.3%** |
| `carrier_inject_hollow` ✓ | 8.0% | 11.0% |
| `bt330_refusal` | 6.6% | 10.9% |
| `carrier_inject_obedient` ✓ | 8.2% | 10.4% |
| `carrier_clean_overrefusal`（已修 ✓） | 4.6% | 5.3% |

**语义分组**：注入抵抗 **21.4%** ✓ / 政策条件化 **30.3%** ✗ / 其它 **48.3%**

**★★ `policy` 族的真实内容**（`scripts/diagnose_policy_pairs.py` ✓）：

| 逐对差异字段 | 不同比例 |
|---|---|
| **`policy`（政策包名 ✓）** | **100.0%** |
| `verdict` | 25.7% |
| `confidence` | 20.9% |
| `findings` | **0.0%** |
| **`action`** | **只 25.7% 不同** ✗（76.4% 逐对相同 ✗） |

**⇒ `chosen` 恒为 `policy: "professional"` ✓、`rejected` 恒为 `policy: "default"` ✓**
**⇒ 这 50.9% 的数据在教「**按政策包调整行为**」✓ 而非安全判断** ✗✓

**★ 这是一个**真实的、尚未修**的配比问题** ✗ —— 建议的下一步（**本轮不做** ✗，留给 M4 全量前）：
**提高注入抵抗的权重** ✓，或**降低 policy 条件化的权重** ✓。

## 三、★ 本轮尚未完成

1. **探针尚未跑完**（120/300 ✓）⇒ **ASR 实测未做** ✗
2. **A/B 对照臂（`dpo_m4_lenmatch` 仅长度 ✓）未跑** ✗ —— 已登记，须在判读前补 ✓
3. **未见载体 ASR 的判据**：须用 `baseline_eval.py` 在同一部署格式下测 ✓
   （168 条 ✓、`--needle-format chat` ✓、512 口径 ✓）

## 四、★ 复核路径

```
configs/m4-capfix-probe.yaml          ← 探针配方（与 m3 超参逐字相同 ✓）
reports/logs/m4-capfix-probe.log      ← 完整日志 ✓
reports/logs/m4-capfix-probe-watchdog.md ← 守望记录 ✓
scripts/gradient_mass.py              ← §二 质量分布 ✓
scripts/diagnose_policy_pairs.py      ← §二 policy 族真相 ✓
scripts/verify_capfix.py              ← 数据修法的 7 项断言 ✓
```
