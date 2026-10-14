# P1.6 三轮拒绝校准对 · r3 release（M2b D 良单旋钮，冻结件）

- 规格：`reports/p1.6-round2-design.md` **§七（M2b 预注册，配方与预测已冻结）** · seed=20261014m2b
- 构建：`scripts/build_p16_r3.py`（纯 CPU，确定性子选 + 逐字节复制，PREFLIGHT 防覆写；
  = 二轮 `build_p16_r2.py` 同算法最小复制版，仅 D 良子选、A 原样全量）

## 内容

| 文件 | 行数 | 组成 | sha256 |
|---|---|---|---|
| `parts-d-sub.jsonl` | 336 | D 重组 = 良 96/240 子选 + 恶 240 原样 | `4c3af433046d614d6f4671790331005edc5f3c395be28e141e4ee6a26de60104` |
| `p16_benign_release.jsonl` | 2,736 | A 1,500（原样全量）+ B 480 + C 360 + E 300 + D放行 96 | `822510c11c5453db7039359c8e3899d8ead0f7a35accb3da737720f174ba080c` |
| `p16_malicious_honest.jsonl` | 2,880 | F 2,640 + D拒绝 240（一轮件逐字节副本） | `f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d` |

极性 良 2,736 : 恶 2,880 = 48.7 : 51.3；总量 5,616（一轮 5,760、二轮 5,216）；
与一轮唯一差异 = D 良 240→96（seed=20261014m2b，B/C/E/F/D恶/A 逐字节不动）。
子选算法/阈值摘要/按族 sha 对拍/全量分布见 `manifest.json`。

## 纪律

- 冻结 = `manifest.json` sha256；任何修改 ⇒ 新开版本目录，**不得原地改** ✗。
- 一轮 `data/dpo/p16-calibration/` 与二轮 `data/dpo/p16-calibration-r2/` 全链只读
  （施工前后 sha 对账一致）。
- G1 扫描交互：r2+r3 均在一轮 checker G1 字节扫描范围内 ⇒ **三轮不跑全 checker**，
  快检替代 = 一轮冻结件 sha 复验未动 + r3 行级子集断言（见 `manifest.json`
  `g1_scan_interaction`；checker 零改动 ✗）。
- 装载 = 多数据集三注册 `data/m5a-r3-run/dataset_info.json`（纯 ASCII ✗✓ GBK 教训）+
  `configs/m5a-dpo-r3.yaml`（HP 零改动）。

P16-R3-RELEASE=FROZEN
