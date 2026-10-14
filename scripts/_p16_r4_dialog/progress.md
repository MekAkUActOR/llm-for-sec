# P1.6 四轮 F 对话式扩容施工账本（F4-dialog，progress.md）

- 规格：`reports/p1.6-round4-design.md`（§二 配方 + §四 施工规格；§三 T1–T4 预注册已冻结）
- 任务总量：F 对话式扩容 **792 新生成对**（2 批，每批 396 ≤400）+ G9 同款污染检查 1 件
- 纪律：✗✓ 全项留痕——不读 `data/probes/**` 与 `data/heldout/**`（G9 检查器除外：官方
  checker 样板扫描为其本职，builder 输入只有自建网格 + 冻结模板）；零接触
  `_p16_parts_cef/`、`_p16_parts_abd/` 的**写面**（公共库只读 import，绝不调用其
  write_part/PARTS_DIR）；F4 编码变形 / F6 权限伪造永不用（含仿写变体）；零武器化
- 种子：`SEED_R4=20261014`（每风格独立子流 = SEED_R4 + STYLES 索引；确定性，manifest 登记）
- tokenizer = `checkpoints/qwen3-06b-sec-m4-capfix-probe`（真实部署 tokenizer，批检 ≤970；
  G8 全量门 ≤1000）
- 三包模板：`p16cef_common.assert_packs()` 启动断言（sha256 与一轮登记逐位一致）
- 行级机检：`p16cef_common.batch_check`（冻结公共库 import 零改动：schema 11 键序 /
  VERDICT 五键词表 / H1 标记词双向 / H4 逐对 [0.7,1.4] + 批中位 [0.9,1.1] / F4F6 红线 /
  零武器化 / token ≤970）+ 本生成器新增四断言（prompt 全局唯一 / id 与一轮零重叠 /
  逐风格配额闭合 / 原型计数 ≤48）

## 0. 盘点（2026-10-14 20:0x，本任次首步）

1. 一轮对话层 f07/f08 = 792 行（esc+rol 396 / fic+puz 396；2 轮 577 / 3 轮 215，无 4 轮
   形态）——扩容对象与其**零文本复用**（新骨架 11–20 / 新主题 / 新施压句 / 新响应模板）。
2. G1 扫描交互承 r3 遗留：r4 落点在 checker 扫描范围内 ⇒ 不跑全 checker，快检替代 =
   行级断言（本账本）+ G9 同款专项检查（check_f4_g9.py）+ 冻结件 sha 复验（build_p16_r4.py）。
3. GPU 状态：本目录全部命令纯 CPU；训练发射另行 Guard 排队（RL 四轮代理在跑）。

## 1. 施工决策（规格缺口/口径澄清，登记入报告）

| # | 决策 | 依据 |
|---|---|---|
| D1 | F 对话式扩容采用「专门子族 F4-dialog」而非原 792 行重生：一轮 f07/f08 冻结行**逐字节保留**，新 792 行独立成件（p16_f4_dialog.jsonl，四注册装载） | 冻结件只读零覆写纪律；恶意件 sha 保持一轮登记值 f9dac930… 可验 |
| D2 | 四风格配额与一轮对话层同构（各 198；en119/zh79；def89/pro79/cons30；cd99/lip99）——形态混合与语言/包分布**不是**本轮变量 | 单机制变量纪律（量与轮深） |
| D3 | 轮深新轴：新骨架前缀交换 1/2/3 组按 3:4:3（每风格每语言）；一轮对话层 2 轮为主（577/792）无 4 轮 | jb 4 轮战场 + B 族 3/4 轮形态对齐（设计 §一.2/§二） |
| D4 | id 延续 F 族编号 002641–003432（不另起新前缀）：G2 行断言 `p16-F-\d{6}` 同口径，谱系连续 | arch 11–20 与一轮 01–10 不碰撞，G11 上限 48 余量充足 |
| D5 | 施压句仅附加于 en 溢出行（j≥100，19 行/风格）保证组合唯一；zh 79 行 < 100 组合无需附加 | 一轮 (i+j)%5 分支的简化替代，唯一性由断言保证 |
| D6 | rejected lip「交付」仍为四段式模式级复述（摸底/试探/实施/收尾，无操作增量）；新写措辞与一轮零复用 | H1 诚实性 + 零武器化；风格多样性 |
| D7 | H4 垫句池新写 3+3 条（zh/en），触发线 0.90（一轮同款机制） | rejected 过短时补齐长度平价 |
| D8 | G9 同款检查 = monkeypatch 官方 checker ROWS 后调 gate_g9()（官方两段式全逻辑零改动） | 任务书「G 门禁行级断言——8-gram 污染检查对 heldout 冻结件」的最忠实实现 |

## 2. 维度配比（精确边际，代码保证）

- **每风格 198**：en 119 / zh 79；pack default 89 / professional 79 / conservative 30；
  form cd 99 / lip 99；骨架 11–20 轮转（每骨架 ~12 en + ~8 zh 行）
- **合计 792**：en 476 / zh 316（60.1:39.9）；def 356 / pro 316 / cons 120；cd 396 / lip 396
- 轮深（user 轮数）预期分布：2 轮 ~238 / 3 轮 ~316 / 4 轮 ~238（骨架 1/2/3 组交换按 3:4:3
  轮转；实测以批检 dist 为准）
- 批次：g01 = escalation+roleplay 396；g02 = fictional+puzzle 396（id 升序 2641–3432 连续）

## 3. 批次账本（每批落盘后追加：rows/sha256/自检数字；机器可读真值 = parts/*.check.json）

| batch | file | rows | sha256 | checks | ts |
|---|---|---|---|---|---|
| g01 | parts/part-g01.jsonl | 396 | `2eeb7516fdcdae84d9f9718991550087ce00e4b51dbcf7875bc770e1064387c4` | fails=0；H4 中位 0.9389（min 0.9/max 1.0377）；token max 442/mean 371.5；en 238/zh 158；def 178/pro 158/cons 60；cd 198/lip 198；user_turns 2:120/3:140/4:136 | 2026-10-14 |
| g02 | parts/part-g02.jsonl | 396 | `077871df58bcf5a16d617a1a405a666c633d22c2a3a12b99c81566c7df97493d` | fails=0；H4 中位 0.9498（min 0.9006/max 1.0098）；token max 448/mean 366.7；en 238/zh 158；def 178/pro 158/cons 60；cd 198/lip 198；user_turns 2:120/3:140/4:136 | 2026-10-14 |

合计实测：792 行（id p16-F-002641…p16-F-003432 升序全局唯一，与一轮 5,760 id 零重叠 ✓）；
en 476/zh 316（60.1:39.9）；def 356/pro 316/cons 120；cd 396/lip 396；
**user_turns 2:240 / 3:280 / 4:272**（30.3%/35.4%/34.3%——4 轮形态从一轮的 0 提至 272，
3+4 轮合计 69.7% vs 一轮 27.1%）；prompt 全局唯一 792/792 ✓；原型计数 max ≤48 ✓。

## 4. G9 同款污染检查（新内容放行条件）

| 检查 | 对象 | 样板 | 结论 | ts |
|---|---|---|---|---|
| G9-equivalent（官方 gate_g9 代码路径，monkeypatch 文档侧） | 792 新行 | data/heldout 全部 12 版本目录 + data/probes 全部（68 文件 / 12,460 needle / 30,733,933 窗口） | **PASS ✓✓**：官方 char-gram 游程 ≥50 对数（验证后）= 0；每针最大游程 = 0；诊断层 threshold=30 全量全景 0 对（耗时 111 s；产物 parts/part-f4-g9.check.json + reports/logs/p16-r4-g9-check.log） | 2026-10-14 |

## 5. 进度备注

- [x] 盘点（规格/遗留/环境）
- [x] content_f4_dialog.py（4 风格 × 2 语言 × 10 新骨架 + 10 新主题 ×2 + 施压句 ×2 + 响应模板）
- [x] gen_f4_dialog.py（确定性生成 + 行级断言 + 配额闭合 + 唯一性断言 + 批检落盘）
- [x] check_f4_g9.py（G9 官方逻辑 monkeypatch 复用）
- [x] g01 批落盘（fails=0，sha 2eeb7516…）
- [x] g02 批落盘（fails=0，sha 077871df…）
- [x] G9 同款检查 PASS（官方游程 ≥50 对数 = 0）
- [x] build_p16_r4.py 组装 release（data/dpo/p16-calibration-r4/）+ dataset_info + config + 冒烟
      （BUILD-P16-R4=OK · VERIFY-R4=PASS · DIFF-HP-ZERO=PASS · SMOKE-M5A-R4-MULTIDS=OK；
      施工后独立复检 VERIFY-R4-POST=PASS rc=0；f4_dialog 冻结 sha `f3052110…c78819`）
- [x] 报告 reports/p1.6-round4-build.md（P16-R4-BUILD=DONE）+ 抽查件 p1.6-spotcheck-r4.md（16 行，PENDING_HUMAN_GATE）

## 6. 训练/门禁阶段登记（发射后追加）

- configs/m5a-dpo-r4.yaml sha256 = 47eb8b616fe47f4590fcc5af8807450c6cc84d0fb5edbb659004b93ce09c84d5（build 落盘值，gates 报告复验锚）
- 门禁链准备（20:4x）：run_m5a_r4_gates.ps1（8 步 fail-closed，Guard+重 worker=0 双确认，15 产物 PREFLIGHT，仪器 sha 复验内置）
- 训练发射器 wait_and_train_m5a_r4.ps1（等 RL-v4 链 verdict 落地或静默>15min 双确认 → Guard → NOT-EXIST → llamafactory-cli train；后台 job pwsh-584 承载）
- sanity 核验 _tmp_m5a_r4_sanity.py（结构/300 步/runtime/loss/margins/acc）+ gates 报告骨架 m5a-r4-gates.md（八方对照表七臂基线已填，r4 位留待实测）
