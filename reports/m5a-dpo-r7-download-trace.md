# m5a-r7 下载通道执行留痕（Qwen3-8B-Base 入缓存全记录）

- 执行人：r7-runner（Team Lead 裁决方案 A，授权消息 2026-10-16 01:14）
- 时间窗：2026-10-16 00:46 – 01:2x（详见各节时间戳）
- 纪律：fail-closed（任何文件 sha256/size 不匹配即停手报 Lead）、append-only、来源可溯

## 一、时间线

| 时刻 | 事件 |
|---|---|
| 00:46:15 | Lead 发射直连 HF 下载（snapshot_download，xet 后端，PID 39128/33076） |
| 00:54–00:56 | r7-runner 轮询：盘上仅 67MB —— xet 内存缓冲未刷盘假象（当时未识破） |
| ~01:03:38 | 直连任务实际已缓冲+落盘 6.7GB（~41%，有效速率 ~6.6MB/s），最后一笔写入 |
| 01:03:46 | Lead 以"12 分钟仅 0.06GB"为由杀直连、重启 hf-mirror 下载（PID 24108/33316，HF_ENDPOINT=hf-mirror.com，走本地代理 7890） |
| 01:04–01:08 | r7-runner 探针诊断：mirror 临时文件零增长、15 条代理连接空转（CPU 累加、WS 涨） |
| 01:08–01:11 | 吞吐探针（15s 独立连接）：hf-mirror range 3.4KB/s / full GET 66KB/s（**对 xet-backed 仓库透传回 us.aws.cdn.hf.co，非自有 CDN**）；官方 HF 经代理单流 637KB/s；ModelScope 经代理 27.7MB/s；**ModelScope 直连 34.6MB/s** |
| 01:12 | ModelScope API 清单核验：5 分片 Sha256 与 HF trees\49e3418f….json lfs_sha256 **逐字节一致**；12 个目标文件尺寸全对 |
| 01:13–01:14 | r7-runner 报 Lead（诊断表 + 三方案）；Lead 裁决**方案 A**（杀 mirror、ModelScope 直连、sha256 验证入缓存、清死数据、代录 xet 教训） |
| 01:14:20 | 杀 PID 24108/33316（确认死）；删 8 个 .incomplete（10.1GB）+ xet CAS 缓存目录 |
| 01:15:49 | `_tmp_ms_download_r7.ps1` 后台发射（暂存 → 验证 → 入快照三段 fail-closed） |
| （下载完成后本表补齐） | MS-CACHE-FILL=OK / 训练发射 / 合并 / 门禁链 / W 读数 |

## 二、通道实测数据（15s 探针，2026-10-16 01:08–01:11）

| 通道 | 实测吞吐 | 判定 |
|---|---|---|
| hf-mirror → us.aws.cdn.hf.co（xet-bridge）经代理，range 50MB | 3,389 B/s | ✗ |
| hf-mirror 同上，full GET | 66,086 B/s | ✗ |
| 同目标直连（noproxy） | 0 B/s（被墙） | ✗ |
| 官方 huggingface.co 经代理，range 50MB | 637,186 B/s | △（xet 并行聚合实测 ~6.6MB/s） |
| ModelScope 经代理，range 50MB | 27,725,099 B/s | ✓ |
| **ModelScope 直连（noproxy），range 50MB** | **34,641,018 B/s** | ✓✓（采用） |

注：mirror 进程死前（01:04–01:14）其临时文件实际推进到各 ~1GB（合计 ~3.5GB / 10min ≈ 5.8MB/s）——比探针单流快但仍逊于 ModelScope 直连 5 倍以上，方案 A 不变。

## 三、sha256 双锚验证（fail-closed）

- **锚 1（HF 冻结清单）**：`hub\models--Qwen--Qwen3-8B-Base\trees\49e3418fbbbca6ecbdf9608b4d22e5a407081db4.json` 的 lfs_sha256（5 分片）
- **锚 2（ModelScope API）**：`/api/v1/models/Qwen/Qwen3-8B-Base/repo/files` 的 Sha256 字段（全 12 文件）
- 两锚 12/12 一致后才发射下载；每文件下载后 size + sha256 复验；入快照后 post-move 复验
- 目标布局：`snapshots\49e3418f…\` 平铺 12 文件（HF_HUB_OFFLINE=1 下 transformers 按 refs/main → snapshots 解析，普通文件即可）+ `refs/main`（已在，指向 49e3418f…）
- ModelScope 侧 `.gitattributes` / `README.md` / `configuration.json` 为平台杂项，不入 HF 快照布局（Lead 消息口径"13 文件"实测对齐 HF trees 清单 = **12 文件**：9 新下载 + 3 已在快照复验留用）

## 四、sha256 清单（落盘实测锚）

| 文件 | size | sha256（前 16…后 8） |
|---|---|---|
| config.json | 729 | 3bd01d7ad7a2e203…49564983a |
| generation_config.json | 138 | 8c970692323e3ea0…280ebf6e8 |
| merges.txt | 1,671,853 | 8831e4f1a0444713…308a904d5 |
| model-00001-of-00005.safetensors | 3,996,250,744 | 9983f1b9ef2f60e7…d158cd0446b |
| model-00002-of-00005.safetensors | 3,993,160,032 | 9aa12339835bf7a0…58ebf7a1f |
| model-00003-of-00005.safetensors | 3,959,604,768 | c7dd5a191c8da555…7ac0186bc |
| model-00004-of-00005.safetensors | 3,187,841,392 | ad8b708792105133…d59fd9fe |
| model-00005-of-00005.safetensors | 1,244,659,840 | fbf24915d47ea030…3f2326a550 |
| model.safetensors.index.json | 32,878 | cd39d5e44c5aadfd…278b7fec2e4 |
| tokenizer.json | 7,031,645 | c0382117ea329cdf…e96ce87539 |
| tokenizer_config.json | 9,678 | 3c04ed3ca964ea2f…5046b422b5 |
| vocab.json | 2,776,833 | ca10d7e9fb3ed185…10b1440910 |

## 五、清理登记（Lead 授权）

- 8 × `.incomplete`（blobs 目录，直连 4 + mirror 4）= 10.1GB，已删
- `.cache\huggingface\xet`（CAS 缓存，2 文件 0GB）已删
- mirror 进程 PID 24108/33316 已杀（Lead 名下任务，授权处置）
- handover 勘误已代录：`reports/handover-20261014-0800.md` §二十四（含 xet 缓冲教训 + 该文件 00:45 起混入 GBK 段的编码注记）

## 六、结果（回填）

- **MS-CACHE-FILL=OK @ 01:24:09**：12 文件全落 snapshots\49e3418f…\（3 存量复验 + 9 新下载），total 15.267 GiB（16,394,660,170 bytes，与 trees 清单逐文件尺寸和精确一致），refs/main 指向复验通过
- 下载实测：01:15:49–01:24:09 = 8.3 分钟 / 16.4GB ≈ **33MB/s 均值**（峰值 56MB/s）
- 加载验证（01:24，五重）：config.json 可读（Qwen3ForCausalLM / bf16 / hidden 4096 / 36 层 / vocab 151936）✓；hub 离线解析 id → 快照路径 ✓；AutoTokenizer 加载（Qwen2Tokenizer vocab 151643）✓；5 分片 safetensors 头全过（合计 399 tensors）✓；Guard=PASS + VRAM 21.6GB 空闲 ✓
- **训练发射 @ 01:26**（job pwsh-250，log: reports\logs\m5a-dpo-r7-train.log）
