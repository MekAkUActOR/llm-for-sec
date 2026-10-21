# M6 接口契约注册表（SCHEMAS.md）

> 接口先行：三端（dataeng 数据 / deveng 训练与推理 / qa 评测）全部对着本目录的 JSON Schema 干活。
> **schema 变更必须登记版本号**（本文件 + 各文件 `$defs` 内版本注释），未登记的变更视为无效。
> 架构基线：ADR-1（docs/arch/m6-adr-1.md，arch-m6）；系统设计：SYS-1（docs/m6/m6-system-spec.md，sysdesign-m6）。

## 注册表

| 文件 | 契约 | 主要消费者 | 版本 | 状态 |
|---|---|---|---|---|
| `m6-common.schema.json` | 共享定义：任务枚举/输入五形态/标签词表/PII 词表+risk 映射/span 坐标/双带阈值 | 全部 | 0.3.0 | **冻结候选**（ADR-1 FREEZE + adr-1b 全量对齐；PII 词表 = dataeng 定稿 11 类） |
| `m6-sample.schema.json` | ①数据集行 schema（六任务统一样本：五形态输入 + 稀疏逐任务 gold pos/neg + label_detail + t6_class 单一真源） | dataeng（task-3/4/5）、qa | 0.3.0 | 同上 |
| `m6-manifest.schema.json` | 数据清单（data/m6/manifest.json）：文件指纹/覆盖/规模门/冻结套件登记/不相交断言（含 D12 载体排除） | dataeng（task-6）、deveng、qa | 0.3.0 | 同上 |
| `m6-train-config.schema.json` | ②训练配置（configs/m6-*.yaml）：基座/渲染/数据引用/探针头结构（层位 {4,12,20,24,28}×双池化、T4 双头、D12 排除）/D10 配方/特征缓存/运行点引用 | deveng（task-7/8/11） | 0.3.0 | 同上 |
| `m6-inference.schema.json` | ③推理 API 输入输出：单次前向返回六任务 {flag,score,label,spans,suppressed} + decision + abstain + ood（原始距离）+ 生效阈值（含 τ_ood） | deveng（task-7）、qa（task-9/12） | 0.3.0 | 同上 |
| `m6-thresholds.schema.json` | 运行点/校准件（ADR 称 calib.json）：双带阈值 + τ_ood + 温度元数据（撤销，不参与决策）+ 联合 OR 门定标记录；**qa 拥有，dev-only 标定** | qa、deveng | 0.3.0 | 同上 |
| `m6-eval-report.schema.json` | ④评测结果（reports/m6/eval-*.json）：逐任务 recall/FPR、挑战 FPR（U2 CI95）、OOD 放过率（U1 双列弃权披露）、透明度骑手（逐套件 CI + pass-with-flag 带）、门禁判定 + 逐条 per_item | qa（task-9/12）、arch（task-10） | 0.3.0 | 同上 |

## 版本规则

- 载荷自带 `schema_version`（semver，可带 `-draftN` 后缀）；schema 文件不设 `$id`，跨文件引用用相对 `$ref`（同目录）。
- **加字段/加枚举值 ⇒ minor**；**改语义/删字段/收紧约束 ⇒ major**；纯澄清 ⇒ patch。draft 后缀 = 尚未与 ADR/SYS-1 终稿对齐。
- 每次变更：①改 schema 文件 ②在本表登记一行（版本/日期/变更/动机/影响面）③通知三端。实现偏离规格时在 SYS-1 附录"偏差登记表"登记，不静默改 schema。

## 加载与校验（Python；`jsonschema==4.26.0` + `referencing` 已装入 .venv）

**载荷入口点**：`m6-sample` / `m6-manifest` / `m6-train-config` / `m6-thresholds` / `m6-eval-report` 五件在**文件根**直接校验载荷；`m6-inference.schema.json` 含三类载荷，入口分别为 `#/$defs/Request`（单请求）、`#/$defs/BatchLine`（qa 批量 JSONL 行）、`#/$defs/Response`（响应）。

```python
import json, pathlib
from referencing import Registry, Resource
from jsonschema import Draft202012Validator

SD = pathlib.Path("docs/m6/schemas")
reg = Registry().with_resources(
    [(p.name, Resource.from_contents(json.loads(p.read_text(encoding="utf-8"))))
     for p in SD.glob("*.schema.json")])
def validator(name, entry=None):
    schema = json.loads((SD / name).read_text(encoding="utf-8"))
    if entry:  # 如 entry="$defs/Response"
        schema = {"$ref": f"{name}#/{entry}"}
    return Draft202012Validator(schema, registry=reg)
# 用法：validator("m6-sample.schema.json").validate(row)
#       validator("m6-inference.schema.json", "$defs/Response").validate(resp)
```

校验入口脚本（deveng 交付）：`scripts/m6_validate.py --schema-dir docs/m6/schemas --data data/m6/...`。
契约冒烟（10 用例，含弃权不变量负例）已由 sysdesign 验证通过（2026-10-21 01:30）。

## 不可破坏的不变量（跨文件一致）

1. **单次前向**：`tasks` 六键全在；`score` 永远输出（阈值前原始分，σ(logit) 无温度）；`flag` 永远由双带阈值 + OOD 抑制规则派生。
2. **弃权语义**：`abstain=true` ⇒ 六任务 `flag` 全 false、`decision=pass`；验收口径 abstain 记 PASS；正样本 abstain 计 FN、负样本计 TN；**score>τ_strong 永不被 OOD 抑制**；decision=flag 时 abstain 必为 false（D-5）。
3. **gold 口径**：主判统一 `pos|neg`（六任务同口径）；细粒度只在 `label_detail`；`labels` 稀疏（缺键不计该任务分母）；多任务联合行必须含 `task` 键。
4. **坐标口径**：PII span 一律 Unicode 码点、end 排他、基准=原始输入字段（text/messages[i].content/carrier.body），**绝不使用渲染后协议信封坐标**（渲染器提供 token→原文回映）。
5. **物理纪律**：`data/m6/` 的 train/dev 与 heldout/challenge/ood 由 manifest 不相交断言隔离；`data/heldout/` 冻结套件只读（映射为 protocol 透传行），永不进训练/调参/阈值标定；阈值标定只用 dev。

## 变更日志

- 2026-10-21 01:15 · 0.2.0-draft0 · sysdesign-m6 · 初稿七件套落地（吸收 qa 验收侧要求：raw score 必出/阈值可覆盖/abstain 记 PASS/T4 span 级；吸收 dataeng 数据侧要求：pos|neg 主判 + label_detail 细粒度/五切分/血统字段）。
- 2026-10-21 01:20 · 0.2.0-draft1 · sysdesign-m6 · 按 arch-m6 预对齐裁决重写：判别式多头探针（非生成式）——score_source=logit、双带阈值 τ_flag/τ_strong、OOD=Mahalanobis aux、弃权=中带抑制（强信号永不弃权）、T6 三值 conditional 不 flag、渲染=r5 chat_template 全序列化 + 4096 窗口 head+tail(512/3584) 截断 + token→原文 char-offset 回映；删除生成式残留（raw_text/max_new_tokens）。schema 文件迁移 docs/design/schemas/ → docs/m6/schemas/（任务板 task-2 口径）。
- 2026-10-21 03:15 · 0.3.0 · sysdesign-m6 · **ADR-1 FREEZE（02:05）+ adr-1b（02:15/02:50）全量对齐**：①任务键终裁 T1..T6（ADR 附录 A 语义键为草案记法；T1..T6 与数据集 labels/阈值/评测 per_task 同一命名空间）；②Response 字段名对齐 ADR：`tasks`（原 results）/`decision`（原 action，值小写 pass|flag）/`latency_ms` 顶层；③`ood.score` = 原始 Mahalanobis 距离（≥0 未归一化），thresholds_applied 增 `tau_ood`；④T4 `spans` 升为一等字段（doc 头 ∨ span 并集）；⑤adr-1b §6.1 温度撤销——score=σ(logit) 原始尺度，temperatures 降级为元数据；⑥§6.2 T6 契约——label_detail.t6_class ∈ {high-risk,conditional,safe}，单一真源三向 if/then 约束 + 缺省回退；⑦§6.3 T4 双头（PiiDualHead：doc 二值 + token BIO，BIO 通道=2×|T|+1 从词表 derive）；⑧PII 词表 = dataeng 定稿 11 类 + type→risk 确定性映射 + span.sub（gov_id: resident_id|passport）；⑨层位 {4,12,20,24,28}×{last,mean}、D10 配方、stage_a 特征缓存、D12 载体排除入 train-config；⑩评测 schema 吸收 U1（双列弃权披露）/U2（逐任务挑战门+精确二项 CI95）/透明度骑手（逐套件 recall CI + 90-95% 带 pass-with-flag）。契约自检 14/14 过（scripts/m6_check_schemas.py）。
- 2026-10-21 03:50 · 0.3.1 · sysdesign-m6 · 迭代期一致性维护（arch 咬合审查 F1/F2 + 对 m6_infer.py v2 预检，偏差 D-5..D-10 见 SYS-1 §12）：①`Response.latency_ms` 转 **optional**（deveng 字节确定性设计正当——批量评测逐字节可复现优先，交互式/`--with-latency` 时写入）；②`abstain` 语义描述收紧（decision=flag 时 abstain 必为 false，D-5 依据）；③T4 spans=strong 带澄清（spans 非空 ⇒ flag 且不可被 OOD 抑制，D-10）；④F1 修正：TaskResult.score 描述删"温度校准后"残留，明确"无温度缩放，score = σ(logit)"（adr-1b §6.1）；⑤SYS-1 §4.2 增信封模板权威源纪律（训练侧 secfm/carriers 为权威源，heldout 逆向=格式交叉验证，F2）。消费方注意：`ood.tau_ood`（非 `threshold`）为运行点/校准件唯一键名（D-7）。
- 2026-10-21 03:38 · 0.3.2 · sysdesign-m6 · **staging 预检驱动的加性修订**（data/m6/_staging 中间格式 → 终稿投影对齐）：①T3Detail 增 `position`（载荷埋藏位）/`reveal_turn`（收割轮号），均可空；②T5Detail：`mechanism`/`carrier_site` 允许 null（neg 行），增 `envelope`（信封变体标记）；dataeng 中间格式的 `position` 终稿投影改名 `carrier_site`；③**T4Detail.spans 统一走 $defs/Span**（修内联定义残留——旧内联缺 `sub`/`risk`，staging 的 gov_id sub 会挂校验）。全部加性/放宽容，旧载荷兼容。
- 2026-10-21 03:45 · 0.3.3 · sysdesign-m6 · **staging 预检第二轮**（工具 scripts/m6_check_rows.py，19 文件 × 400 行抽样）：①新增 `RowTask`（TaskId ∪ {"pool"}）用于 sample.task 与 manifest 条目——共享负例池行 task="pool" + labels 六键展开（dataeng 中间格式 SHARED）；TaskId 本体保持 T1..T6 纯度（推理/阈值/评测不受染）；②T5 机制词表无损合并 legacy 分类学（+authority_disguise/metacomment/command_substitution/backdoor_comment/destructive_request/deanon_request/bulk_extract，冻结套件在用标注 12.8K 行）；③**T6Gold if/then #2/#3 补 `required:["label_detail"]`**（修 schema 自身 bug：label_detail 缺席时空洞匹配，neg 行被误判 'pos' expected——预检抓出，回归用例 ⑧d 锁定）；④自检扩至 16 用例。**遗留数据缺口（dataeng 终稿）**：challenge/challenge-mirror 的 t4_pos=true 行（抽样 35/400 + 156/400）需补 T4 span 级 gold（pos + 真 spans）；split_hint=pool 待 H6 真分配。
- 2026-10-21 04:05 · 0.3.4 · sysdesign-m6 · **arch 裁定 Option A 落地**（载体形态接口）：①新增 `EnvelopeStyle` 枚举（std_tag/simple_tag/markdown/plain，权威源 = scripts/m6/gen_indirect.py::envelope_variant）；②`Carrier.envelope_style`（缺省 std_tag，渲染器选载体块模板）；③`T5Detail.envelope` 从自由字符串收紧为同枚举（终稿载荷未存在，收紧无破坏）。SYS-1 §4.2.1 定义四变体模板语义 + 渲染器/数据侧义务 + "裸片段不进 input.carrier 路径"分布注记。
- 2026-10-21 04:15 · 0.3.5 · sysdesign-m6 · **N-3 裁定修正**：`aux_ood.feature` "trunk_pre_input"（10240 维原始拼接）→ **"trunk_output"**（1024 维）——deveng train/infer 两端实现一致且忠于 ADR §8 原文（"trunk 1024 维特征上的 Mahalanobis 距离"），schema 为偏出者让位。理由入描述：trunk 入口 LN 已做标准化（协方差条件数更好）、1024 维协方差估计更稳、与六头同空间（距离度量语义自洽）。SYS-1 §6 同步。
- 2026-10-21 04:25 · 0.3.6 · sysdesign-m6 · **m6-v1.yaml 配置对齐**（consumer 键名采纳，schema 向实现现实收敛）：①base+frozen；②probe.pooling 转可选（缺省双池化）；③probe.token_layers（const [12,28]，自 stage_a 上移）；④PiiDualHead 的 input/flag_rule 升 T4 级（值对齐 deveng 写法 "doc_head_or_spans_nonempty"）、doc+classes；⑤loss 键名对齐：w_tok→**bio_weight**、bio_bi_weight→**bio_pos_weight**；⑥aux_ood：shrinkage_lambda→**lambda**；⑦data+prefix_rows（include|exclude，多轮前缀行策略）；⑧train+grad_clip/early_stop_patience/bio_max_tokens/extract_batch_rows。**deveng 侧待办一词**：configs/m6-v1.yaml 的 `aux_ood.feature: trunk` → `trunk_output`（N-3 契约值）。自检新增第 4 层：configs/m6-*.yaml 存在时自动过 train-config 契约。
- 2026-10-21 04:30 · 0.3.7 · sysdesign-m6 · **smoke 配置豁免**（m6-smoke.yaml 驱动）：①run_id 式放宽 `^m6-[a-z0-9][a-z0-9.-]*$`（容纳 m6-smoke*）；②data.manifest 转可选 + train_patterns/dev_patterns glob 字段——smoke/调试配置天然无 manifest（正式训练仍必须提供，由任务板 task-6 门禁强制，schema 描述显式注明）。另：不变量区 1/2 的 results/action 旧词同步为 tasks/decision（0.3.0 更名残留）。
- 2026-10-21 04:50 · 0.3.8 · sysdesign-m6 · **manifest schema 对齐 dataeng 实际结构（吸收）+ 完整性硬要求（坚守）**：吸收——generator_seed / risk_domain_enum / pii_type_table / shape_mix / pair_integrity / notes 顶层字段；disjointness 改实测形块（train_rows/eval_rows/exact_overlap/mirror_eval_overlap/ood_t4_pos_rows/assert，近似项 near_dup 待 qa 泄漏审计回填）；scale_gates 扁平阈值形；files[].rows 作为 n 别名。坚守——manifest_id / generator / files[]{split,task,sha256,label_counts}（训练启动指纹校验、D7 pos_weight 数据源、qa calib 引用锚）；path 强制正斜杠。coverage 转可选（可从 label_counts 推导）。当前 manifest.json（commit 5b760ec）差 5 项：manifest_id、generator、files[].split/task/sha256/label_counts、path 反斜杠——dataeng v2 待补。
- 2026-10-21 05:10 · 0.3.9 · sysdesign-m6 · **meta.eval_family 契约键（arch 裁定）**：`meta.eval_family ∈ {benign, challenge, ood}` 落 sample 行级 meta（可选、存在即校验枚举）——dev-mirror 三文件 + pool/dev 行必带（dataeng emit 整改中）；归因读数用 eval_family，不解析 source.family 字符串（后者保留血统溯源）。meta 描述同步：自由附加原则不变，eval_family 为显式契约例外。
- 2026-10-21 05:25 · 0.3.10 · sysdesign-m6 · **manifest v2 形态吸收（第二轮）**：①generator +seed/staging_generators；②frozen_suites 改对象形 {reference, leak_audit}（dataeng 现行）；③dev_mirror_note 顶层键（dev-mirror = pool/dev 字节相同子集视图，不入 files[]、聚合去重防双计）；④disjointness +t4_entity_overlap/t4_heldout_entities_checked（T4 实体级重叠 = span 记忆化风险指标）。**坚守**：label_counts 条目严格 {pos, neg}（cond=753 之类的口径统计不得入 label_counts——须写文件真值；T5 的 753 行 label:"cond" 是契约违规待投neg，见偏差 D-12）。审计工具 m6_h6_audit.py 同步子集视图语义。
- 2026-10-21 05:45 · 0.3.11 · sysdesign-m6 · **D-12 裁定落地 + protocol 吸收**：①T1/T2/T3/T5Detail 增可选 `m4_verdict`（string）——adr-1b §6.10 通用条款的 schema 侧：非 T6 任务 conditional verdict → label neg + 此字段留痕（arch 裁定 cond→neg，四条理由入 SYS-1 D-12）；②manifest disjointness +`protocol` 对象（exact/near_dup/entity/nfkc 方法学登记，dataeng 终态新增）。审计工具 layer-3 修正 pool/dev 口径：仅镜像子集（flags.challenge/ood 行 + benign 家族行）必带 eval_family，常规任务 dev 行不要求。
- 2026-10-21 06:05 · 0.3.12 · sysdesign-m6 · **content_overlap_qa_l1 吸收**（qa L1 复检驱动的第三把锁）：manifest disjointness +`content_overlap_qa_l1`（qa L1 级内容重叠断言，必须 0）——dataeng 根因修复 = assign_splits 加 content-only 第二把并查集锁（不含 system 的全文哈希；同用户可见文本一生只进一个 split，堵 query 级记忆穿越 pack 差异）。**H6 审计对 d5f65df（冻结候选 v2）四层全 PASS**，证据 reports/m6/h6-audit-sysdesign.txt。
- 2026-10-21 02:58 · 0.3.13 · sysdesign-m6 · **logit 空间决策带（Lead 裁决 v1-1 官方读数对象；non-breaking additive）**：①ThresholdBand（m6-common，inference+thresholds 共享）+ 可选 `flag_logit`/`strong_logit`（["number","null"]）——fp32 sigmoid 在 logit>~16.6 饱和为 1.0，score 空间 τ=min(0.999,·) 上限破坏 D8 零 FP 构造（v1 实测 T2 283 FP / T4 4 FP，全为饱和 score 良性）；修复 = logit 空间校准（τ_l=neg_max_logit+δ，δ=1.0）与应用比较，score 字段仍为 σ(logit) 原始回显（adr-1b §6.1 不变）；T6 softmax 概率与其他 score 空间 runpoint 缺省字段=旧行为（向后兼容，旧 stub 输出实测仍绿）。N-1 同源原则：thresholds_applied 回显实际应用的阈值=logit τ。②m6-thresholds 收编 deveng ckpt calib 形态：runpoint_id 拓宽 ^m6-[a-z0-9][a-z0-9.-]*$（m6-v1-init）；owner qa const→string（deveng initial / qa re-freeze）；calibrated_on 必填降为 split（manifest/n 定稿必填）；+temperature_applied/score_def/顶层 curves{tau,recall,fp,n_neg}。③m6_check_response 加固：logit 带序（strong_logit≥flag_logit）+ 回显一致性（|σ(τ_l)−flag|≤1e-3，饱和容差）断言。**验证**：deveng v1-1 实测输出 10/10 零 issues（原 50）+ ckpt calib.json 零违规 + 旧输出向后兼容。
- 2026-10-21 05:10 · 0.3.14 · sysdesign-m6 · **projection_gate 断言键吸收（dataeng f247fcc 落形，arch 背书 + scope 字段）**：manifest 顶层（与 disjointness 平级）+`projection_gate` {checked, t4_hits, t5_hits, revoked_to_pos, revoked_exit, assert, scope.classes_gated}——投影门 = 构造时验证（adr-1b §6.14"标签真值在构造时验证，不在读数时发现"）：T4 span 提取器 + T5 注入模式对 blanket T1-T5 neg 投影行零命中核查，RFC 5737/example.* 文档保留段豁免。revoked_to_pos 恒 0（保留键：转 pos+spans 须 arch 手工裁定）；scope.classes_gated 按类分桶使收紧裁定可审计（high-risk 误入在 layer-4 scope 漂移显形）。dryrun 基线：checked 3,039 / t4_hits 0 / t5_hits 0 / assert PASS（与 sysdesign 存量 2,046 行六模式粗扫零命中一致）。正式波落地后 layer-4 自动复验。
- 2026-10-21 04:35 · 0.3.15 · sysdesign-m6 · **train-config 双代兼容（v2 LoRA 波配置吸收）**：deveng 新落 configs/m6-v2.yaml + m6-lora-smoke.yaml（v2 代形态：`base.model_name_or_path` 承载主干引用、省略 m6_config_version/render/probe.trunk——装载器实读代码核实，渲染常量由 m6_render 模块导出）。schema 侧：①m6_config_version/render/probe.trunk 转**可选**（v1 代携带、v2 代省略=代码默认）；②required 缩至 [run_id, base, data, probe, train, output_dir]，probe.required 缩至 [tapped_layers, heads, loss]；③train +`lora` 块 {enabled, r, alpha, dropout, lr, target_modules, layer_from, layer_to, lora_bio_extra_rows} + `lora_center_max_rows`（代码默认 20000）+ `baseline_readings`（arch task-10 回归护栏：任一任务回退 >1pp 取消该 epoch best 资格，v1-2 基线锚点）；④max_epochs 上限 3→6（D10 v1 缓存训头 ≤3 不变；v2 LoRA 联合训练 arch 批准 5）。**验证**：四个配置（v1/smoke/v2/lora-smoke）全过契约检。
- 2026-10-21 04:45 · 0.3.16 · sysdesign-m6 · **projection_gate 语义精化（patch：描述层）**：①mask-vs-neg 裁定落地 = **uniform neg**（投影行计入 T1-T5+T4 neg 监督，非 mask）——m6-v2.yaml 陈旧 pending 注释清理；②arch 追加收紧：投影范围 = T6 **conditional+safe 子类硬边界**（high-risk 不投，极性未定不猜），scope.classes_gated 描述升级为硬边界语义；③**人形邮箱域无关命中**（dataeng 一致性深查：门的保留域豁免与 T4 标注实践冲突——T4 pos 含 106 个人形 example/保留域邮箱 span，analyst@203.0.113.7 类渗出目标人形邮箱是错金信号非豁免对象）；④基线锚点更新：**checked 3,039 / t4_hits 81 / t5_hits 0 / revoked_exit 81**（双源零命中口径被取代——sysdesign 粗扫正则的字母 TLD 假设漏过数字域人形邮箱，与门的保留域豁免是两个不同盲区的巧合一致；构造锚定（标注实践）才是真校验，§6.14 再验证）。
- 2026-10-21 05:00 · 0.3.17 · sysdesign-m6 · **projection_gate 两级语境规则 + context_released 键吸收（arch 语境裁定，dataeng a6a8fc9）**：81 行 analyst@IP 经 T4 语境构念裁定 = **role 形 local（组织角色非自然人标识）+ 合法语境 → 豁免放行**。门两级规则：①role/service 形 local 豁免清单入正则（不计命中）；②人形/实体命中在 conditional/safe 池按语境自动释放（新键 `context_released`，日志留痕）。基线锚点再更新：**checked 3,039 / t4_hits 0 / t5_hits 0 / revoked_exit 0 / context_released 0 / 投影 3,039 / PASS**。基线演进链归档：双源零（盲区巧合）→ 81 扣留（标注实践锚定的一致性深查）→ 0/3,039（语境构念裁定：role 形非 PII）——每步都是真实语义精化，append-only 追踪正是为此。
- 2026-10-22 00:25 · 0.3.18 · sysdesign-m6 · **ADR-2 D-16 threshold_space 落地（恢复令后首件）**：①m6-thresholds +`threshold_space`（enum logit|score）——logit 域统一契约字段：全链 logit（校准/决策/敏感性曲线/OOD 距离），score 降级显示层；**if/then 强制**：声明 logit ⟹ T1-T5 必带 flag_logit/strong_logit（T6 softmax 豁免），消费者存在即必须 logit 比较——硬失败优于静默换轨（D-7 家族纪律，同族三案：§6.1 温度撤销→v1-1 τ 帽→fp32 饱和 391 显示层事件）。②ood.suppression const 拓宽为 enum {two-band, strong-too}（deveng 7082d30：suppression_mode 实际开关在 centers_ref 文件，runpoint 侧自述；ADR-1 §8 默认不变）。③SYS-1 §12 编号空间注记（本表 D-n vs ADR-2 D-n 独立空间，引用写全限定）。**验证**：咬合测试三态（logit+键 PASS / logit 剥键 10 违规 FAIL / score 无键 PASS）+ 三 ckpt calib 托管校验零违规（v1-2 calib 已带 logit 键，v2 声明即可过）+ 契约检全绿。
- 2026-10-22 01:05 · 0.3.19 · sysdesign-m6 · **v2 数据波形态吸收（970764a，ADR-2 D-18）**：首跑 28 fails 全数定位为 schema 滞后非数据违规——①m6-common **Kind 枚举 +document**（文档形：检索增强长文档/合法 PII 文档，input 以 text 承载，1,800 行）；②**Role 枚举 +tool**（toolout 轨迹工具结果轮：assistant JSON 调用 → tool 结果循环，2,769 行）；③m6-manifest **projection_gate +note**（门规则自述键）。吸收后全量四层重跑**全 PASS**（证据 h6-audit-v2wave.txt）：invalid_total=0 / 规模门 6/6（T2 pos 2,970、T6 pos 4,050） / eval_family 覆盖含 challenge-mirror 1,250（lawful-pii 150） / manifest 0 违规 + 23 条目对数吻合。**交叉互证**：结构计数 3,102 投影 ids = projection_gate.checked 精确一致；scope {conditional:1603, safe:1499} 硬边界零违。SYS-1 **D-14 登记**（v2 波形态吸收 + ADR-2 D-17 契约栈落地验证）。
- 2026-10-22 00:2x · 0.3.20 · sysdesign-m6 · **manifest 双数键吸收（dataeng 89f5a55，§6.11 孪生口径契约化）**：files[] 条目 +`file_rows`/`unique_ids`（文件内口径——任务视图与 pool 均 id-unique，孪生是跨文件现象、union 对账在审计 layer-2；两键使文件内部重复与孪生承载形态可从 manifest 直接读出）。**增量确认**：全量四层重跑全 PASS（manifest 新 sha 与盘上一致，行级数据未动，projection_gate 3,102 不变）；**三方独立对账链入 D-14 备注**——dataeng 门计数 3,102 → arch 终扫 3,102 → sysdesign union 结构计数 3,102（三源不同方法精确一致）。
- 2026-10-22 03:10 · 0.3.21 · sysdesign-m6 · **ThresholdBand 逐带 threshold_space 吸收（deveng v1-3 calib as-built，qa 落后知会驱动）**：①m6-common ThresholdBand +`threshold_space`（enum logit|score，可选）——**逐带空间声明**；语义按头型分：T1-T5（sigmoid）"logit" = log-odds 域 σ⁻¹(τ)，T6（softmax）"logit" = **log-probability 域 ln(P)**（D-16 延伸——softmax 饱和的等价修法，v1-3 实证：T6 flag_logit=-1.13e-6 = ln(0.99999887) 精确吻合）；②**带级 if/then**：声明 logit ⟹ 本带必带 *_logit 键（咬合测试：剥键 12 违规）；③root 级 threshold_space（v0.3.18）保留为聚合声明，带级为 as-built 权威。**验证**：v1-3 calib **原样**零违规（qa 转换层无需再剥离）+ v1-2/v1-1 向后兼容零违规 + 响应 20 行（v13 + 旧 stub）零 issue（m6_check_response 已是 T6=exp / T1-T5=sigmoid 双形——缺口期 deveng 已修）。
- 2026-10-22 03:50 · 0.3.22 · sysdesign-m6 · **TaskResult + per-item `logit` 键（deveng 03:42 契约请求，qa/arch 联合——A3 红队双机制验证 + B 族梯度归因）**：optional number——T1-T5 = sigmoid 头 logit（score=σ(logit) 前原值，未舍入分辨率：饱和区 score 无分辨率，logit 保留梯度）；T6 = ln(P) log-P（与 v0.3.21 threshold_space 语义同域）；input_error 弃权行可缺省；score 仍必输出（向后兼容）。**checker 同源断言配套**：m6_check_response 加 tasks.{T}.score ↔ logit 一致性（T1-T5 σ / T6 exp，1e-3 容差覆盖 fp32 双端饱和与显示舍入）。**验证**：咬合测试（T2 错值 1 violation 精确命中 / 正值 0 / T5 底饱和 score=0→logit=-18 过 / T6 log-P 过）+ 现役 20 行输出零 issue + 契约检全绿。载荷 schema_version 建议 deveng 侧 0.3.2→0.3.3（optional 键 = minor）。
