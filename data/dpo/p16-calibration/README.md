# P1.6 拒绝校准对 · 最终 release（冻结件）

- 规格：`reports/p1.6-calibration-design.md`（§4 施工规格为唯一权威）· seed=20261008
- 构建：`scripts/build_p16_calibration.py`（合并器，PREFLIGHT 防覆写）·
  门禁：`scripts/check_p16_calibration.py`（G1–G12 fail-closed，报告 `reports/p1.6-gate-report.md`）

## 内容

| 文件 | 行数 | 组成 | sha256 |
|---|---|---|---|
| `p16_benign_release.jsonl` | 2,880 | A 1,500 + B 480 + C 360 + E 300 + D放行 240 | `1636ba88c2f8834cdb581ea9c147e94990f28229c3665e5559375dd669daacc1` |
| `p16_malicious_honest.jsonl` | 2,880 | F 2,640 + D拒绝 240（对话式 120 + 载体 120） | `f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d` |

极性 50:50（良 2,880 / 恶 2,880）；en:zh ≈ 60:40；全量分布与两 parts 谱系链见 `manifest.json`。

## 纪律

- 冻结 = `manifest.json` sha256；任何修改 ⇒ 新开 `data/dpo/p16b-calibration/`，**不得原地改** ✗。
- parts 中间件（`parts-abd.jsonl` / `parts-cef.jsonl`）保持原样，本目录只增不改 ✗。
- 门禁 G9 样板豁免白名单（政策包模板/VERDICT 骨架/dsh-protocol 头骨架）逐条登记于 `manifest.json`
  `gate_registration.g9_whitelist`，逐条可审计。
- CEF 多轮前缀轮 `from: assistant` 已归一为 `gpt`（house DPO / LLaMA-Factory 口径，共 1007 轮，
  登记 `normalization`）。

## 待办（发射前置）

1. `scripts/launch_audit.py`（P1.8）建成后串接 checker 退出码：无 `P16-GATE=PASS` = 拒绝发射
   （已登记 `manifest.json` `launch_audit_wiring`）。
2. 人工抽查 90 行 → `reports/p16-spotcheck.md`（§6 人工关口，状态 PENDING_HUMAN_GATE）。
3. M5 合并件 `data/m5-run/dpo_m5_calib.jsonl`（基座 28,842 + 本包 5,760）与
   `dataset_info.json` 注册 `sec_dpo_m5_calib` 属 P2.9 发射集成，不在本件职责内。
