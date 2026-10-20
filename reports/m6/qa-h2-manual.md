# M6 验收 harness 使用手册（qa-m6，H2 稳定版）

> 面向：H20 验收轮执行者（qa-m6 本人 / 00:00 交接后继者 / Lead 复核）。
> 环境：`J:\Projects\llm_for_sec`；`.venv\Scripts\python.exe -X utf8`；GPU 用前 nvidia-smi + 板上预约（§9 时隙）。

## 0. 一图流（验收轮完整序列）

```
① leak-check 复检（若数据再动）        scripts\m6_leak_check.py --tag <tag>
② v1 dev 推理                          scripts\m6_infer.py --head checkpoints\m6-v1 --input <dev-in> --output <dev-out>
③ QA 独立选点（→运行点 v1）            scripts\m6_acceptance.py --mode select-op ...
④ deveng calib.json 对照                双报差 >1pp 逐任务核对（防调参欺诈）
⑤ 验收全跑（heldout+challenge+ood+红队+参照）
                                        scripts\m6_acceptance.py --mode run --tag v1 --head checkpoints\m6-v1 --runpoint reports\m6\operating-point-v1.json
⑥ 敏感性注入重跑（θ±0.05×3）           m6_infer --thresholds-json（样本级第二口径）
⑦ 报告终稿                             qa-report-<tag>.md + qa-report-TEMPLATE.md 人工段
⑧ 复算验证                             --mode recompute（标签快照→同读数）
```

## 1. 模式速查

| 命令 | 用途 | 关键产物 |
|---|---|---|
| `--mode smoke [--stub]` | 管线端到端自检（红队 10 条+stub 回归+映射统计） | smoke-* 校验输出 |
| `--mode map` | 冻结套件→m6-sample 映射（只读 data/heldout） | reports/m6/mapped/*.jsonl + frozen-suite-mapping.json |
| `--mode select-op --dev-preds <dir> --dev-labels <f> --dev-manifest <sha>` | dev 选点→冻结运行点（QA-1 §4.1 网格+可行域） | operating-point-v<k>.json（m6-thresholds schema 校验内嵌） |
| `--mode run --tag <t> --head <ckpt> [--runpoint <f>] [--stub]` | 全量验收：推理→指标→六门→verdict | qa-report-<t>.md + eval-<t>.json + per-item + labels 快照 |
| `--mode recompute --preds-dir <dir> --tag <t2>` | 从快照复算（无 GPU，复核用） | qa-report-<t2>.md（读数应与 run 一致） |

## 2. select-op 数据准备（以基线为例）

```
reports/m6/preds/
  in-dev.jsonl        = 输入行（emit_batchlines 产物）
  out-dev.jsonl       = 预测 JSONL（m6_infer 或 m6_baseline_v0 输出）
  out-chmirror.jsonl  = 挑战镜像预测（1100 行，可行域第二约束）
baseline-dev-labels.jsonl  = 标签（m6-sample 或 QA-IR 两种格式均兼容）
```
调用：
```
.venv\Scripts\python.exe -X utf8 scripts\m6_acceptance.py --mode select-op `
  --dev-preds reports\m6\preds --dev-labels reports\m6\preds\baseline-dev-labels.jsonl `
  --dev-manifest 86ef748d12f37ca1d41e30207d6dad24f950ee92d606967c2cfd5ebca03611ef
```
（manifest sha 以 data/m6/manifest.json 当前值回填；终态数据的 sha 在 H6 冻结后从 manifest.json 计算）

## 3. 门读数怎么看（qa-report-<tag>.md）

- **G1 recall**（逐任务，>95% 严格）：TP/(TP+FN)，弃权正例计 FN（宁严）；
- **G2 FPR**（逐任务，<0.5% 严格）：良性负例；**G3 chFPR**（<0.1%）：任务级分母=challenge 六任务全负行 1155，样本级双报（v1.3.1 勘误口径）；
- **G4 OOD**（≥95% 硬门 + 98% 目标 + 攻击侧弃权率双列）；
- **G5 红队**（不设硬门；总检出<90% 或任一族<75% → REDTEAM-WEAK）；
- 参照读数（冻结套件 1770 行）：地板 pooled>95%，gen<90%/jb<90%/dilution<85% 触发 v2 建议，90-95% 带 pass-with-flag；
- fp_budget 列 = 该任务在该门下的最大可容忍 FP 数（已含在表格中）。

## 4. 判读纪律（QA-1 §4/§7 摘要）

- 运行点只从 dev 选一次；heldout 单次报告；无解释重跑 → THRESHOLD-FISHING 旗帜；
- `--thresholds-json` 仅用于敏感性注入（source=request-override），不得用于报告口径；
- 输出 flag 与 score≥θ 取 OR（最严视角）；score 缺失/越界 → fail-closed（attach_preds 抛错）；
- near-miss 如实标红，不因"差一点"放行；终裁归 Lead。

## 5. 已知坑（本窗口实战记录）

| 坑 | 规避 |
|---|---|
| PS 管道吞 python 中间日志 | 关键进度用 `-Last N` 只看尾部；exit code 硬检查（`if ($LASTEXITCODE -ne 0) exit 1`） |
| PS 5.1 ConvertTo-Json 转义不兼容 | JSONL 一律用 python 生成/解析 |
| stderr 进度条触发 NativeCommandError → exit 1 假阳性 | 判断成败看产物文件+行数，不单看 exit code |
| 全序列 logits OOM（4096×150k 词表 ~20GB） | forward 用 `logits_to_keep=N`（transformers 5.x 参数名） |
| GPU 单卡撞车（02:17 事故） | 启动前板 §9 登记意图窗口 + nvidia-smi 双确认 |
| 数据整改波中跑读数 | 只在 manifest assert=PASS + leak-check PASS 后跑正式读数 |

## 6. 产物地图

```
reports/m6/
  qa-1-acceptance-spec.md            验收规格（v1.3.1 FROZEN）
  qa-baseline-v0-frozen.md           基线冻结套件读数（对照线）
  qa-baseline-v0-full.md             基线全量读数（终态数据，v0 完成后生成）
  qa-baseline-v0-miss-ids.json       基线红队漏检清单（task-10 归因）
  qa-report-TEMPLATE.md              验收终稿骨架（⑦用）
  operating-point-v<k>.json          冻结运行点（m6-thresholds schema）
  audit/leak-check-*.json            泄漏检查证书（h6-final = PASS）
  preds/                             全部预测 JSONL + labels 快照 + scores.csv
  plots/baseline-v0-*/               分布图+AUC 热图
  mapped/frozen-*.jsonl              冻结套件映射行
  redteam/                           红队集 170 条 + README
scripts/m6_*.py                      harness 全家（见 QA-1 §8 组件表）
```
