# M2 期 manifest 行对账（16 行 status='procured'）

生成：`scripts/manifest_m2_reconcile.py`（只测量，不改 manifest）

| id | 声明 tier | 盘上原始体量 | 文件数 | 首见 mtime | 文档量级 | 实际入训证据 |
|---|---|---|---|---|---|---|
| `advbench` | public | 0.12 MB | 2 | 2026-09-25 09:33 | §采购表 攻击提示基准 | ◐ 同上 |
| `beavertails` | public | 38.99 MB | 4 | 2026-09-25 10:06 | L46 330K QA + 361K 危害标注（CC-BY-NC-4.0，T2） | ◐ 用户拍板纳入 M2 第二批；是否入 m1 未在源文档逐条登记 |
| `cvalues` | public | 167.67 MB | 4 | 2026-09-25 09:50 | §2.11 L122 14.5 万对比对（prompt+双响应+人标，Apache-2.0） | ✅ 入 DPO 对（dpo_m3 类 policy/无差别攻击侧 cv 系；m1 assembler SUBCAPS cv 4,800 行） |
| `harmbench` | public | 0.20 MB | 2 | 2026-09-25 09:50 | §采购表 攻击/防御基准 | ◐ 同上 |
| `hh-rlhf-harmlessness` | public | 27.88 MB | 4 | 2026-09-25 09:49 | L15 42.5K harmlessness 对（MIT） | ◐ 同上（MIT 主力候选） |
| `maliciousinstruct` | public | 0.00 MB | 1 | 2026-09-25 09:50 | §采购表 恶意指令基准 | ◐ 同上 |
| `or-bench` | public | 11.34 MB | 3 | 2026-09-25 09:50 | §2.9 L109 or-bench-80k + hard-1k(1,320) + toxic（误拒测量） | ◐ eval 侧复用（误拒测量）；训练侧未登记 |
| `pku-saferlhf` | public | 232.68 MB | 6 | 2026-09-25 10:06 | L45 330K 偏好对（CC-BY-NC-4.0，T2） | ✅ 入 DPO 对（pku 系；m1 SUBCAPS pku 3,600 行） |
| `safemtdata` | public | 27.12 MB | 2 | 2026-09-25 09:50 | L15 600 条（MIT） | ◐ 同上 |
| `safety-prompts` | public | 68.98 MB | 2 | 2026-09-25 09:33 | §2.2 L81 100K 对 ≈30MB zh ≈12–18M zh tokens（zh 最大单源） | ✅ 入 SFT（docs/06 m1 配方 T5-attack/T12 政策问答 zh 侧） |
| `strongreject` | public | 0.07 MB | 2 | 2026-09-25 09:33 | L6 攻击强度基准（raw/m2-research） | ◐ 同上 |
| `tc260` | reference | 0.83 MB | 4 | 2026-09-25 09:50 | §2.10 L117 2,903 行 ≈0.7–1M zh tokens（ref-only，不入权重） | ⛔ ref-only（永不入权重；仅评估/分类参照） |
| `trustllm-safety` | public | 1.91 MB | 6 | 2024-01-01 23:53 | L6 TrustLLM 基准（已克隆 raw/m2-research） | ◐ 同上 |
| `wildguardmix` | public | 56.00 MB | 2 | 2026-09-25 10:29 | L47 92K prompt-response 审核对（AI2 OUFRA+门控，T3） | ✅ 登记入 m1（T1/T5 输入侧清洗源） |
| `wildjailbreak` | public | 532.66 MB | 2 | 2026-09-25 10:28 | L48 426K 对抗对话（ODC-By+门控，T3） | ✅ 登记入 m1（对抗转化源） |
| `xstest` | public | 0.04 MB | 1 | 2026-09-25 09:33 | §2.8 L108 250 prompts ≈0.3M tokens（误拒测量；输入侧种子+eval） | ◐ eval 侧复用（误拒测量）；训练侧未登记 |

**合计原始体量：1166.5 MB**（manifest 现记 est_tokens=0）

## 三个待决问题（记账口径）

1. **status**：这些源既已抓取且部分已入训——是否统一改 `ingested`（另设 `role` 字段区分 train/eval/reference）？tc260 已 ref-only，改动仅涉其余 15 行。
2. **ingested_at**：按盘上 mtime（2026-09-25 09:49–10:29）填，还是按实际入训日（m1 组装 2026-09-26 / DPO 对 2026-09-26）填？
3. **est_tokens**：填**原料层**体量（会与 SFT 产物谱系行重复计入总账，需在卡上标注「SFT 原料层」分区）还是填**实际入训用量**（更贴 M5 权重成分口径，但需逐行溯源；当前可用上界=原料层）？

证据文件：`reports/manifest-audit.json`、本表；工具：`scripts/audit_manifest.py`（可复跑）。
