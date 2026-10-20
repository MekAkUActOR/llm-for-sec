# M6 task-7 工程交付 · Smoke 证据（deveng-m6）

> 时间：2026-10-21 ~01:40 ｜ run_id: m6-smoke ｜ ADR-1 FREEZE + adr-1b + SYS-1 v0.3.1 契约实现

## 交付物

| 组件 | 文件 | 说明 |
|------|------|------|
| 渲染器 | `scripts/m6_render.py` | 五形态输入规范化、r5 chat_template 字节一致渲染、dsh-protocol/0.1 信封、4096 窗口 head+tail(512/3584) 截断、token→char offset 回映、span↔BIO 双向（11 类终版词表+防呆别名） |
| 特征抽取 | `scripts/m6_feat_probe.py` | `forward_extract`：**单次前向**同时产出 pooled {4,12,20,24,28}×{last,mean}=10240 维 + L12/L28 per-token 2048 维；全量抽取器模式（--input --cache-dir --with-token-feats） |
| 训练管线 | `scripts/m6_train.py` | config 驱动（m6-train-config schema）；三阶段：A 缓存（fp16 pooled + PII 行 tokfeat+BIO）/ B 头训练（trunk+5 二值+T6 三值+T4doc+T4 BIO；masked BCE pos_weight∈[1,20] + CE3 + 2.0×BIO CE(B/I 15×)；bs256/AdamW 1e-3 cosine→0.1×/warmup5%/wd0.01/≤3ep/早停1）/ C 校准（零 FP τ_flag+ADR margin、τ_strong、Mahalanobis 双中心收缩协方差 λ0.1、τ_ood=dev-benign q99.5） |
| 推理运行时 | `scripts/m6_infer.py` | m6-inference v0.3.1 契约（tasks/decision/ood.score 原始距离/T4 spans 一等字段/abstain=(pass∧ood∧弱带)/suppressed 审计标记）；阈值三级优先（request>runpoint>config-default）；τ_ood fail-closed 双读；单次前向；确定性（无计时字段进输出行） |
| 配置生成 | `scripts/m6_build_train_config.py` | 产出 `configs/m6-smoke.yaml` / `configs/m6-v1.yaml`（v1 指向 data/m6/manifest.json，含 T3 前缀消融开关） |
| smoke 数据 | `scripts/m6_smoke_data.py` | m6-sample 格式 171 train/63 dev 行：六任务±、T4 spans（终版词表）、T6 三值、多轮+reveal_turn 前缀行、挑战镜像行 |
| 单测 | `tests/test_m6_pipeline.py` | **25/25 通过**（渲染/截断/BIO 往返/标签派生/头形状/Mahalanobis/合成端到端） |

## Smoke 运行记录

### 训练（全链路，GPU 9s）
```
.venv\Scripts\python.exe -X utf8 scripts\m6_train.py --config configs\m6-smoke.yaml
```
- Stage A：165 train/61 dev（前缀行排除 6 行）→ pooled (165,10240) fp16 + 69 PII 行 tokfeat (69,42,2048)+BIO，trunc=0，4s
- Stage B：macroR@zeroFP=1.0000 @ep1（早停触发），损失无 NaN
- Stage C：六任务 τ 定标，dev 全负例（含 6 条挑战镜像）**FP=0/任务**
- 产物 10 件：probe-heads.pt / head_structure.json / ood_centers.json / calib.json（τ_ood 键）/ metrics.json / train_log.jsonl / config.json / feat_cache×4

### 推理（契约输出+确定性）
```
.venv\Scripts\python.exe -X utf8 scripts\m6_infer.py --head checkpoints\m6-smoke3 --input <in> --output <out> --determinism-check
```
- 3 行 turns/text 混合输入 → v0.3.1 输出（双带决策/OOD 抑制/suppressed 审计/spans/T6 三值 label）
- 确定性 PASS：sha256 逐字节一致（×2 运行）
- 时延：单前向 ~40ms/row @短文本（warm），含首 batch warmup ~170ms
- PII 端到端：5 行（4 PII/1 benign）→ flag/spans/类型/原文坐标回映全链路工作；benign 正确 clean（span 边界精度受限于 smoke 数据量，真数据后验证）
- 回归集（10 条，qa 崩溃报告的场景）：真头+stub 双模式 PASS + 确定性 PASS

### 回归 hash（qa 锁定用，stub seed=1234）
- 输入：`reports/m6/regression/m6_regression_inputs.jsonl`（10 条固定）
- stub v2 输出：`reports/m6/regression/stub_regression_out_v2.jsonl` sha256=`e9d148fd675e4a2ef32d1e46d1d360af26dd41bf8f7c3a6093953ebb62be3907`
- 真头（m6-smoke3）输出：`outputs/m6/regression_realhead.jsonl` sha256=`e91094a3735d6dd6f50011dbfb2232102cb4eaa8e71673ea52d17d354e7dcaf7`
- 注：旧 hash（56550639…/ffcb20b3…）基于 v0 字段名，作废

## 修复记录（smoke 期间抓出的真实 bug）
1. `_pool` last 分支 float 索引崩溃（单测抓出）
2. 输出行内嵌计时破坏确定性 → 移出，--with-latency 显式开关
3. PS5.1 BOM jsonl 读取崩溃 → utf-8-sig 全线
4. 温度校准 T→0 分辨率塌缩 → adr-1b §6.1 撤销（arch 裁决）
5. calibrate() CPU 张量喂 CUDA 模型
6. Stage B 标签键(T4) vs 头键(T4doc) 映射错位
7. BIO 预测含 batch pad 长度 → offsets 越界（qa 回归集崩溃的根因）
8. 单行推理 logits 索引维度错
9. **两次前向违规** → forward_extract 合并为单次（mission 红线）
10. Stage A token 特征切片用 batch pad 长度而非行真实长度
11. abstain 语义偏差（any_suppressed → ADR §8 的 pass∧ood∧弱带）
12. τ_ood 静默 fallback → fail-closed 双读（sysdesign D-7）

## 待真数据（task-8 v1）
- data/m6/manifest.json 就位后：`--config configs/m6-v1.yaml` 直接跑（H7-H9 窗口已预锁）
- T3 前缀消融：`data.prefix_rows: include` 对比读数随 v1 报告出
- LoRA v2 触发路径按 ADR §16 读数决定
