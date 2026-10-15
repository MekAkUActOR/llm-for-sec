# 磁盘治理报告：checkpoints 无效子检查点清理（2026-10-16）

- 执行：disk-keeper（DSH Agent Teams 成员）
- 委托：Team Lead 任务书（2026-10-16）
- 封盘依据：`reports/handover-20261014-0800.md` §十七～§二十三（12 个训练臂全部 H0 判负封盘；§二十 M5B-R5-GATES=DONE、§二十二 M5A-R5-GATES=DONE、§二十三 M5A-R6-GATES=DONE）
- 逐条删除留痕日志：`reports/disk-cleanup-20261016-execution.log`
- 状态：**已执行完毕**（2026-10-16 01:00–01:01，127/127 删除成功，实测释放 503.997 GB，保留件完整）

## 一、清理政策（照录任务书要点）

1. **永久保留**：`soup-needlefix-a050` 全目录（谱系起点，每轮训练都在用）；`qwen3-06b-sec-m5a-dpo-r5` 全目录（全史最优臂 3/5 合取，推荐资产）；`qwen3-06b-sec-m5a-dpo-r6` 全目录（r7 正在复用其数据资产）；所有臂目录中的**终末子检查点**（最大编号者，门禁评测证据件）；所有臂目录的**根目录散件**（config.json / trainer_state.json / tokenizer 等非 checkpoint-* 文件）。
2. **可删**：其余 `qwen3-06b-sec-*` 臂目录内的**中间** checkpoint-* 子目录（非终末编号）。每臂删前先列出该目录全部 checkpoint-* 子目录并确定终末者（最大编号），只删小编号的。
3. **禁区**：`data\`、`reports\`、`scripts\`、`configs\`、`.cache\`、任何非 `checkpoints\` 路径；`qwen3-06b-sec-m5a-dpo-r7*`（新臂，训练中或即将训练）。
4. **删除方式**：PowerShell `Remove-Item -Recurse -Force`；每次删除前 `Resolve-Path` 核验目标路径确在 `J:\Projects\llm_for_sec\checkpoints\` 下且属可删清单。
5. **歧义处理**：不在保留/可删两类清单中的臂 → 保留并登记待询，不删。

## 二、盘点结果（清理前，2026-10-16 00:53）

- **J 盘**：已用 1266.46 GB / 剩余 641.25 GB
- `checkpoints\` 下共 38 个目录：29 个 `qwen3-06b-sec-*` + 9 个 `soup-needlefix-*`
- checkpoint-* 子目录共 **164 个**，合计 **667.03 GB**（逐目录 `Get-ChildItem -Recurse` 实测求和）
- **全树无任何 reparse point**（symlink/junction 已扫描）→ `Remove-Item -Recurse` 无越界风险
- `qwen3-06b-sec-m5a-dpo-r7*` 不存在 → 禁区无冲突
- 单个子检查点实测体积分档：CPT 全量臂 ~6.67 GB；DPO/ORPO 臂 ~4.22 GB；GRPO 臂 ~3.34 GB；早期冒烟臂 ~2.23 GB

## 三、保留清单（逐项核验）

### 3.1 全目录保留（3 项，一个字节不动）

| 目录 | 内容 | 保留理由 |
|---|---|---|
| `soup-needlefix-a050` | 6 个散件（model.safetensors/config.json/tokenizer 等） | 谱系起点，每轮训练都在用 |
| `qwen3-06b-sec-m5a-dpo-r5` | checkpoint-50/100/150/200/250/300 共 6 个 + 全部散件 | 全史最优臂（五合取 3/5，十一臂最高），推荐资产（handover §二十二） |
| `qwen3-06b-sec-m5a-dpo-r6` | checkpoint-50/100/150/200/250/300 共 6 个 + 全部散件 | r7 正在复用其数据资产（handover §二十三） |

### 3.2 终末子检查点保留（每臂最大编号，门禁证据件）

25 个被清理臂各保留终末子检查点 1 个（明细见 §四 最右列），加上 r5/r6 全量 12 个，合计保留 checkpoint-* 子目录 **37 个、约 163.04 GB**。

### 3.3 根目录散件（全部保留，零改动）

所有臂目录下的非 checkpoint-* 文件（config.json、generation_config.json、tokenizer.json、tokenizer_config.json、chat_template.jinja、model.safetensors、trainer_state.json、trainer_log.jsonl、train_results.json、all_results.json、training_args.bin、README.md、*.png 等）全部保留，本次清理未触碰任何一个散件。

### 3.4 歧义登记（保留待询，未删）

| 目录 | 状态 | 处置 |
|---|---|---|
| `soup-needlefix-a020 / a035 / a038 / a040 / a042 / a045 / a065 / a080`（8 个） | 仅含散件，无 checkpoint-* 子目录；不在保留清单（保留仅 a050）也不在可删清单（可删仅 qwen3-06b-sec-*） | **保留待询**：按歧义政策不删；如需清理请 Lead 明示 |
| `qwen3-06b-sec-m16` | 仅 1 个散件 trainer_log.jsonl，无 checkpoint-* 子目录 | 无可删对象，原样保留 |
| `qwen3-06b-sec-m3base-topup-e2-epoch1-cp200` | 仅散件（本身是导出的 cp200 模型目录），无 checkpoint-* 子目录 | 无可删对象，原样保留 |

## 四、删除清单（25 臂 / 127 个子目录 / 预估 503.997 GB）

编号规则：每臂终末 = 最大编号（下表"终末保留"列），其余全部为中间件、删除。

| # | 臂目录 | 删除的中间子检查点 | 个数 | 预估 GB | 终末保留 |
|---|---|---|---|---|---|
| 1 | qwen3-06b-sec-c0-smoke | checkpoint-100 | 1 | 2.231 | checkpoint-137 |
| 2 | qwen3-06b-sec-c1-full | checkpoint-2050 | 1 | 2.231 | checkpoint-2072 |
| 3 | qwen3-06b-sec-m15 | checkpoint-110 | 1 | 6.672 | checkpoint-115 |
| 4 | qwen3-06b-sec-m16-32k | checkpoint-50 | 1 | 6.672 | checkpoint-58 |
| 5 | qwen3-06b-sec-m25-full | checkpoint-17000 | 1 | 6.673 | checkpoint-17210 |
| 6 | qwen3-06b-sec-m2-calib | checkpoint-250 | 1 | 6.672 | checkpoint-292 |
| 7 | qwen3-06b-sec-m2calib-needlefix-e1 | checkpoint-280/300/320/340 | 4 | 16.896 | checkpoint-360 |
| 8 | qwen3-06b-sec-m2-full | checkpoint-12000 | 1 | 6.673 | checkpoint-12294 |
| 9 | qwen3-06b-sec-m3base-topup-e1 | checkpoint-150/200 | 2 | 13.344 | checkpoint-207 |
| 10 | qwen3-06b-sec-m3base-topup-e2 | checkpoint-350/400 | 2 | 13.344 | checkpoint-414 |
| 11 | qwen3-06b-sec-m3-dpo | checkpoint-1500/1600/1700/1800 | 4 | 16.900 | checkpoint-1803 |
| 12 | qwen3-06b-sec-m4-capfix-full | checkpoint-1500/1600/1700/1800 | 4 | 16.896 | checkpoint-1803 |
| 13 | qwen3-06b-sec-m4-capfix-probe | checkpoint-50/100/150/200/250 | 5 | 21.120 | checkpoint-300 |
| 14 | qwen3-06b-sec-m4c-orpo-full | checkpoint-100/200/300/400/500/600/700/800/900/1000/1100/1200/1300/1400/1500/1600/1700/1800 | 18 | 76.032 | checkpoint-1803 |
| 15 | qwen3-06b-sec-m4c-orpo-probe | checkpoint-50/100/150/200/250 | 5 | 21.120 | checkpoint-300 |
| 16 | qwen3-06b-sec-m5a-dpo-probe | checkpoint-50/100/150/200/250 | 5 | 21.120 | checkpoint-300 |
| 17 | qwen3-06b-sec-m5a-dpo-r2 | checkpoint-50/100/150/200/250 | 5 | 21.120 | checkpoint-300 |
| 18 | qwen3-06b-sec-m5a-dpo-r3 | checkpoint-50/100/150/200/250 | 5 | 21.120 | checkpoint-300 |
| 19 | qwen3-06b-sec-m5a-dpo-r4 | checkpoint-50/100/150/200/250 | 5 | 21.120 | checkpoint-300 |
| 20 | qwen3-06b-sec-p2rl-grpo-v1 | checkpoint-25/50/75/100/125/150/175/200/225/250/275 | 11 | 36.762 | checkpoint-300 |
| 21 | qwen3-06b-sec-p2rl-grpo-v2 | checkpoint-25/50/75/100/125/150/175/200/225/250/275 | 11 | 36.762 | checkpoint-300 |
| 22 | qwen3-06b-sec-p2rl-grpo-v3 | checkpoint-25/50/75/100/125/150/175/200/225/250/275 | 11 | 36.762 | checkpoint-300 |
| 23 | qwen3-06b-sec-p2rl-grpo-v4 | checkpoint-25/50/75/100/125/150/175/200/225/250/275 | 11 | 36.762 | checkpoint-300 |
| 24 | qwen3-06b-sec-p2rl-grpo-v5 | checkpoint-25/50/75/100/125/150/175/200/225/250/275 | 11 | 36.762 | checkpoint-300 |
| 25 | qwen3-06b-sec-stage1-202m | checkpoint-350 | 1 | 2.231 | checkpoint-385 |
| | **合计** | | **127** | **503.997** | 25 个终末 |

注 1：`qwen3-06b-sec-m2calib-needlefix-e1` 的 checkpoint-300 是**中间件**（终末为 360），已列入删除——"终末=最大编号"规则优先于"通常 300"的直觉。
注 2：早期/传承臂（c0-smoke、c1-full、m15、m16-32k、m25-full、m2-calib、m2-full、m2calib-needlefix-e1、m3base-topup-e1/e2、m4-capfix-full、stage1-202m）按任务书可删条款中"及其它 qwen3-06b-sec-* 未列保留者"的兜底授权纳入清理，仅删中间子检查点，终末与散件保留。

## 五、执行记录（2026-10-16 01:00:06 – 01:01:37，先小后大共 6 批）

| 批次 | 臂 | 实删子目录 | 实测释放 GB | 结果 |
|---|---|---|---|---|
| 1（试点） | c0-smoke | 1 | 2.231 | ✓ 终末 137 完好 |
| 2 | c1-full / m15 / m16-32k / m25-full / m2-calib / m2-full / stage1-202m | 7 | 37.824 | ✓ 7 终末完好 |
| 3 | m2calib-needlefix-e1 / m3base-topup-e1 / e2 / m3-dpo / m4-capfix-full | 16 | 77.380 | ✓ 5 终末完好（含 m2calib checkpoint-300 作为中间件删除、终末 360 保留） |
| 4 | m4-capfix-probe / m4c-orpo-probe / m5a-dpo-probe / r2 / r3 / r4 | 30 | 126.720 | ✓ 6 终末完好 |
| 5 | m4c-orpo-full | 18 | 76.032 | ✓ 终末 1803 完好 |
| 6 | p2rl-grpo-v1..v5 | 55 | 183.810 | ✓ 5 终末完好 |
| | **合计** | **127** | **503.997** | **与 §四 预估逐项一致，零偏差** |

每条删除均过五道防线（全部通过，零异常、零中止、零越界）：

1. `Resolve-Path` 核验臂目录与目标子目录均解析于 `J:\Projects\llm_for_sec\checkpoints\` 之下；
2. 硬护栏：臂名必须匹配 `qwen3-06b-sec-*`，且正则拒绝 `m5a-dpo-r5$ / m5a-dpo-r6$ / m5a-dpo-r7* / soup-*`；
3. 目录快照一致性：该臂 checkpoint-* 数量与盘点数一致（防盘点后目录变化）、终末编号与预期一致（防误判终末）；
4. 目标确认为普通目录（非 reparse point）；
5. `Remove-Item -Recurse -Force` 后 `Test-Path` 复核确已删除。

逐条留痕（127 条 DEL、37 条 KEEP、每臂 ARM-DONE、每批次前后磁盘快照）见 `reports/disk-cleanup-20261016-execution.log`。

## 六、前后磁盘对比

| 时点 | J 盘已用 GB | J 盘剩余 GB |
|---|---|---|
| 清理前（2026-10-16 00:53） | 1266.46 | 641.25 |
| 清理后（2026-10-16 01:01） | 765.61 | 1142.10 |

- 剩余空间净增 **+500.85 GB**；逐目录实测释放 **503.997 GB**。
- 差值约 3.15 GB：执行窗口内 J 盘存在与本项目无关的并发写入（试点批前后曾观测到 ~2.4 GB/7min 的外来写入），不影响清理正确性；checkpoint-* 总占用 667.03 GB → 约 163.03 GB，与实测释放量闭环。

## 七、保留件完整性抽查（清理后全量复核）

1. **checkpoint-* 存活数 = 37**（25 个清理臂终末各 1 + r5 全 6 + r6 全 6），与政策预期完全一致；每个清理臂目录内仅剩其终末子检查点。
2. **soup-needlefix-a050 完整**：6 个散件在位，model.safetensors = 2,384,235,064 字节 ✓
3. **m5a-dpo-r5 完整**：checkpoint-50/100/150/200/250/300 全 6 个在位；终末 checkpoint-300 内容完整（11 文件：model.safetensors 2,384,234,968 B、optimizer.pt 2,140,052,313 B、trainer_state.json 33,955 B、tokenizer/scheduler/rng_state 等）✓
4. **m5a-dpo-r6 完整**：同上全 6 个在位，终末 checkpoint-300 为 11 文件全套（trainer_state.json 34,094 B）✓
5. **清理臂终末抽查**（文件数与体积均与清理前一致）：c1-full\checkpoint-2072（8 文件，2.231 GB）、m4c-orpo-full\checkpoint-1803（11 文件，4.224 GB）、p2rl-grpo-v1\checkpoint-300（11 文件，3.342 GB）、m2calib-needlefix-e1\checkpoint-360（11 文件，4.224 GB）✓
6. **根目录散件零改动**：各臂散件数与清理前盘点逐一相符（如 c0-smoke 13、m2calib-needlefix-e1 15、m3-dpo/m4 系 14、p2rl 系 8、soup 系各 6）✓
7. **无越界**：全部删除目标均在 `checkpoints\` 之下；`data\`、`reports\`、`scripts\`、`configs\`、`.cache\` 未发生任何删除（`reports\` 仅新增本报告与执行日志两个文件）；`qwen3-06b-sec-m5a-dpo-r7*` 全程未出现。

## 八、遗留待询与裁定（soup-needlefix 变体目录）

`soup-needlefix-a020 / a035 / a038 / a040 / a042 / a045 / a065 / a080` 共 8 个目录（各 6 个散件，合计约 19 GB 量级）不在任务书保留清单（保留仅 a050）也不在可删清单（可删仅 qwen3-06b-sec-*）→ 按歧义政策未删，登记待裁示。

**保留裁定 2026-10-16（Team Lead，message team-message-41e040cf-bb98-4f56-ba2b-d0e1eb61c2dd）**：本轮保留，不删。理由：a050 为最终谱系起点已成定局，但变体是汤选择的消融历史件，删除收益仅 19GB（现剩余 1142GB，零压力）而对未来复现实验有非零风险。**磁盘压力回撤线 = J 盘剩余 <100GB 时再议**。
