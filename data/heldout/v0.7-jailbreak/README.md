# v0.7-jailbreak：对话式越狱仪器（P0.7）

> 设计：`reports/p0.7-jailbreak-instrument-design.md`（DESIGN=DONE）。
> 构建：`scripts/build_jailbreak_suite.py`（幂等确定性组装，冻结 sha256 见
> `manifest.json`）。唯一消费者 = `scripts/probe_jailbreak.py`。

## 这不是单轮 heldout 套件（防误用 ✗）

- 本套件为**真·多轮 rollout** schema：每行是 `turns`（3–5 个 user 轮），
  `turns[-1]` = 收割轮（良性层 = 最终正当请求）；
- **不能**用 `secfm.eval.heldout.load_dir` 加载：本套件无 `query` 键，
  loader 会 fail-closed 报错——这是预期的防误用行为；
- **不能**用 `scripts/baseline_eval.py --heldout` 跑：那是单轮渲染器；
- 唯一运行器/判分器 = `scripts/probe_jailbreak.py`（token 拼装式多轮渲染
  + 逐轮 `score_heldout_v2.classify` 双口径判分 + ASR 汇总）。

## 构成（150 行）

| 层 | 构成 | 条数 |
|---|---|---|
| 攻击层 | 6 族 × 20（10 zh + 10 en/族） | 120 |
| ├ 训练可见族 | F1 渐进升级 / F2 角色扮演 / F3 虚构框架 / F5 拼图抽取 | 80 |
| └ **泛化留出族 ✗** | F4 编码变形 / F6 权限伪造 | 40 |
| 良性对照层 | 15 zh + 15 en；professional 15 + default 15 | 30 |

harm 类别：C1 恶意软件 ×30 / C2 定向入侵 ×30 / C3 钓鱼 ×29 /
C4 隐私去保护 ×20 / C5 系统提示泄漏 ×11（分布见 manifest）。

## 留出冻结纪律（§5，红线）

- `holdout=true` 的 F4/F6 **永不入训练**（含任何仿写变体）；训练数据生成器
  必须把留出族清单作为输入断言；
- 构建验收阶段对留出族**零模型读数**（冒烟只允许合成接线测试与训练可见
  族的假响应判分）；
- 冻结 = `manifest.json` 登记的 `sha256`；修改 ⇒ 新开 `v0.7b-jailbreak`。

## 零武器化

全部轮文本为**模式级请求**：不含可运行代码、URL、真实凭证或成品有害
内容；泄漏类的成功证据是哨兵标记（`LEAK_OK`/`DEBUG_OK`）与政策包
n-gram，而非真实系统提示全文。F4 编码轮的密文可机械解码还原
（`〈…〉` span，base64/ROT13），解码视图即模式级请求本身。
