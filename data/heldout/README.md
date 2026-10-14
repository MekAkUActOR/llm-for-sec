# 私有留出集（held-out）

**纪律（docs/01 §5.5、docs/02 §3）：**

1. 本目录内容**只进评估管线，永不进入训练语料**——`data/corpora/` 是训练侧，两者物理分离；
2. 版本化：子目录名即版本号（`v0.1/`）；条目只增不改，需修正时新开版本并在旧版标记 deprecated；
3. 判定以本集为准，公开基准只作参考曲线；
4. 扩容目标：**≥50 条/优先域**（ai_safety / security / privacy），v0.1 为 20/域种子批；
5. 标注分歧样本升级为边界集（`data/boundary/`，规划中），驱动政策修订循环（docs/01 §4.3）。

## 格式

JSONL，每行一个条目：

```json
{"id": "sec-r1", "domain": "security", "kind": "robustness", "language": "zh",
 "policy_pack": "default", "query": "…", "expected": {"must_refuse": true}, "group": ""}
```

- `kind ∈ {robustness, alignment, capability, calibration}`；expected 按 kind：
  robustness/alignment → `must_refuse`；capability/calibration → `correct_verdict`；
- 政策对照组：同 `group` + 同 query + 不同 `policy_pack`，expected 随包变化
  （政策条件化的直接测试，docs/01 §5.3）；
- id 前缀：`ais-` / `sec-` / `priv-`；r=攻击 a=正当 c=能力 cal=校准 p=政策对。

## 校验与统计

```powershell
python -m secfm.eval.heldout --dir data/heldout/v0.1
```

### v0.4-toolout（tool_output **同载体回归集**，2026-09-30）

`tool_output` 载体已在训练侧出现 1,224 次（`reports/carrier-census.json`）→
按 `reports/review-2026-09-30.md` §4.4，该载体的"未见载体泛化"断言作废。
`data/heldout/v0.4-toolout/` **只能用于同载体、新 phrasing 的回归读数**，
不得宣称未见载体泛化（`scripts/m25_exit_verdict.py --require-unseen-carrier`
会 fail-closed）：

```powershell
python scripts/check_toolout_heldout.py --stats-out reports/toolout-heldout-stats.json
python -m pytest tests/test_toolout_heldout.py -q
```

## 运行（对抗模型）

```powershell
python scripts/baseline_eval.py --model <底座快照> `
  --heldout data/heldout/v0.1 --out reports/heldout-baseline-<model>.json
```
