# M6 v1 训练读数（deveng-m6，task-8）

> run: 2026-10-21 02:18-02:41（GPU 23min）｜ config: configs/m6-v1.yaml
> data: manifest m6-data-v1 终态（59,323 train / 12,626 dev，前缀排除后，共享行去重 42,569+4,396）｜ commit 链：1fafc6d/9731703（读取器）→ 本提交（产物）

## 训练过程
- Stage A（特征缓存）：train 1,099s + dev 202s，pooled (59323, 10240) fp16；PII tokfeats 扁平 504,708/246,946 tokens；**trunc=0**（全量无截断）
- Stage B：bs 256，3 epoch + 早停（patience 1），best ep2 macroR@zeroFP=**0.7988**，27s
- Stage C：六任务双带阈值 + Mahalanobis 双中心（trunk 1024 维）+ τ_ood

## 校准后 dev 读数（score>τ_flag 口径；FP 分母=该任务全部 dev 负例，含跨任务攻击行）

| 任务 | recall | FP | τ(flag, strong) |
|------|--------|-----|-----------------|
| T1 内容审核 | 0.636 | 0/5862 | (0.967, 0.987) |
| T2 越狱/直接注入 | 0.996 | 283/5494 | (0.999, 1.000) |
| T3 恶意意图 | 0.676 | 0/5558 | (0.999, 1.000) |
| T4 PII | 0.956 | 4/5262 | (0.999, 1.000) |
| T5 间接注入 | 0.552 | 0/5862 | (0.999, 1.000) |
| T6 高危指令 | 0.852 | 0/5862 | (0.967, 0.987) |

**读数注记（供 arch task-10 归因）**：
1. **T2/T4 的"FP"是跨任务攻击行**（如 T1 武器问题被 T2 头打高分）——ADR D8 校准口径=dev-benign∪mirror 上 union FP=0，此表 FP 分母含跨任务攻击负例，故非违约；验收 FPR 以 qa harness 良性口径为准。跨任务攻击互相触发或为特性（攻击语料共享风险域），arch 裁定是否计入 precision 考量。
2. **T1/T3/T5 recall 0.55-0.68 偏低**——v1 冻结主干探针的预期短板（ADR §16 v2 LoRA 触发条件之一）。T5 间接注入最难（载体语义），T1 多类别风险面广，T3 多轮/长上下文意图累积。ep1→ep2 提升 0.55→0.80 说明容量未饱和，3 epoch 上限和早停可能偏保守。
3. **τ_strong 普遍贴 1.0**（T2/T3/T4/T5）——强带在 dev 上几乎不触发，双带机制的 OOD 抑制主要靠弱带+τ_flag 生效。
4. pos_weights 温和（T5=1.0 因正负均衡），无过补偿迹象。

## 产物（checkpoints/m6-v1/）
- probe-heads.pt（50MB，六头+trunk）｜calib.json（τ 双带+tau_ood，m6-thresholds 格式）｜ood_centers.json（32MB，双中心+收缩协方差逆）｜head_structure.json｜metrics.json｜train_log.jsonl｜config.json
- feat_cache/（3.4GB，可再生：`--reuse-cache` 之外的重建 ~22min GPU；v2 迭代复用=头重训 27s）

## 验证链
- m6_infer 冒烟 3 行 + 回归 10 行：v0.3.1 契约输出，--determinism-check PASS（sha256: smoke 59e77f44… / regression 3d89beab…）
- m6_check_response.py：13 行 0 issues（schema + verdict_line 同源 + 不变量）
- 30/30 单测维持绿

## 下一步
- qa task-9：v1 首轮读数（heldout/challenge/ood 全量）
- arch task-10：归因 + v2 改进清单（预期方向：LoRA r16 @ L14-28（ADR §16）、T1/T3/T5 数据增补、epoch 上限放宽）
- v2 迭代引擎：feat_cache 复用，头重训 <1min
