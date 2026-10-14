# P1.6 二轮拒绝校准对 · r2 release（M2a 良性侧风格先验回调，冻结件）

- 规格：`reports/p1.6-round2-design.md`（§二 M2a 配方 / §五 施工规格）· seed=20261014
- 构建：`scripts/build_p16_r2.py`（纯 CPU，确定性子选 + 逐字节复制，PREFLIGHT 防覆写）·
  门禁 = 一轮 `scripts/check_p16_calibration.py` G1–G12 快检重跑（P16-GATE=PASS，
  先于本目录落盘）+ builder 行级子集完整性断言（fail-closed）

## 内容

| 文件 | 行数 | 组成 | sha256 |
|---|---|---|---|
| `parts-a-sub.jsonl` | 1,100 | A 子选 1,100/1,500 | `230fa5cb47e008bfbd08207c9b5a632bed417790a43a15713ad39b3b039c3507` |
| `parts-d-sub.jsonl` | 336 | D 重组 = 良 96/240 子选 + 恶 240 原样 | `b804dd4d5a7cc44e07b79355c1fa088462f5602824bac503b22edfbe355cf398` |
| `p16_benign_release.jsonl` | 2,336 | A 1,100 + B 480 + C 360 + E 300 + D放行 96 | `c55da1e8d05dcaf648ee0bbc690fae066913960bf787e6e41761641c5bc5e183` |
| `p16_malicious_honest.jsonl` | 2,880 | F 2,640 + D拒绝 240（一轮件逐字节副本） | `f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d` |

极性 良 2,336 : 恶 2,880 = 44.8 : 55.2（恶意占比 50→55.2%）；总量 5,216（一轮 5,760）；
子选算法/阈值摘要/按族 sha 对拍/全量分布见 `manifest.json`。

## 纪律

- 冻结 = `manifest.json` sha256；任何修改 ⇒ 新开版本目录，**不得原地改** ✗。
- 一轮 `data/dpo/p16-calibration/` 全链只读（施工前后六件 sha 对账一致）。
- G1 扫描交互：本目录在一轮 checker G1 字节扫描范围内 ⇒ 门禁重跑须先于本目录落盘（已照办）；
  事后重跑见 `manifest.json` `g1_scan_interaction`（checker 零改动 ✗）。
- 装载 = 多数据集三注册 `data/m5a-r2-run/dataset_info.json`（纯 ASCII ✗✓ GBK 教训）+
  `configs/m5a-dpo-r2.yaml`（HP 零改动）。

P16-R2-RELEASE=FROZEN
