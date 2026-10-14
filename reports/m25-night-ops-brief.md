# m25-full 夜间作业简报（2026-09-30 凌晨自主执行）

> 面向用户晨间速读。所有动作均在既有授权内（方案 A + 标准自主派发权），
> GPU 侧只有 m25-full 一个训练作业；无沙箱升级请求、无审批阻塞。

## 1. 一句话状态

**M2.5 全量重训（m25-full）健康运行中，预计 12:51 完成训练**；训后评估链、
出口判定器、锚决策器**已就绪并已在 m2 画像上校准**；M3 DPO 配置**已定稿到可
一键发射**；探针 v0.4（污染修正）**已交付**。**当前无阻塞、无需你介入**；
需要在读数后拍板的只有"锚决策"一项（见 §5）。

## 2. 训练实况（截至 02:50）

| 项 | 读数 |
|---|---|
| 起止 | 2026-09-30 ~01:50 起，预计 **~12:51** 完（17,210 步 @ ~2.3 s/it） |
| 进度 | step 1,153/17,210（6.7%），2.35 s/it（baseline 2.10-2.33） |
| 损失 | 1.087 @140 → **0.689-0.881** 区间（下行正常） |
| 显存 | 21.1 / 23.9 GiB（全参 + 优化器态，符合预期） |
| 功率 | 200-290 W @ util 40-100%（该配置正常画像；已向看门狗澄清勿按 350-450W 旧口径误报） |
| checkpoint | checkpoint-500 / -1000 已落盘；看门狗**已验证含 weights + optimizer.pt（4.55GB）= 全量可无损续训** |
| 崩溃保险 | `scripts/m25_full_auto_restart.ps1` 已武装（最多 3 次重启，自动从最新 checkpoint 续） |
| 看门狗 | 已跑 2 轮（R1 01:57 / R2 02:24），日志 `reports/m25-watchdog.log`，30-45 分钟一报 |

## 3. 训练窗口内并行交付（GPU 未受影响）

1. **探针 v0.4 落地**（原"排期"项）：修正 v0.3 的两处系统性污染——
   - `privacy` 换源到英国 ICO 指导页（**非 GDPR 原文**）：90 页 → 423 单元 →
     单元级 8-gram 预筛剔 49（其中 42 个逐字引用 GDPR 被 c0_gdpr 捕获）→ 173 篇；
   - `general_en` 用 C1 **同池哈希补集**（26% 未训标题）重建：600 篇超采样剔 37 → 300 篇，
     成品 vs sft_m25 全量 137,670 行 **0 命中**、vs sec_c1_full 抽样 60,000 行 **0 命中**；
   - 其余六域**字节复制**（SHA256 留档）→ 这六域历史纵向读数完全可比；
   - 残留仅 sec 7 + aisafety 1（既有已裁定的公共公告/arXiv 双侧复用类）。
   证据链：`data/probes/v0.4/README.md`、`reports/probes-v04-build.json`、
   `reports/probes-v04-vs-sft.json`。
2. **出口判定器** `scripts/m25_exit_verdict.py`：四门禁 → 机器可判 VERDICT。
   已在 m2-full 画像上 dry-run **校准**：复现 8/8 顺从、general_en +13.39%、
   general_zh +18.56%、needle 9/12 → **FAIL**，与当时的实况完全一致。
3. **锚决策器** `scripts/m25_anchor_decision.py`：把"M2 期保留的锚 pass vs 接受漂移"
   量化为三选项；同样复现 m2 的 32k +12.89/+16.35% 并触发选项 B。
4. **训后链扩展 + 预检**：`scripts/post_m25_eval.ps1` 新增第 7 步（v0.4 干净口径
   复测 m15 与 m25）与第 8 步（自动出判定）；`scripts/preflight_m25_eval.py`
   报 **0 缺件**（六点行为基线 / PPL 对照 / longctx 对照全在位）。
5. **M3 就绪**：`configs/m3-dpo.yaml` 起点重指向 m25-full，三处【待 M2 读数】
   占位按 docs/07 §2.2 定稿（**lr 2.0e-6 / beta 0.1 / epochs 1**；beta 条件旋钮：
   若 G4 行为保持判 FAIL 则发射前升 0.2）；DPO 数据 47,948 对复核**零 schema 违规**、
   **model-agnostic 无需重导**（`reports/m3-dpo-readiness.md`）。
6. **文档**：`docs/research/m25-backfill-plan.md` → v1.3 + §10.1（本轮交付）；
   `docs/research/probe-contamination-audit.md` 的 v0.4 条由"排期"改"已落地"；
   数据卡走生成器（`scripts/gen_datacard.py` 已加 m25 条目与评估注意事项节，
   避免直改被覆盖）；README 增 M2.5 状态表。

## 4. 今日时间线（自动推进）

```
12:51  训练完成（train_results.json）
  ↓   scripts/post_m25_eval.ps1 自动/看门狗触发
~14:00 评估完：heldout v0.2.1 × 判分器 v2、tool_output 8 条主读数、
       六点行为对照、PPL vs m15（v0.3 门禁口径 + v0.4 干净口径）、
       longctx needle、出口判定器 VERDICT
~14:30 汇总给你（含锚决策的量化输入）
  ↓   判定 PASS → M3 DPO 一键发射；FAIL → 给你失败项与再设计选项
```

## 5. 需要你拍板的（读数后，非阻塞）

**D1 锚决策**（唯一真需要你的项；脚本已把量化输入备好）：
- **A 接受漂移 + 用 v0.4 校正解读**：32k 两语言 ≤ +15% 且行为门禁过 → 直接进 M3（0 GPU 额外开销）；
- **B 跑 PT 回放锚 pass**：32k 任一语言 > +15% 或 needle < 9/12 → 额外 5-10h GPU 拉回 PPL，M3 顺延一天；
- **C 改锚口径**：若 v0.4 显示漂移主要来自探针污染（v0.4 幅度显著小于 v0.3）→ 把 +10% 线改为 v0.4 相对口径。

**D2 出口 FAIL 时的路线**：届时给选项（数据侧补族 vs 阶段侧换配方）。
**D3 用户侧历史项**（不阻塞）：HF token 轮换、平台政策文档粘贴、"法务两问"、
遗留 16 行 M2 期 manifest。
**D4 历史阶梯 v0.4 复测**（建议排期）：base / c1-full / m2-full 在 v0.4 上重测
（约 40-60 分钟 GPU）→ 得到"去污染"的完整纵向曲线；建议放在 M3 发射前或 M3 完成后的空隙。

## 6. 风险与口径备注

- **过拒答风险**：m25 混料里 T5-attack 占 ~17%（m1 为 20.1%），且 m2 的失败模式是
  **欠拒答**（tool_output 8/8 顺从）；G4 行为保持门禁就是为此设的监控项。
- **门禁语义**：通用/32k 门禁用 v0.3 口径（与 base/c1-full/m15/m2* 连续）；
  v0.4 只作**绝对幅度**附注——两域跨版本数值不可直接比较。
- **sec/aisafety 探针残留**（7+1 单元）对所有阶段等权，横向比较仍有效。
- **无回滚需求**：m25 训练不受任何本轮 CPU 侧动作影响；探针 v0.4 是**新增目录**，
  v0.3 原样保留，评估链两条口径并行输出。

## 7. 追加段落（03:00-05:00）：仓库体检发现的真实缺陷

> 触发方式：跑全量单测做"今晚改动是否破坏东西"的验证——结果 491 项里
> **1 失败 1 错误**，且两类问题都**不是本轮引入**，而是历史遗留的诚实性缺陷。

### 7.1 已修复（两处）

| # | 缺陷 | 性质 | 处置 |
|---|---|---|---|
| 1 | `t6_devign` / `t6_devign_lines` / `t6_cvefixes` 三源在 manifest 但 `TIER_MAP` 未分级 → 单测失败 + 数据卡报 `unclassified 45.4M (4.1%)` | 簿记缺失 | 按备忘自身判据补录（**非新政**：§6 已定"许可记账以 canonical 上游为准"，§5 已定 devign_lines 处置方向）：devign **T1**（MIT）/ cvefixes **T1**（CC-BY-4.0 canonical，镜像卡不可信）/ devign_lines **T3**（衍生卡未标 license）。卡片再生后 **unclassified 归零**（T1 229.4M / T3 852.0M）；`d3-ledger-memo` §3 两处清单 + §5 缺口条同步注明 |
| 2 | `tests/test_build_m15_mix.py` 的 `TestReplayComplement` 三个用例**停在已废弃设计上** | 测试失真（**含 2 例空洞通过**） | 2026-09-26 按"用户选 C"重构已废弃 enwiki 摘要补集回放、改为 zhwiki 全文长文回放（`replay_keep(line, min_chars, zh_keep)`），测试未同步：1 例失败（期望 3.8% 密度、实得 0.0）+ 2 例**平凡通过**（断言 `replay ≤ 0.31` 而回放恒 0）+ 端到端 fixture 缺 `c1_zhwiki_gen.jsonl` 报错。已按**现行契约**重写为 `TestReplayZhwikiLongdoc`（长文闸/坏行/title 退化/确定性/阈值单调性/密度 59%/**回放不查 C1 保留集**）+ 补 fixture，3 例→4 例 |
| 3 | 出口判定器 G1 基线常量**与实测相反**（`TOOL_BASE` 记 m2full comply **0/8**，实测 `scored-m2full-tooloutput-v2.json` = **8/8**） | 展示性 bug（门禁判定读当前文件，不影响 PASS/FAIL，但**恰好掩盖 G1"翻转"叙事**：本该显示"从 8/8 顺从翻到 ≤2/8"却显示"从 0/8"） | 常量改为 `(8, 8)` + stdout 也改为读报告字段（原先硬编码在打印串里，改常量不生效）；复验 stdout 与 JSON 均显示 `m2full 8/8 comply`。另：陈旧 dry-run 的 `reports/m25-exit-verdict.{json,md}`（02:24 / 全门禁 PENDING）改名留档为 `.dryrun-20260930-0224.*`，避免与 14:00 的真实读数混淆 |
| 4 | 判定器**缺件路径会崩溃**：打印段硬编码 `gates["G2_general_ppl_vs_m15"]`，一旦参照系改名或某项评估缺失即 `KeyError` | **只在实际缺件时触发**——正是最需要 PENDING 报告的时刻（如某步评估失败）会得到一个崩溃而非报告 | 配合参照系参数化（`--ppl-base/--longctx-base/--behavior-base`，默认 m15/m2full/m2full，**M2.5 调用行为逐字未变**）改为按前缀查找 G2 键；两条路径均验证：默认参照系输出逐字一致、全缺件路径干净报 `PENDING` + 写 JSON（不再崩溃）。另在评估链第 8 步补**判定 JSON 回读**——原先 `Tee-Object` 之后无论脚本是否崩溃都照打 `ALL DONE`，现在会显式打出 `VERDICT=…` 或"判定 JSON 未产出"告警（该 PS1 编辑后已重新加回 BOM 并 PARSE 通过） |

**为什么第 2 条值得单独说**：空洞通过比失败更危险——它让"回放隔离性质已被验证"
成为假信号。**m15 的磁盘产物与谱系不受影响**（重构是既定用户决策，真实 mix 由当时
脚本产出；坏的只是测试的忠实度）。

### 7.2 新发现（需你定口径，非阻塞）

**16 行 M2 期 manifest 行**（原列为用户侧历史项，现已量化）：`status='procured'`、
`est_tokens=0`、无 `ingested_at`，但**原始目录都在盘上**（2026-09-25 抓取，
**合计 1,166.5 MB**），且部分源**确实已入训**（cvalues/pku-saferlhf → DPO 47,948 对；
safety-prompts/wildguardmix/wildjailbreak 登记入 m1）。备忘 §5 早已登记此缺口
（"T2/T3 占比待 SFT mix 定稿后复核"）——**mix 现已定稿，可复核**。
对账表：`reports/manifest-m2-reconciliation.md`（逐源：磁盘体量 / 文档量级 / 入训证据）。
三个待决口径 → **D5**（见 §8）。

### 7.3 新增工具与就绪文档（本轮交付）

- `scripts/audit_manifest.py`——manifest 完备性审计（必需字段 / **记账滞后** /
  **幽灵行** / ingested_at / TIER_MAP 覆盖），可复跑，报告 `reports/manifest-audit.json`；
- `scripts/manifest_m2_reconcile.py`——16 行逐源对账表（只测量不改行）；
- `scripts/check_rlvr_tasks.py` + `reports/m35-tasks-contract.json`——M3.5 任务契约核查
  （2,000 行 = 4 型 × 500，**违规 0**，zh/en 979/1021）；
- `reports/m35-rlvr-readiness.md`——M3.5 就绪文档（奖励层/数据层已验证，
  超参【待 M3 读数】七项，含 **R1 包条件化风险**：包语义仅覆盖 25% prompt，
  建议 M3.5 出口加"同题三包 → 动作分化"一致性检查，防 RL 把 M3 的包条件化洗平）；
- `scripts/pack_consistency.py` + `reports/pack-consistency-sweep.jsonl`——**R1 检查工具已落地并自测通过**
  （`--selftest` 7 项断言全 PASS；打分**复用训练奖励库** `rlvr_reward._component_policy_compliance` 保证同口径）。
  实测：`policy_ruling` 500 行中**期望动作分化行 158 行（31.6%）**，三包 system 提示为共享契约
  → **无需新造探针**，一行题跑三次包即可；扫描题已预生成（40 组 × 3 包 = 120 条，
  seed 20260930）。M3 完成后一条命令出分化率/吻合率/格式错误率；仅 `--run` 的 GPU 生成路径待 M3 时冒烟验证；
- `data/sft/m2.5-staging/README.md` 补齐 fA/fB/fD/fG/t14 五族记录（含经验统计）；
- `docs/research/d3-ledger-memo.md` §3/§5 同步补录；
- `scripts/bind_m25_run.py` + `reports/m25-run-binding.json`——**训练数据绑定记录**  （补一个真缺口：训练启动时**没有任何记录绑定训练集的 sha256**，只有散文提及
  `sft_m25.jsonl`；数据卡对 manifest 做了"语料态绑定"，训练侧却是空白——事后无法
  证明 m25-full 由哪一版混料训出）。已产出并**交叉核验通过**：
  `sft_m25.jsonl` sha256 `915CF6B5…9E6D`、**行数 137,670 / 内容级 zh 43.97%**
  （与审计值 137,670 / 44.0% 一致）、`configs/m25-full.yaml` sha256 `EC5314F1…`。
  **训练完成后重跑同一脚本即得"结束态"绑定**（含 train_results 与全部 ckpt）。
- `scripts/run_auto_restart.ps1`——**通用崩溃保险 + 发射前预检**（把 m25 的一次性脚本
  泛化，供 M3/M3.5 直接复用；`-Check` 单次预检后退出，参数化 `-Config/-OutDir/-MaxRestarts`）。
  内置**续训前提校验**（§7.4 那条隐性约束）与**边角判据报告**：进程链为
  `llamafactory-cli.exe → python(包装) → python(trainer)`，三层命令行都含配置名，
  整链消失才触发重启（方向正确）；但若 trainer 已死而父进程卡住不退，"按进程存在"
  会漏判——`-Check` 会交叉报主日志 mtime 停滞分钟数与 GPU util，>15min 停滞且 GPU 空闲
  时打 ⚠️ 边角告警（**只报告不自动动作**，避免误杀正常的慢存档/慢阶段）。
  实测：`m25-full` 与 `m3-dpo` 两份配置预检均 **PREFLIGHT=PASS**；m25 侧读数
  `checkpoints=2 latest=checkpoint-13000 主日志停滞 0 分钟 GPU 34%`（无假告警）。
  注：**当前跑动仍挂在原来的 m25 专用保险上（不改动在跑的安全网）**，本脚本自 M3 起启用。

### 7.4 体检结果

**全量单测 492 项 OK（rc=0）**。训练侧不受影响（看门狗 R1-R12 全绿；
step 9,184 @ 07:24，2.15 s/it，loss 0.45-0.77，epoch-1 边界 8,605 步**无停顿**跨越；
唯一观察项为 `expandable_segments` 下显存缓升——**R8 后已自行稳定在 21.28-21.35 GiB**
（证实是分配器缓存而非泄漏），已给看门狗明确的后备处置：OOM → 崩溃保险自动从最新
checkpoint 无损续训，**不手工调参**）。

**运维尽职检查（07:30）**：J: 余 **1,320.5 GB**（训练期无写满风险）；
`checkpoints/qwen3-06b-sec-m25-full` 13.35 GB / `save_total_limit=2` 有界；
崩溃保险进程存活（PID 7488，01:52 起）；`train_results.json` 尚未出现（未收尾）。

**评估链↔判定器的接口对账（07:40）**：逐项核对产出/消费文件名，**全部对齐**——
`scored-{tag}-tooloutput-v2.json`（G1，含 `$tag`=m25full 的 tooloutput 子集输出）、
`ppl-m15/m25full-v0.3.json`（G2，PS1 的 `$probeVer='v0.3'` 与判定器 `PROBE_VER="v0.3"` 一致）、
`ppl-*-v0.4.json`（G2 附注，第 7 步）、`longctx-m25full.json`（G3）、
`scored-{tag}-v2.json` + `scored-m2full-v2.json`（G4）。**未发现命名不匹配**——
即 14:00 不会因接口错位而空跑一轮（这正是本次对账的目的）。

**崩溃保险的"无损续训"已实证（08:55）**：此前仅是注释里的假设，现逐环验证——
`configs/m25-full.yaml` 为 `stage: sft`（`can_resume=True`）且**未设**
`overwrite_output_dir`、未设 `resume_from_checkpoint` → 命中 LF
`hparams/parser.py:612-627` 自动续训分支（`get_last_checkpoint(output_dir)`）；
`resume_from_checkpoint` 显式设或 `overwrite_output_dir: true` 都会**破坏该分支**
（后者会从 step 0 重跑并覆盖成果——这是本配置必须保持的隐性约束，已记入纪律）；
`save_total_limit=2` 保留的检查点含 optimizer/scheduler/rng 全状态 → 真无损。
本次确为首跑（主日志无 `Resuming training from`），保险日志仅 `01:52:09 armed`。

**同时发现并已告知看门狗的运维盲点**：重启进程的输出写往
`reports/logs/m25-full-restart<N>.log`（**不是**主日志）——真发生重启时**主日志 mtime 会冻结**，
看门狗若只看主日志会误判"停滞"。已把正确判据交给它（重启日志出现 `restart N/3` 行 +
检查点目录继续增长 + 新日志 mtime/PID 变化，三者同时不符才算 stalled），
并要求它在重启日志中核对 `Resuming training from …checkpoint-NNNN` 这一**无损续训确证行**。

## 8. 决策项汇总（更新）

| 编号 | 决策 | 时机 |
|---|---|---|
| **D1** | 锚决策 A / B / C（见 §5） | 读数后（~14:00） |
| **D2** | 门禁 FAIL 时的路线 | 读数后 |
| **D3** | 用户侧历史项（HF token / 平台政策文档 / 法务两问） | 你有空时 |
| **D4** | 历史阶梯 v0.4 复测排期（~40-60 min GPU） | M3 前后空隙 |
| **D5** | **16 行 M2 期 manifest 记账口径**（新增）：<br>① status 是否统一改 `ingested` + 增设 `role`（train/eval/reference，tc260 保持 ref-only）？<br>② `ingested_at` 填盘上 mtime（09-25 09:49-10:29）还是实际入训日（m1 组装 09-26）？<br>③ `est_tokens` 填**原料层**体量（1,166.5 MB 原始 → 需在卡上另立「SFT 原料层」分区以免与 SFT 产物谱系重复计入总账）还是**实际入训用量**（更贴 M5 权重成分口径，但需逐行溯源）？ | 你有空时（不阻塞训练/M3） |
