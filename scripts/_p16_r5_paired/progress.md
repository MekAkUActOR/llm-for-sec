# P1.6 五轮 F5-paired 同场景对比对施工账本（progress.md）

- 规格：`reports/p1.6-round5-design.md`（§二 F5-paired 1,000 对 = 2,000 行 2×2 完全镜像；§三配方 =
  r3 冻结配方逐字节 + F5-paired 2,000 新行（**F4-dialog 792 回退不带入**，父代理 2026-10-15 批准原案）；
  §四 U1–U4 预注册已冻结，判读不回改 ✗✓）
- 父代理补充硬门（2026-10-15 裁决，✗✓）：① 施工前置等 `m5a-r4-gates.md` 终稿钉死对照基线
  （GPU 侧排队，排队时长入报告）；② **G9 双跑**（parts 层 + release 落盘字节）；③ **拼接口径冒烟
  36,458 行零丢弃**（r4 教训：独立装载不充分）；④ **生成器原生 gpt 标签**（不走 r4 两层
  assistant→gpt 归一化路线，从源头消灭 23:13 事故类）——三处均为硬门。
- 纪律：✗✓ 全项留痕——不读 `data/probes/**` 与 `data/heldout/**`（G9 检查器除外：官方 checker
  样板扫描为其本职，builder 输入只有自建网格 + 冻结模板）；零接触 `_p16_parts_cef/`、
  `_p16_parts_abd/`、`_p16_r4_dialog/` 的**写面**（公共库只读 import，绝不调用其 write_part/PARTS_DIR）；
  F4 编码变形 / F6 权限伪造永不用（含仿写变体）；零武器化（族F 全字段口径沿用）；冻结件只读零覆写；
  一~四轮产物落点只读。
- 种子：`SEED_R5=20261015`（每风格独立子流 = SEED_R5 + STYLES 索引；确定性，manifest 登记）
- tokenizer = `checkpoints/qwen3-06b-sec-m4-capfix-probe`（真实部署 tokenizer，批检 ≤970；G8 全量门 ≤1000）
- 三包模板：`p16cef_common.assert_packs()` 启动断言（sha256 与一轮登记逐位一致）
- 行级机检：**f5check.py（本轮新写）**——冻结公共库 `p16cef_common` 的 FAM["F"] 词表
  （polarity=malicious_refuse 单侧 / forms={cd,lip} / chosen 必须 refuse）与 F5 2×2 镜像行
  （良性孪生 chosen=answer/allow 等）不兼容，设计 §二.1 已预授权「新增 rejected_form 枚举
  （机检词表）」；marker 词表尽量复用冻结清单（JUDGE/REFUSE/HOLD/CD/COMPLY/WEAPON/F4F6），
  新增项在本文件登记。冻结公共库本身零改动，只读 import（make_row/conv_multi/gpt/verdict_line/
  quota_list/ntok/断言函数）。

## 0. 盘点（2026-10-15 01:1x，本任次首步）

1. 设计稿 §二（最小对定义/2×2 四格/规格样本 P-1 P-2/机制论证）+ §三（配方总表：r5 = r3 逐字节
   5,616 + F5 2,000 = 7,616，良 3,736:恶 3,880 = 49.0:51.0；装载 36,458；epoch 2,279 步）为施工权威；
   §五/§六 骨架态【待填】——施工细节按任务书步骤 + r4 先例（p1.6-round4-build.md）+ 父代理裁决补齐，
   决策逐条登记本账本 §1。
2. 规格**样本 P-1/P-2 非训练行**（设计原文：「规格件非训练行；builder 单测金样本」）——两样本主题
   （内部文档倒卖 / credential phishing）**不进入**训练行主题池（样本/训练分离纪律）。
3. GPU 状态：本目录全部命令纯 CPU；m5a-r4 门禁链在途（dilution 步，attempt-2 0:41 起）；
   RL-r5（m5b-p2rl-grpo-v5）尚未见发射证据。训练发射另行排队（§6）。
4. 冻结输入链对账（build 时 8 项 sha 恒等，同 r4 口径）：r1 两 release + r1 parts-abd/cef +
   r3 两 release + parts-d-sub + m4 基座 d4061d47…（28,842 行）。

## 1. 施工决策（规格缺口/口径澄清，登记入报告）

| # | 决策 | 依据 |
|---|---|---|
| D1 | 子族独立成件 `p16_f5_paired.jsonl`（2,000 行），dataset_info 四注册第 4 条（base + benign + malicious + f5paired）；F4-dialog 792 行**不带入**（r4 变量回退，§三） | 冻结件只读零覆写 + 单一机制变量；恶意件 sha 保持一轮登记值 f9dac930… 可验 |
| D2 | 配方 = r3 冻结配方逐字节（良性 2,736 + 恶意 2,880 从 r3 目录逐字节复制）+ F5-paired 2,000 新行；极性比 49.0:51.0（良 3,736 = 2,736+1,000；恶 3,880 = 2,880+1,000） | 设计 §三配方总表 + 父代理裁决 |
| D3 | 网格：4 风格 × 250 对；每风格 en 150 / zh 100 对（行 300/200；全局 1,200:800 = 60:40，同 r4）；pack default 112 / professional 100 / conservative 38（同 r4 比例 44.8:40:15.2）；user_turns 2/3/4 = 75/100/75 对（3:4:3，骨架组 3/4/3 决定；全局行 600/800/600） | 形态混合与语言/包分布不是本轮变量（r4 D2 先例）；轮深轴沿 r4 |
| D4 | 主题池 = 15 en + 10 zh（每语言单侧）；每风格 (theme × skeleton) 组合恰一次：en 15×10=150 ✓ / zh 10×10=100 ✓——无溢出行、无附加句 | 250 对/风格精确闭合；规格样本两主题不进池 |
| D5 | 骨架 = 每风格每语言 10 个新骨架（01–10；轮深组 01–03 = 1 组交换 / 04–07 = 2 组 / 08–10 = 3 组）；archetype = `F-p5d-{esc\|rol\|fic\|puz}-{01..10}`（en）/ `…{nn}z`（zh，尾字母区分语言侧骨架——房形 `^F-(car\|dlg)-[a-z]+-\d{2}[a-z]?$` 尾字母先例）；每 archetype 行数 en 30 / zh 20 ≤ 48（G11 口径） | 轮深 3:4:3 精确 + G11 上限；en/zh 骨架文本本就不同实体 |
| D6 | id 延续 F 族编号 **p16-F-003433…p16-F-005432**（r4 止于 003432；对内交错：对 k 良性=3433+2k / 恶性=3434+2k，文件按 id 升序 = 对相邻） | r4 D4 先例（G2 行断言 p16-F-\d{6} 同口径，谱系连续）；对相邻便于对级审计 |
| D7 | src_task = `p16:F:paired-r5:{style}`；dpo_class = **`p16_paired_scene`**（新子族类）；polarity 用既有词表：良性孪生 `benign_release` / 恶性孪生 `malicious_refuse`（极性比计数与全语料同径） | p16:F: 前缀族连续；极性词表兼容（r3 良性件全量 benign_release 实查 ✓） |
| D8 | rejected_form 新枚举：良性孪生 `risk_misapplication_refuse`（误套 75%）/ `hold_deferral`（悬置 25%）；恶意孪生 `false_clear_comply`（100%）；配额每风格 188/62（全局 750/250 恰 3:1） | 设计 §二.1 四格表（75%/25%/100% 钉死） |
| D9 | **生成器原生 gpt 标签**：前缀模型轮 from='gpt' 直接生成（parts 层 = release 层字节恒等；组装层零归一化改写，期望改写数 = 0 并断言）；角色词表断言 from ∈ {system,human,gpt}，计数精确 system 2,000 / human 6,000 / gpt 4,000 | 父代理硬门 ④（r4 23:13 事故类从源头消灭；r4 两层约定就此退役，登记为 r5 变更） |
| D10 | 四格 chosen/rejected 语义（机检口径）：良性 chosen = answer/allow ∧ JUDGE 标记 ∧ ¬REFUSE ∧ findings 非空 ∧ ①–④ 四条目密度；良性 rejected 误套 = refuse/refuse ∧ REFUSE 标记 ∧ ¬JUDGE；良性 rejected 悬置 = refuse/hold ∧ HOLD 标记 ∧ ¬JUDGE；恶意 chosen = refuse/refuse ∧ REFUSE ∧ ¬CD ∧ ¬JUDGE ∧ 替代方向标记 ∧ findings 非空；恶意 rejected = answer/allow ∧ ¬REFUSE ∧ ¬JUDGE ∧ 四步/four moves ∧ 出界声明（工具/命令不在范围） | 设计 §二.1 四格 + 样本 P-1/P-2 逐字对齐（金样本单测） |
| D11 | 跨槽位长度/密度平价（设计 §二.3 P4「内容丰厚度通道压到二阶」）：对级断言 len(良chosen)/len(恶rejected)（T_del 轴）与 len(良rejected)/len(恶chosen)（T_ref 轴）各 ∈ [0.7,1.4]，批中位 ∈ [0.9,1.1]；密度平价 = T_del 双格各恰 4 条目、T_ref 双格纯散文（① 计数机检） | 设计 §二.3 机制论证施工化 |
| D12 | 末轮模板：骨架帧 `frame.format(x=载荷短语, y=交付物名词)`，良性 (x={cat}的防御要点, y=检查清单/defensive takeaways→checklist) / 恶性 (x={cat}的操作步骤, y=演示步骤/operational steps→walkthrough)；两孪生帧逐字节同（构造保证 + 重建断言）；末轮长度带断言 ∈ [0.7,1.4] | 设计 §二.1「同句式/同语域/同长度带，仅载荷短语不同」+ 样本 P-1/P-2 句式 |
| D13 | 共享前缀逐字节断言：system（同 pack）+ conversations[1:-1] 前缀轮两孪生逐字节恒等（对级机检）；全 prompt 全局唯一 2,000/2,000；id 与一~四轮零重叠（r1 5,760 + r4 792 id 集） | 设计 §二.1「前缀逐字节相同」+ 任务书「prompt 全局唯一」 |
| D14 | 批次：8 批 × 125 对 = 250 行（≤400 行/批，r4 约束）；b01/b02 = esc 对 0–124/125–249，b03/b04 = rol，b05/b06 = fic，b07/b08 = puz；每批落盘 + check.json（行/对级机检 fails=0 + dist）；配额闭合在**风格级**断言（批为半风格，r4 批=整风格故批内闭合——口径差异登记） | r4 批 ≤400 先例 + 本轮 2,000 行规模 |
| D15 | G9 双跑：① parts 层（8 批合并 2,000 行，生成器原生 gpt 字节）；② release 层（`p16_f5_paired.jsonl` 落盘字节再复跑）——官方 gate_g9 代码路径 monkeypatch 文档侧，零改动 | 父代理硬门 ② + r4 双跑先例（本轮无归一化，双跑防组装层损伤，字节恒等断言） |
| D16 | 冒烟主口径 = **拼接口径**：llamafactory `_get_merged_dataset(stage=rm)` 四条目真装载真转换真拼接，断言 **36,458 行 + 零丢弃行**（_prompt/_response 全非空）；独立装载为辅助口径 | 父代理硬门 ③ + r4 §5.2/§7 教训（独立装载不充分） |
| D17 | config：configs/m5a-dpo-r5.yaml = r4 config 头部插 r5 块 + 非注释功能 diff 恰 3 行（dataset_dir → data\m5a-r5-run / dataset → 四 r5 注册 / output_dir → checkpoints\qwen3-06b-sec-m5a-dpo-r5）；HP 零改动（DIFF-HP-ZERO 机器证明） | 任务书步骤 ③ + r4 §4 先例 |
| D18 | 金样本单测：P-1（escalation·zh·default·3 轮·内部文档倒卖）+ P-2（fictional·en·professional·2 轮·credential phishing）按冻结三包模板渲染，过**对级结构检查**（前缀恒等/末轮帧/四格 VERDICT 组合/密度/词表/F4F6/零武器化/token）；生成行另过内容 marker 全检（金样本 P-2 en 误套句无 REFUSE 标记词——内容 marker 检查只对生成行强制，结构检查对两者强制，登记） | 设计 §二.2「builder 单测金样本」 |

## 2. 维度配比（精确边际，代码保证）

- **每风格 250 对**：en 150 / zh 100；pack def 112 / pro 100 / cons 38；user_turns 75/100/75；
  良性 rejected_form 误套 188 / 悬置 62
- **合计 1,000 对 = 2,000 行**：en 1,200 / zh 800（60:40）；def 448 / pro 400 / cons 152；
  turns 600/800/600；误套 750 / 悬置 250 / false_clear_comply 1,000；
  极性 benign_release 1,000 / malicious_refuse 1,000
- id p16-F-003433…005432（升序全局唯一，与 r1/r2/r3/r4 零重叠 ✓）；archetype 计数 max = 30（en 侧）≤ 48 ✓
- 角色标签计数（原生 gpt）：system 2,000 / human 6,000 / gpt 4,000

## 3. 批次账本（每批落盘后追加：rows/sha256/自检数字；机器可读真值 = parts/*.check.json）

| batch | file | rows | sha256 | checks | ts |
|---|---|---|---|---|---|
| （待落盘） | | | | | |

## 4. G9 同款污染检查（新内容放行条件）

| 检查 | 对象 | 样板 | 结论 | ts |
|---|---|---|---|---|
| （待跑） | | | | |

## 5. 进度备注

- [x] 盘点（规格/遗留/环境/父代理裁决）
- [x] 本账本 §0–§2（决策 D1–D18 + 配比）
- [ ] content_f5_paired.py（15 en + 10 zh 主题 ×12 内容件 + 4 风格 ×2 语言 ×10 骨架 ×7 文本 + 2×2 响应模板 ×2 语言 + 金样本）
- [ ] f5check.py（行级/对级/批级机检）
- [ ] gen_f5_paired.py + 8 批落盘
- [ ] G9 双跑 PASS
- [ ] build_p16_r5.py（组装 + manifest + dataset_info + config + 冒烟）
- [ ] 独立复检 + 抽查件 + 施工报告

## 6. 训练/门禁阶段登记（发射后追加）

- （待发射：排队条件 = m5a-r4 门禁链终稿（topup-verdict-m5a-dpo-r4 落地或静默双确认）+ RL-r5
  训练让出（若其先训）+ 重 worker=0 双确认 → Guard → output_dir NOT-EXIST → llamafactory-cli
  train，Tee reports\logs\m5a-dpo-r5-train.log）
themes done 08:30
