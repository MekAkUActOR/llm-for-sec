# Git 仓库初始化报告 — llm-for-sec 首次版本化

- **日期**：2026-10-14
- **工作目录**：`J:\Projects\llm_for_sec`
- **任务**：主工作区建本地 git 仓库（不推送；推送留待所有者提供远端）
- **结果**：`git init -b main` → 首次提交完成，**staged 1610 个文件 / 约 429.7 MB（<500MB 预算 ✓）**

---

## 一、结论摘要

| 项目 | 值 |
|---|---|
| 分支 | `main`（`git init -b main`） |
| 首次提交信息 | `llm-for-sec: M5 round-1 complete — dual-arm five-conjunction gates, verdicts, instruments v0.2.2-v0.7` |
| staged 文件数 | **1610**（含本报告、.gitignore、.gitattributes） |
| staged 总量 | **429.71 MB（450,585,824 bytes ≈ 工作树原样字节）** |
| 预算核对 | 429.70 MB < 500 MB ✓（余量约 70 MB） |
| 最大单文件 | 17.50 MB（`data/sft/dpo-reserve/pku-saferlhf.jsonl`），无任何文件 >20MB |
| 绝不入库核对 | LLaMA-Factory/ 0 个文件 ✓；checkpoints/ 0 个文件 ✓（check-ignore 抽查 36/36 通过 + porcelain 全量扫描 0 命中） |

提交身份为本仓本地配置（全局无 git 身份）：`user.name=llm-for-sec` / `user.email=llm-for-sec@local`。所有者推送前可改回本人身份（见「七、推送就绪说明」末尾）。

## 二、顶层体量盘点（步骤①，du 式）

| 顶层条目 | 文件数 | 大小 (MB) | 处置 |
|---|---:|---:|---|
| checkpoints/ | 1,231 | 456,415.79 | **排除**（训练权重，~445GB） |
| data/ | 93,697 | 30,616.09 | 按策略过滤后 **164 个 / 359.34 MB 入库** |
| .cache/ | 746 | 30,604.20 | **排除**（HF 等缓存） |
| .venv/ | 45,819 | 4,171.75 | **排除**（Python 虚拟环境） |
| reports/ | 903 | 121.21 | 过滤 resp/大日志后 **835 个 / 63.74 MB 入库** |
| scripts/ | 765 | 25.71 | 排除分片/退役/pyc 后 **456 个 / 4.85 MB 入库** |
| LLaMA-Factory/ | 722 | 20.12 | **排除**（第三方独立仓库） |
| tests/ | 186 | 2.56 | 66 个 / 0.60 MB 入库（其余为 .pyc） |
| secfm/ | 52 | 0.77 | 26 个 / 0.39 MB 入库（其余为 .pyc） |
| docs/ | 28 | 0.67 | 全部入库 |
| .scratch/ | 57 | 0.62 | **排除**（一次性探针/普查草稿） |
| configs/ | 29 | 0.08 | 全部入库 |
| .pytest_cache/ | 5 | 0.06 | **排除** |
| _work/ | 17 | 0.04 | **排除**（临时校验/分析工作目录） |
| logs/ | 4 | 0.01 | **排除**（GPU 监控/校验输出，沿旧版策略） |
| outputs/ | 0 | 0 | **排除**（训练输出目录，沿旧版策略；当前为空） |
| 根文件 | 5 | ~0.03 | `.gitignore` `.gitattributes` `MODEL_DATA_CARD.md` `pyproject.toml` `README.md` 入库；`$null`（0 字节误重定向产物）排除 |

排除目录后工作区共 95,403 个文件 → 入库 1,610 个（1.7%）。

## 三、排除清单与理由（步骤②，.gitignore 全量）

### 3.1 指令要求的必排项

| 规则 | 理由 | 实际排除量 |
|---|---|---|
| `/checkpoints/` | 训练权重 ~445GB，可再生（训练脚本在库） | 1,231 文件 / 456.4GB |
| `/.cache/` | HF/模型缓存 | 746 文件 / 30.6GB |
| `/LLaMA-Factory/` | **第三方独立仓库，绝不入库**（纪律） | 722 文件 / 20.1MB |
| `/scripts/_p16_parts*` | p16 分片产物（目录 `_p16_parts_abd/` 6.42MB、`_p16_parts_cef/` 9.50MB，及分片转储文件 `_p16_parts_cef_pack_templates.txt` 2KB） | ~16MB |
| `/scripts/_p07_parts/` | p07 分片产物 | 0.22MB |
| `/scripts/_retired/` | 退役脚本 | 0.01MB |
| `**/resp-*.jsonl` | 会话响应记录，推理产物可再生 | 69 文件 / 32.76MB（全在 reports/） |
| `/reports/logs/m5b-grpo-train*.log` | >10MB 日志登记排除：`m5b-grpo-train.log` 24.74MB（全库唯一超 10MB 者）；同系列 `m5b-grpo-train-r2.log` 当前 0.78MB 但正被 round-2 训练活跃写入，整系排除防后续提交膨胀 | ≥24.74MB |
| `*.png` | 训练曲线图 | 219 文件 / 104.64MB（均在 data/corpora，随目录规则一并排除） |
| 单文件 >50MB | 无需额外规则：过滤后 staged 最大 17.50MB，0 个 >20MB | 0 入库 |
| `.venv/` `__pycache__/` `*.pyc` `*.pyo` `.pytest_cache/` | Python 运行时 | ~4.2GB |

### 3.2 data/ 策略（指令：jsonl/md 默认保留、逐文件查大小、>20MB 登记后排除）

`.gitignore` 实现：`/data/**` 全排除 → `!/data/**/`、`!/data/**/*.jsonl`、`!/data/**/*.md` 重包含 → 再排除 `data/corpora/raw/` 与 39 个 >20MB 文件（last-match 语义，check-ignore 抽查 36/36 通过）。

- **入库**：data/ 下 ≤20MB 的 jsonl/md 共 **164 个 / 359.34 MB**：

| data/ 子目录 | 文件数 | 大小 (MB) |
|---|---:|---:|
| sft/ | 34 | 146.89 |
| probes/ | 35 | 85.92 |
| lf/ | 9 | 56.14 |
| dpo/ | 6 | 29.53 |
| corpora/（clean+顶层） | 26 | 28.39 |
| rlvr/ | 2 | 9.67 |
| heldout/ | 51 | 2.80 |
| dpo-remediation-staging/ | 1 | 0.00（仅 README.md） |

- **登记排除（>20MB 的 jsonl/md，39 个，共 12,218.91MB ≈ 11.93GB）**：见「四」。

- **data/corpora/raw/ 整目录排除（工程决策，特此登记）**：原始外部语料转储（enwiki/zhwiki .bz2、cvelistV5 .zip、ghsa .zip、parquet、.tsv 等 ~14.4GB），且内含 **12 个嵌套 `.git` 第三方克隆仓**：`gtfobins`、`lolbas`、`p0-0days`、`m2/_repo_harmbench`、`m2-research/{agentdojo, ChineseSafetyQA, InjecAgent, llm-attacks, Safety-Prompts, strongreject, TrustLLM, xstest}`。理由：①与 LLaMA-Factory 同属第三方独立仓库（指令同类别排除）；②若不排除，`git add` 会将嵌套仓记为坏 gitlink（无 .gitmodules，无法克隆还原）；③其中的 jsonl/md 为外部数据非本项目成果物。受此影响未入库的 raw 内 jsonl/md 共 290 个 / 24.57MB（含 pku-saferlhf Alpaca-7B/2-7B/3-8B train.jsonl 73.90/69.14/56.62MB 三个 >20MB 者，已随目录排除）。**如需保留 raw 内某文件：`git add -f <路径>` 或调整 .gitignore 后单独提交。**

- **data/ 非 jsonl/md 文件默认排除（~14.9GB）**：二进制（models/classifier-v1/model.pkl 27.34MB、tokens_test.npy、.parquet/.pkl/.bz2/.zip 等）与小型元数据（lf/dataset_info.json、heldout 与 probes 的 .json/.log、sft 与 dpo 的 .json、m*-run 的 .json/.txt、ontology/*.json、fertility/*.txt、corpus_test/*.txt，合计 <2MB）——均可由 scripts/ 再生或属外部转储。指令口径为「data/ 的 jsonl/md 默认保留」，故其余格式不入库。

### 3.3 其他排除（沿旧版 .gitignore 策略 + 通用惯例）

- `/outputs/`、`/runs/`：训练运行产物目录（outputs 当前为空，runs 不存在；防未来误入）。
- `/logs/`：GPU 监控/校验输出（gpu_monitor*.csv、verify_*.txt，12KB）。
- `/.scratch/`、`/_work/`：一次性探针、普查草稿、校验日志工作目录。
- `/$null`：0 字节 PowerShell 误重定向产物。
- `.pytest_cache/`：测试缓存。

### 3.4 新增 .gitattributes（字节级完整性）

`* -text` 禁用一切行尾转换：全局 `core.autocrlf=true` 会在未来 clone/checkout 时把 LF 改写为 CRLF，破坏 jsonl 数据件的哈希可复现性；此设置保证 **blob = 工作树原样字节，任何机器克隆往返一致**。staged 总量 450,573,086 bytes 即工作树原样字节（`git add --renormalize .` 已按此属性重建索引）。

## 四、>20MB jsonl/md 登记表（39 个，逐文件检查结果）

| # | 大小 (MB) | 路径 |
|---:|---:|---|
| 1 | 4,238.74 | data/lf/sec_c1_full.jsonl |
| 2 | 2,870.62 | data/corpora/clean/c1_enwiki_gen.jsonl |
| 3 | 1,024.21 | data/lf/sec_c1.jsonl |
| 4 | 754.62 | data/corpora/clean/c1_zhwiki_gen.jsonl |
| 5 | 341.20 | data/lf/sec_m15.jsonl |
| 6 | 279.74 | data/lf/sft_m25.jsonl |
| 7 | 233.69 | data/corpora/clean/c0_all.jsonl |
| 8 | 233.51 | data/lf/sec_c0.jsonl |
| 9 | 224.17 | data/corpora/clean/c0_cve.jsonl |
| 10 | 206.76 | data/corpora/clean/c0_redhat-csaf.jsonl |
| 11 | 197.88 | data/sft/m1/train.jsonl |
| 12 | 197.88 | data/lf/sft_m1.jsonl |
| 13 | 185.18 | data/lf/sec_m16.jsonl |
| 14 | 81.86 | data/dpo/m3/train.jsonl |
| 15 | 81.86 | data/lf/dpo_m3.jsonl |
| 16 | 71.78 | data/m5-run/dpo_m5_calib.jsonl |
| 17 | 71.78 | data/m5a-run/train.jsonl |
| 18 | 70.31 | data/corpora/clean/t6_cvefixes.jsonl |
| 19 | 66.04 | data/corpora/clean/c1_arxiv_full.jsonl |
| 20 | 59.67 | data/corpora/clean/t6_devign.jsonl |
| 21 | 57.02 | data/dpo-remediation-staging/dpo_m4_capfix.jsonl |
| 22 | 57.02 | data/m4-run/dpo_m4_capfix.jsonl |
| 23 | 55.30 | data/lf/sec_sft_needlefix_carrier.jsonl |
| 24 | 53.30 | data/lf/dpo_m3_final.jsonl |
| 25 | 41.87 | data/lf/sec_sft_needlefix.jsonl |
| 26 | 40.18 | data/m4-run/dpo_m4_rebal.jsonl |
| 27 | 39.35 | data/lf/needle_longctx_slice.jsonl |
| 28 | 38.01 | data/lf/dpo_m3_v2_q.jsonl |
| 29 | 38.01 | data/lf/dpo_m3_v2.jsonl |
| 30 | 35.90 | data/corpora/clean/c1_zhwiki_sec.jsonl |
| 31 | 35.01 | data/corpora/clean/c0_msrc-cvrf.jsonl |
| 32 | 34.10 | data/corpora/clean/c0_debian-dsa.jsonl |
| 33 | 32.82 | data/corpora/clean/c0_cisco-psirt.jsonl |
| 34 | 32.65 | data/sft/m2.5-staging/fG_t6_devign_ext.jsonl |
| 35 | 32.02 | data/lf/dpo_m3_v2_strict.jsonl |
| 36 | 28.91 | data/corpora/clean/c0_sans-isc.jsonl |
| 37 | 27.10 | data/sft/dpo-reserve/cvalues.jsonl |
| 38 | 27.04 | data/corpora/clean/c2_aisafety_arxiv.jsonl |
| 39 | 21.78 | data/corpora/clean/t6_devign_lines.jsonl |

另：data/ 内非 jsonl/md 的 >20MB 文件（dpo-remediation-staging/dpo_m4_lenmatch.jsonl.superseded 57.34MB、models/classifier-v1/model.pkl 27.34MB、corpora/raw 下 zip/bz2/parquet/tsv/pkl 等）随「data 仅 jsonl/md」与 corpora/raw 目录规则一并排除。

## 五、staged 内容统计（步骤③）

| 顶层 | 文件数 | 大小 (MB) |
|---|---:|---:|
| data/ | 164 | 359.34 |
| reports/ | 835 | 63.74 |
| scripts/ | 456 | 4.85 |
| docs/ | 28 | 0.67 |
| tests/ | 66 | 0.60 |
| secfm/ | 26 | 0.39 |
| configs/ | 29 | 0.08 |
| 根文件（.gitignore/.gitattributes/MODEL_DATA_CARD.md/pyproject.toml/README.md） | 5 | 0.03 |
| **合计（不含本报告）** | **1609** | **429.70** |
| **合计（含本报告）** | **1610** | **429.71** |

staged 前 10 大文件均在 11–17.5MB（data/sft、data/lf、data/probes 的训练/探针 jsonl），全部 ≤20MB。

## 六、核对与提交记录（步骤④）

- `git check-ignore` 抽查 **36/36 通过**：必排项（checkpoints、LLaMA-Factory、.cache、.venv、corpora/raw、_p16_parts*、_p07_parts、_retired、resp-*、>10MB 日志、$null、png、>20MB jsonl）全部 IGNORED；应保留项（scripts/、data 各子目录 jsonl/md、小日志、reports json、docs、secfm、tests、configs）全部 KEPT。
- `git status --porcelain` 全量核对：**1610 × 'A '**（含本报告），禁入路径（LLaMA-Factory/、checkpoints/、.cache/、.venv/、corpora/raw/、分片目录、resp-*、png、pyc、$null）**0 命中**；staged 0 个文件 >20MB。
- `git add` 仅有 LF/CRLF 提示（已由 .gitattributes `* -text` 消除后续影响），无错误。
- 首次提交已完成（`main` 分支；提交信息与指令逐字一致，em-dash 编码核验通过；提交作者为本地配置身份）。`.git` 对象库 **76.05 MiB**（2109 objects / 2 packs；jsonl 文本压缩后约为工作树 429.71MB 的 18%，推送上传量即此规模）。
- 本地仓配置：`user.name=llm-for-sec`、`user.email=llm-for-sec@local`、`core.longpaths=true`（Windows 长路径保险）。

## 七、推送就绪说明（步骤⑤）

远端未配置（无凭据，按指令不推送）。**所有者只需三步**：

```bash
# 1) 创建私有远端（需 gh 已登录；或网页手动建仓）
gh repo create llm-for-sec --private

# 2) 绑定远端（<OWNER> 替换为实际 GitHub 用户名/组织名）
git remote add origin https://github.com/<OWNER>/llm-for-sec.git

# 3) 推送
git push -u origin main
```

可选（推送前修正提交作者为本人身份）：

```bash
git config user.name "<你的名字>"
git config user.email "<你的邮箱>"
git commit --amend --reset-author --no-edit
```

注意：`reports/logs/m5b-grpo-train-r2.log` 正被 round-2 训练写入（已整系 ignore）；round-2 产物（新 resp-*.jsonl、checkpoints 等）均已被规则覆盖，后续 `git add -A` 不会误入。

## 八、纪律核对清单

- [x] 绝不 add LLaMA-Factory（0 文件 staged，check-ignore PASS）
- [x] 绝不 add checkpoints（0 文件 staged，check-ignore PASS）
- [x] staged 总量 429.70MB < 500MB
- [x] commit 前 `git status --porcelain` 全量核对（1609 'A '，禁入 0 命中）
- [x] data/ jsonl/md 逐文件检查，>20MB 者 39 个全部登记并排除
- [x] 任何单文件 >50MB 排除（staged 最大 17.50MB）
- [x] 首次 commit 信息与指令逐字一致

GIT-SETUP=DONE
