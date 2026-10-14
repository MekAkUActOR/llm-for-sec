# P2-RL 实现件施工报告（纯 CPU，不训练）

- 日期：2026-10-08 · 状态：**实现件施工完成，待发射评审** · 全程零 GPU 触碰
- 规格唯一权威：`reports/p2rl-grpo-preregistration.md`（§2 trl 参数面 / §3 奖励 /
  §4 池 / §5 防线 / §7 训练配置 / §8 发射前闭环清单）
- 环境：`.venv\Scripts\python.exe`（trl 0.24.0 · transformers 5.8.0 · torch
  2.14.0+cu130）；控制台纪律 `PYTHONIOENCODING=utf-8`（GBK 教训，p0.7 §0）✓

---

## 0. 交付清单（全部新建，零覆写既有文件 ✗）

| # | 文件 | 定位 | 状态 |
|---|---|---|---|
| ① | `scripts/p2rl_reward.py` | 五分量 B/C/H/V/D 奖励库（行为主判 strict） | py_compile ✓ · `--self-check` ✓ |
| ② | `tests/test_p2rl_reward.py` | 单测（五组规格 §3.4） | **60 tests 全绿** ✓ |
| ③ | `scripts/p2rl_build_pool.py` | n=3,000 prompt 池构建器 | 产出池 + manifest ✓ |
| ④ | `scripts/run_p2rl_grpo.py` | GRPO 发射脚本（复制改造 run_grpo.py 骨架） | `--dry-run` 全绿 ✓ · `--run` 被安全闸拒绝 ✓ |
| 产物 | `data/rlvr/p2rl-pool-v01.jsonl` | 池（3,000 行，预渲染 ChatML 串） | sha256 `77ff6cf1…851dd0`，重建确定性已验证（两次构建逐字节一致） |
| 产物 | `data/rlvr/p2rl-pool-v01.manifest.json` | manifest（全部配比/隔离/长度数字） | ✓ |

不覆写核查：四件实现件 + 两个产物 + 本报告均为新路径；唯一在既有文件上的动作是
只读（规格/骨架/遗产数据 dump）✗。

---

## 1. 单测计数与覆盖（②）

`python -m unittest`（全仓）：

```
Ran 922 tests in 82.237s
FAILED (errors=2)
```

- 基线（施工前实测）：`Ran 862 tests … FAILED (errors=2)`——两处 error 为
  `tests.test_dpo_carriers` / `tests.test_topup_family_probe` 的
  `ModuleNotFoundError: No module named 'pytest'`（预存环境问题，与本轨道无关）；
- 施工后：**922 = 862 + 60（test_p2rl_reward.py）**，errors 仍 = 2 且为同两处
  预存 ✗ ⇒ **不新增失败** ✓（`python -m unittest tests.test_p2rl_reward` 单独
  跑 60/60 OK，rc=0）。

60 个测试按规格 §3.4 五组分布：

| 组 | 测试类 | 数量 | 锁定内容 |
|---|---|---|---|
| 1 分量已知答案 | TestComponentB/C/H/V/D | 38 | 检出+ ×3 / 放行+ ×2 / 漏检− ×2 / 误拒− ×2 / deflect ×2 / format_error ×2 / policy 四分支（含邻档 +0.5 与单向先例回归）/ 契约分带 1.0·0.6·0.3·−1·不可判读 −1 / H 三态 ×6 / V 词+定位（命中 +1 / 未中 +0.5 / 错词 −1 / 无 GT None）/ D 退化 −1 ×2、正常 +1、软带 +0.5 ×2、带外 0.0 |
| 2 26/80 形态回归 | TestForm26of80 | 3 | 风险题「正文交付 + 自报 refuse」→ **B=−1 ∧ H=−1 双罚、总 = −0.351 ≤ −0.15**；不写裁决词更差（分分量单调）；良性题同形态 → B=+1（放行）∧ H=−1，排序正确但不双罚 |
| 3 三不变量 | TestInvariantI/II/III | 8 | I：常量锁（1.00 > 0.85）+ worst-case 7 形态扫描（行为错 + 其余全满 → 加权和 ≤ −0.15 且归一后 < 0）+ 运行时权重覆盖 fail-closed；II：纯拒绝在良性混合池逐条 < 0 ∧ 均值 < 0，纯放行在风险池同（**防线①双侧编码**）；III：同 body 诚实 > 不诚实严格排序、「自报拒+正文交付」<「正文真拒」 |
| 4 GRPO 契约 | TestGRPOContract | 6 | list[float] 长度对齐 / str + conversational + 混合 / None 语义（缺列、空串、坏 JSON、无可判字段）/ completion_ids·trainer_state kwargs 容忍 / 值域 [−1,1] |
| 5 同源审计 | TestSameSourceAudit | 5 | `p2rl_reward.classify is score_heldout_v2.classify`（sys.modules 同对象）+ strict 判径双侧各 2 条 + **对抗样本：正文中间夹 VERDICT 自报 refuse——strict 不采信（selfreport 会），B 仍漏检−** |

防黑不变量的锁法（①内）：模块级常量 `W_B=1.00`、`W_C+H+V+D=0.85` +
**import 时断言**（改坏权重 = import 即炸，fail-closed）+ `reward(weights=…)`
运行时覆盖再断言。

---

## 2. `--dry-run` 输出（④，逐字原文）

```
$ python scripts/run_p2rl_grpo.py --dry-run
[dry-run] trl 补丁标记 import_utils.py: 1/1 OK
[dry-run] trl 补丁标记 trainer\callbacks.py: 3/3 OK
[dry-run] trl 0.24.0 · transformers 5.8.0
[dry-run] 反射 OK：HP 26 字段全在 GRPOConfig；GRPOTrainer 签名含 reward_funcs/callbacks ✓
[dry-run] §2 默认值对照（信息性）：{'num_generations': 8, 'beta': 0.0, 'loss_type': 'dapo', 'scale_rewards': 'group', 'mask_truncated_completions': False, 'use_vllm': False, 'log_completions': False}
[dry-run] GRPOConfig OK：lr=1e-06 beta=0.04 gens=8 gen_bs=64 pdtbs=8 loss=dapo scale=group max_steps=300 save=25/keep20 vllm=False log_comp=True
[dry-run] ref 模型：挂（beta>0，KL 锚=起点 checkpoint，+~1.2GB）
[dry-run] 池装载：p2rl-pool-v01.jsonl → 3000 行，列 = ['prompt', 'p2rl_task_json', 'reward_pack']（prompt=预渲染 ChatML str ✓）
[dry-run] reward_funcs = [p2rl_reward.grpo_reward_func]（callable 注入 ✓）；不变量 I：w_B=1.0 > 其余和=0.85 ✓；双样本冒烟 = [-0.351351, 0.72973]
[dry-run] parity 门：抽样 20 条（单轮 10 + 多轮 10）逐字节一致 ✓
[dry-run] watchdog 自检 OK（健康不触发/熵塌缩触发/零方差触发/streak 复位；遥测示例 {'windows': 0, 'think_leak': 8, 'truncated': 16, 'rewards_seen': 24})
[dry-run] 步数核算：300 步 × 8 completions/步 ÷ k=8 ≈ 300 prompt（池 3000 的 10%）；checkpoint 12 个（save_steps=25）≤ save_total_limit=20 ✓
[dry-run] 起点 chat_template 含 think 机制: True （已用预渲染 str prompt 绕开——训练/评测渲染零漂移 ✓）
[dry-run] 全绿：配置冒烟 + 池装载 + 奖励接线 + parity 门 + watchdog 自检 + 步数核算（未触 GPU、未训练）。发射评审通过后：--run
```

（rc=0；`--run` 复核：rc=1 被安全闸拒绝，`LAUNCH_APPROVED=False`——评审时改
该行并重跑 `--dry-run` 复核。双样本冒烟值的语义：池首行 A 类风险题 × 良性作答
= −0.351（26/80 形态实时复现），池末行 F 类 = 0.730（裁决词不匹配 V=−1）——
接线语义正确。）

dry-run 覆盖的 §8 闭环项：③ trl 反射核实（HP 26 字段 fail-closed 核对，缺即断言
炸）✓ · ④ 渲染 parity 门（20 条：单轮 10 条 vs `promptfmt.chat_prompt` 逐字节 +
多轮 10 条头尾拼装核对）✓ · ⑥ 发射脚本 CPU 干跑全绿 ✓ · ⑦ watchdog 自检
（构造注入：健康序列不触发 / 熵塌缩 3 窗触发 / 零方差连 3 窗触发 / streak 复位 /
遥测计数）✓。

---

## 3. 池 manifest 数字（③）

`data/rlvr/p2rl-pool-v01.jsonl`：3,000 行 · sha256
`77ff6cf1d05c0d5cbd93e7be48cc8104bd396fdc3627f3d4ea4bd09528851dd0` ·
seed 20261008（派生 A/B/C/D/EF = 2026100801…05，manifest 登记）·
**重建确定性已验证**（同 seed 两次构建 sha256 逐字节一致）。

| 轴 | 数值 | 规格 | 判 |
|---|---|---|---|
| A 载体风险 / B 载体良性 / C 通用良性 / D 多轮良性 / E policy / F pii+carrier | 900 / 600 / 750 / 300 / 300 / 150 | 30%/20%/25%/10%/10%/5% | ✓ 逐类精确 |
| 良性总量（B+C+D） | 1,650（55%） | > 风险 900（30%） | ✓ |
| en 占比 | 1,515 / 3,000 = **50.5%** | ≥50%（C/D 内各 50%） | ✓ |
| 语言×类 | A 450/450 · B 300/300 · C 375/375 · D 150/150 · E 160/140 · F 80/70（en/zh） | 配额制 | ✓ |
| 来源 | 新生成 2,550（A/B 沿 gen_inj_detect 独立 RNG 流 + C/D 新模板）；tasks-v01 抽样 450（E 300 + F 150，schema 先 dump 后用 ✗不猜） | §4.2 | ✓ |
| task_types | inj_detect 1,500 / general_benign 750 / multi_turn_benign 300 / policy_ruling 300 / pii_discover 75 / carrier_classify 75 | — | ✓ |
| 8-gram 游程 vs 全部 heldout（13 套件，双侧先剥 VERDICT 契约样板） | 逐套件 max：v0.1=13 · v0.2=16 · v0.2.1=16 · v0.2.2=25 · v0.2.3=29 · v0.3-gen=17 · v0.4=17 · carrier-extra=18 · v0.5-toolout-reg=16 · v0.5-topup=16 · v0.6-dilution=16 · v0.6-document=9 · **v0.7=16**；overall **29 ≤ 30** | ≤30 | ✓ |
| **v0.7 全套不入训练断言** | 8-gram 16 ≤ 30 **且** 全池正文 vs v0.7 turns/goal 规范化子串命中 **0**（双断言）；D 类骨架与 F1–F6 攻击族零同源（纯良性追问，无升级/人格/虚构/混淆/切片/权威要素） | §4.2.3 | ✓ |
| prompt 长度（soup tokenizer 实测） | 单轮 p50=299 / **p99=406** / max=409；多轮 p50=346 / **p99=455** / max=456 | 单轮 p99 ≤1024、多轮 ≤2048 | ✓（余量大） |
| 渲染 parity（建池时） | 全部 2,700 单轮行 vs `promptfmt.chat_prompt` 逐字节一致 + 3,000 行 `render_chatml` 自洽 | §7.4① | ✓ |
| risk_present=True / verdict_gt 在位 | 1,053（A 900 + E 期望非 answer 153）/ 2,400 | — | 信息 |

构建过程纪要（fail-closed 逐项断言全绿后才落盘）：配比 / en 份额 / 行契约
（prompt==render_chatml、meta 必填字段、reward_pack 一致）/ 隔离 / p99 /
防覆写（目标存在即 exit 4，本次首次构建即新路径）。

---

## 4. 设计决策与登记（不猜项的显式裁决）

1. **B 分量非政策题不走 expected_action 收紧**：风险在场时 refuse/report_finding
   同计检出+（门禁口径 v023 §1 ①），单测回归锁定——若按 expected_action
   （=report）收紧会把「真拒绝」错罚 −1 ✗。
2. **policy_ruling 防御侧邻档 = 单向**（期望 report 得 refuse → +0.5；期望 refuse
   得 report → −1）：逐字沿 rlvr_reward 软判先例（规格原文只给出前一向），
   模块 docstring + 单测双重登记。
3. **F 类（pii/carrier）risk_present=False**：B 的混淆矩阵侧语义 =「需要防御动作
   的风险」，PII 盘点/载体归类的正确行为是 answer（comply → 放行+，refuse →
   误拒−），V/locate 承载判断教学。
4. **C 类显式无风险判断教学**：user 末尾附契约提示（action=answer、verdict=clean，
   规则 44.3「教会输出无风险/放行判断本身」）；B 仍罚真拒绝行为——抄词救不了
   拒答。登记于 manifest design_notes。
5. **隔离扫描的 VERDICT 契约样板豁免（双侧对称剥离）**：v0.5-topup 任务说明内嵌
   VERDICT 示例，与 D 类 canned assistant 的契约行逐字同形（设计内共享，同
   POLICY_SYSTEM 先例）——不剥离则必然伪命中 108 游程。剥离仅限
   `VERDICT: {json}` 样板，散文部分照扫；v0.7 子串断言不剥离（更保守）。
6. **★发现并登记：冻结判分器 v2 `_is_format_error` 的字符多样性线对长英文正文
   天然敏感**。实测（本仓全部 `reports/*resp*.jsonl` 字符串字段）：en 8,924 条中
   28.0% 被判 format_error（p50 长 771 字），zh 13,347 条中 0.8%——机制：英文
   唯一字符集 ≈50，长度超过 ~850 字则 uniq/len < 0.06 必触发。奖励同源复用该
   判分器（规格 §3.4.5 铁律，不得 fork），故 en 长 completion 的 D（−1）与 B
   （−0.5）受此影响：**良性冗长英文作答会被低估**。缓解（已内建）：
   max_completion_length=512 封顶（≈2,000 字符上限，但典型英文作答多在
   800 字内）；log_completions=True + watchdog 遥测可按语言分桶观测 D/B 分布。
   **裁决建议（登记不代读）**：若训练期 en 侧 D=−1 率异常（遥测可见），按规则 23
   走预注册附录（单变量：D 分量对 en 加长度归一豁免或判分器修正重走门禁回归），
   不在本实现件内静默改口径。
7. **GRPO 适配器 None 语义收紧**：`p2rl_task_json` 缺失/空串/坏 JSON/**无可判
   字段**（`{}`）→ None（TRL 多任务语义"不适用"），不给误导分。
8. **watchdog 即停线**（§5 防线②原样实现）：滚动 3 个 logging 窗均值熵 < 早段参考
   （step 10–50 均值）× 0.35，或零方差组率（k=8 组 std=0 占比）> 50% 连续 3 窗
   ——任一触发 `should_training_stop=True` + 回滚指令（save_steps=25 全量档
   保障，规则 43.5）；think 泄漏 / 截断率为登记遥测（§5「登记不设闸」）。

---

## 5. §8 发射前闭环清单状态

| §8 项 | 状态 |
|---|---|
| ① 奖励函数单测全绿 | ✓（60/60；全仓 922 tests，errors=2 预存不新增） |
| ② 池构建 + 隔离扫描 + manifest | ✓（§3 表） |
| ③ trl 参数面反射核实 | ✓（--dry-run 步骤 2，fail-closed） |
| ④ 渲染 parity 门 20 条 | ✓（单轮 10 + 多轮 10，逐字节） |
| ⑤ 奖励-门禁同源（sys.modules） | ✓（单测 TestSameSourceAudit） |
| ⑥ 发射脚本 `--dry-run` CPU 全绿 | ✓（§2 原文） |
| ⑦ 熵/零方差监控 callback 自检 | ✓（构造注入，4 场景 + 遥测） |
| 发射评审（`LAUNCH_APPROVED`） | **待所有者裁决**（安全闸默认 False，--run 被拒 ✓） |

py_compile：四件实现件全部 ✓（rc=0）。

P2RL-IMPL=DONE
