# H6 复验协议（泄漏整改后重新放行判定）· arch-m6

- 触发：dataeng "整改波稳定" 信号（P0 泄漏 + P1 T4 dev/T3 dev + P2 eval_family + manifest v2 全部落地）
- 性质：**全量复验，非增量**——跨 split 全局 sig 重排 + ~961 行删改 + T4 heldout 实体重生成会改变全部计数
- 冻结门：**qa 归一化哈希协议复跑绿 + 本协议全绿 + sysdesign --limit 0 全量滚绿**（三方合并；manifest 断言不作为门）
- 记录：结论 append 至 adr-1b §6.9 后续

## P0 泄漏复验（决定性）

1. **train↔heldout 全文重合 = 0**：t1..t6 全部任务，train/dev vs heldout/challenge/ood + heldout-shared，归一化口径（空白折叠 + 小写；qa 协议以其冻结版为准）。上轮基线：t1 485 / t3 476 / 合计 961（轻归一化）。
2. **T4 实体重合 = 0**：span 表面串（按正确坐标模型提取——spans 可能带 message_index/carrier_id，勿用 input.text 直接 Substring）train vs heldout 实体集合交集为空。
3. **manifest v2**：disjointness 记录方法 + 范围 + 协议版本；files[] 带 split/task/sha256/label_counts（sysdesign 完整性缺口对齐）；label_counts 与实测对数（sysdesign 工具交叉核对）。
4. 弃行方向核验：heldout 行未被改动（heldout 侧 id 集与整改前一致，除 T4 实体重生成行）；train 侧缩减 ≤ ~1%。

## P1 管线复验

5. **T4 dev**：≥250 pos / ≥1,200 neg（兄弟任务规模）；t4 train 划拨后仍 ≥2,000 pos / ≥2,000 neg。
6. **T3 dev**：prefix 与 full 双形态在场；full pos ≥206（若补拨则 ~250）；deveng "零正例"复现配置的结论落档（实现 bug 则 deveng 修，数据无涉）。
7. **规模门全量重跑**：六任务 × train/dev/heldout pos/neg（train ≥2,000/2,000；heldout pos=300/neg≥1,000；dev 参照 ~250/1,200）。上轮 t6 pos 2,050 贴线——若重排再降需升级。

## P2 标记与结构复验

8. **eval_family 覆盖率**：dev-mirror 三文件 + pool/dev 行级 100% 带 `meta.eval_family ∈ {benign,challenge,ood}`；schema v0.3.9 全目录校验绿。
9. **pair_integrity 重验**：T5 最小对（上轮 1,589 组/0 跨切分）、f5 1,000 对、T3 对话组 530——行删改后组完整性可能受损，重跑 manifest 断言 + 抽验。
10. **不变量保持**：OOD 500 行 t4_pos=0；challenge 1,500（345 医疗 T4-pos 带 span 出分母）；mirror 1,100/500/3,500；T4 heldout 300/300 span + 11 类覆盖（重生成后新实体）；t6 三值分布合理（cond ~871 量级）；四信封变体均衡；train↔eval exact_overlap 以 qa 协议口径复测。

## 合并

11. sysdesign --limit 0（行契约 + label_counts + 规模门 + eval_family 覆盖率）+ qa 协议复跑 → 三方绿 → H6 重新放行 → v1 训练开跑（H7-H9 窗口）。
