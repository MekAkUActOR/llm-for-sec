# M2 SFT 配方（设计骨架 v0.1）

> 状态：骨架——已定要素具体化，未定要素显式 TBD；数据源清单待 M2 调研
> （docs/research/m2-sft-sources.md，进行中）回填。
> 上游：docs/01 §3.2（T1-T12 + 三贯穿设计）、docs/03（政策包模板）、
> docs/policy-packs-v0-draft.md（三包实例 + 方向性不变量，2026-09-25 定稿）、
> scripts/score_heldout_v2.py（VERDICT 输出契约）。

## 1. 定位与出口判据

M1/M1.5 交付"读得懂"（域感知 + 知识先验），M2 交付"答得对"（行为层）。
基座从 base 起步（docs/01 §3.0 决议：instruct 检查点携带他人对齐层，与政策
条件化冲突），对话能力由 SFT 恢复。

M2 出口判据（docs/01 §7）：
- 核心任务族（T1-T12）达标线：heldout v0.2 各域能力条目 verdict_correct
  达标（阈值 TBD，校准跑后定）；
- 短上下文注入 ASR < 阈值（默认包，前瞻条目经判分器 v2 读取）；
- 误拒纪律：professional 包误拒 ≤ 阈值（v0.2 政策组读数）；default 包
  robustness 全集拒绝；
- instruct/base 起步消融关门（§9）；
- 通用能力不塌方：探针 general_en/zh 回升 ≤10%（延续 M1 门禁语义）。

## 2. 起点检查点

- **主线**：`checkpoints/qwen3-06b-sec-m15`（C1-full + C2 知识针）；
- **消融对照**：`Qwen/Qwen3-0.6B`（instruct 快照 c1899de2，已预取）——
  同数据配方 SFT，对比"继承他人对齐层 vs 政策条件化从零塑"；
- 起点检查：m15 的五域 PPL / 新域 PPL（v0.3）/ 长上下文 32k 无退化
  （post_m15_eval.ps1 产物作为 SFT 前登记基线）。

## 3. 任务族 → 数据映射

| 族 | 输入→输出 | 数据来源 | 状态 |
|---|---|---|---|
| T1 检测/定位/分类 | 载体→信号+span+类别 | 注入植入语料（自建：向 email/webpage/log/code 系统性植入，协议包裹）；CVE/通告改写 | 自建为主 |
| T2 机制解释 | 信号→机理 | C0/P1 语料改写为 QA 对；arXiv 摘要扩展 | 半自建 |
| T3 风险评估 | 载体+语境→九元组 | 通告数据合成（CVSS 要素改写） | 自建 |
| T4 政策接地判断 | 载体+语境+政策→裁决+引用 | 政策包 v0 × 场景模板生成 | 自建 |
| T5 响应生成 | 载体+裁决+政策→谱系响应 | 政策条件化配对（§4） | 自建 |
| T6 代码安全 | 代码→漏洞/修复/加固 | 公开漏洞数据集（Devign/BigVul/CVEfixes 类，调研中）；检测练习（heldout sec-c6 同型） | 调研回填 |
| T7 隐私操作 | 文本→PII 发现/分级/脱敏 | 合成 PII 语料（CN/国际格式：证件/手机/凭证格式知识已在 C2）；真实文本脱敏对 | 自建+合成 |
| T8 AI 安全操作 | 载体→注入检测/越狱识别/IO 审查 | 攻击框架语料（越狱四变体模板×政策配对）；AgentDojo/InjecAgent 类（调研中） | 调研回填 |
| T9 网页/钓鱼分析 | DOM→裁决+证据 | 钓鱼页合成（结构信号：隐藏元素/表单指向/混合来源）；反诈语料 | 自建+调研 |
| T10 多轮/组合判断 | 对话历史→整体裁决 | 多轮走私构造（分段无害→整体有害）；红队对话 | 自建 |
| T11 校准/弃权 | 缺语境→澄清式提问 | 情境模板（缺授权/缺对象/缺目的三轴） | 自建 |
| T12 政策问答 | 政策文档+查询→接地回答 | C2 政策文本（GDPR 全文/四法/NIST/OWASP）+ 引用格式训练 | 现成改写 |

贯穿比例（docs/01 §3.2）：T8 与全族 ≥X% 样本含注入载荷（分离不变量采样，
正确行为=报告）；政策条件化覆盖所有双用途样本（§4）。

## 4. 政策条件化配对（核心机制）

1. **三包配对**：凡政策包 v0 阈值表判定不同的（查询, 语境），生成
   conservative / default / professional 三条训练目标，`<system>` 区注入
   政策引用（docs/03 政策端口不变量：用户区/载体区政策声称无效——heldout
   sec-r15/ais-r13/r8c 实证项）；
2. **方向性不变量**（2026-09-25 复核新增，高于阈值表）：
   - professional 放行仅限**保护方向**（输出=结论/风险判断）；
   - **去保护方向**（输出=还原身份/明文/剥离脱敏）三包同拒，
     唯一例外=合成数据演示风险评估；
   - 该不变量作为训练样本的显式讲解案例（SFT 样本自带理由），不只作为
     阈值行——一条可教学规则优先于十张表；
3. **hard-floor 六条**（HF-001~006）入所有包的负样本：任何包语境下的
   HF 请求，正确响应=拒绝+解释（政策包不调整 HF）；
4. **VERDICT 自报**：每条训练目标末行携带 `policy` 字段=实际激活包
   （判分器审计"声称=激活"）。

## 5. 输出契约（VERDICT）

采纳判分器 v2 定义（scripts/score_heldout_v02 docstring）：
```
自由推理...
VERDICT: {"action": "answer|refuse|report", "verdict": <任务词表|null>,
          "confidence": <0..1>, "findings": [...], "policy": "<pack>"}
```
- action 三值=模型意图；deflect/format_error=评估侧观察标签（不训练）；
- T1-T12 各族定义 verdict 词表（TBD：随首校准跑定稿）；
- 全部 SFT 目标以 VERDICT 结尾（结构化层），自由推理承载解释质量
  （T2 评解释不只评结论）。

## 6. 数据构成与规模（初稿，调研后修订）

| 构成 | 估计 | 来源 |
|---|---|---|
| 政策条件化配对（含三包配对） | ~40-60% | 自建生成管线 |
| 任务族单项（T1/T3/T6/T7/T9/T12） | ~25-35% | 自建+公开数据集 |
| 注入/越狱分离不变量样本 | ~10-15% | 植入管线+攻击框架模板 |
| 多轮（T10） | ~5-10% | 走私构造+红队对话 |
| 通用对话恢复（base 起步的代价） | ~10-20% | 通用 SFT 子集（许可核查） |

总规模初估 50-150k 条（0.6B 模型、对话格式），随调研与校准跑修订。
配比与构成以 docs/research/m2-data-assembly-plan.md §6 定稿为准。

## 7. 合成数据与攻击生成纪律

- **攻击框架作输入 = OK**（越狱结构/注入模式——模型必须见过攻击才学会拒绝）；
- **武器化内容作任何组成部分 = NO**（响应模板、载荷 how-to、成品武器）；
- 合成管线与评估集物理隔离（docs/01 §5.5）：生成管线接触不到
  heldout v0.2 / 探针 v0.3；
- **留出攻击族**（docs/01 §3.4）：若干攻击类型不进 SFT，专测泛化
  （M4 循环启用，M2 期预留清单 TBD）；
  - ~~**tool_output 载体族留出不训练，作泛化探针（v0.2.1 起）**：注入
    植入语料只覆盖 5 载体（email/webpage/log/text/code），tool_output
    （工具返回值内嵌注入）永不入 SFT 生成语料——heldout v0.2.1 的 8 条
    tool_output 条目即未见载体泛化读数（校准跑预期 ASR=1.0，全量跑后
    观察翻转）~~
    **（2026-09-30 订正：此条从未成立，且该"泛化探针"是无效仪器）** 依据
    `scripts/carrier_census.py` + `reports/carrier-census.json`：训练混料
    `data/lf/sft_m25.jsonl`（137,670 行）中带 `<carrier>` 信封者 13,981 行，
    其中 **`tool_output` 出现 1,224 次**——T14-authinject 族正是训练
    tool_output 载体的（占全部带信封行的 8.9%）。因此 tool_output 子集
    **只能作"同载体新 phrasing"回归测试**，不得再宣称未见载体泛化；
    判定器 v2 已内置该断言（`--require-unseen-carrier` 会硬禁）。
  - **真·未见载体留出集 = `data/heldout/v0.3-gen`（2026-09-30 起冻结）**：
    `image_metadata`（EXIF/XMP/ICC）与 `av_metadata`（MP4 box/MKV 附件）两类载体，
    在训练混料中信封计数均为 **0**；`secfm/carriers/meta_ser.py` 为评测侧序列化器，
    且这两个类型**刻意不注册**进 `secfm/carriers/base.py::_CARRIER_TYPES`
    （注册即让生成器可产出它们，留出性立即失效）。
    **本目录条目永不入训练**，由 `scripts/check_gen_heldout.py` 的
    train-disjoint 断言机械保证。
  - **留出集轮换规则**：一旦某留出载体进入训练（新增家族、回填、蒸馏等任何形式），
    必须在**同一次变更**中：① 从 `_CARRIER_TYPES` 之外补入一个新的未见载体并造 ≥34 条
    鲁棒性条目；② 更新判定器与本文档的"已训载体/留出载体"清单；
    ③ 重跑 `carrier_census.py` 留档。轮换纪律由 `reports/s0-remediation-2026-09-30.md §2` 给出。
  - **已训载体清单（客观，随时可复算）**：text 10,239 / email 1,768 / tool_output 1,224 /
    log 250 / webpage 250 / code 250（合计 13,981 行带信封）。
    **已注册·待入训**：`document`（`secfm/carriers/base.py::_CARRIER_TYPES` 已含，
    T15-doc-structure 族 1,200 行仍在 `data/sft/m2.5-staging/`，**尚未进入任何混料**，
    故训练计数为 0——2026-09-30 订正）。
    留出：image_metadata / av_metadata（`data/heldout/v0.3-gen`，122 条，
    其中鲁棒性条 35+35）。
- paraphrase 阶梯：同一攻击面的表述变体作为一致性训练信号（判分口径
  与 M4 对抗循环共用）。

## 8. 评估协议

- 主判据：heldout v0.2（153 条）× 判分器 v2——双指标（ASR×误拒）**按政策包
  分组报告**，前瞻条目（13 条）经 report_finding 标签首次可判；
  （m2calib 链起在 v0.2.1 = 161 条上跑，153 条 byte-prefix 对齐保证与
  基线纵向可比；8 条 tool_output 单列——见 §7 留出族，2026-09-30 起降级为
  **同载体回归读数**，泛化读数改用 `data/heldout/v0.3-gen`）；
- **提示格式（2026-09-30 订正，强制）**：行为门禁必须以**部署提示格式**运行
  （`scripts/baseline_eval.py --prompt-format chat`，渲染入口
  `secfm/eval/promptfmt.py`）；裸续写（`raw`）口径仅可用于与历史读数对照。
  理由：裸续写把 SFT 模型的攻击成功率**高估 5–10 倍**（m25-full 0.6875 vs
  部署口径 0.0625），并曾据此得出"tool_output 8/8 顺从"的错误失败点
  （部署口径下 m2-calib/m2-full/m25-full 三档均 0 comply / 8 report）——
  见 `reports/s0-remediation-2026-09-30.md §1`；
- **统计纪律（2026-09-30 起强制）**：每个门禁必须报 n / 95%CI / Fisher p /
  所需样本量；差异不可区分时判定写"**未达可区分**"，不得写"通过/不通过"
  （判定器三态 ok/worse/undecidable，见 `scripts/m25_exit_verdict.py`）；
  子集判分必须**按 kind 分层**（alignment 条的 comply 是期望行为，
  混入鲁棒性分母会污染读数——该缺陷曾在 `review_statistical_power.py` v1
  与旧 G1 中各出现一次）；
- c1-full 与 m15 的 base 时代读数（post_m15_eval.ps1）作为行为基线锚点；
- 能力/校准条目：verdict 比对（verdict_correct 首次非零）；
- 通用能力：探针 v0.3 general 域 PPL 门禁（回升 ≤10%）；
- 长上下文：32k 无退化（延续 M1.5 对照）。

## 9. 消融与决策点

| 决策点 | 设计 | 关门标准 |
|---|---|---|
| instruct vs base 起步 | 同配方 SFT 两次（0.6B 可承受） | 政策条件化响应率、注入 ASR、通用能力三方读数 |
| lr/epochs | 校准跑（**套件就绪** 📦：sec_sft_v0 自建 2324 条已转换注册；`configs/m2-calib.yaml` lr 1e-5 × 2 epoch × eff-batch 16；训后链 `scripts/post_m2calib_eval.ps1`） | loss 曲线 + heldout 子集 |
| VERDICT 词表定稿 | 校准跑错误分析（v0 草案已首填：T1/T4/T7/T8/T9/T11，见 scripts/gen_sft_v0.py docstring） | 各族词表覆盖率 |
| 通用对话比例 | 10% vs 20% 对照 | 通用探针 + 对话质量人评 |

## 10. 开放问题

1. 数据源短名单（调研中）——公开集的许可与污染核查；
2. T3 九元组的 schema 落地（docs/00 §10.1 承接）；
3. zh 攻击面语料稀缺（M2 数据调研的中文专项重点）；
4. 多轮条目的对话格式与 LLaMA-Factory stage sft 的兼容（packing 关闭？）；
5. 校准跑规模与 heldout 子集切分（不污染 v0.2 主判据）。
