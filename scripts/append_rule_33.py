# -*- coding: utf-8 -*-
"""把本轮实证得出的规则 33 追加到 docs/01-engineering-definition.md §11。

★为什么用 Python 而不是 PowerShell：docs/*.md 是无 BOM 的 UTF-8，
  PS 5.1 的 Get-Content / Set-Content 会把它读/写成乱码（本会话已两次踩到）。
  本脚本显式 encoding='utf-8' 读写，并在写后回读校验。
"""
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\docs\01-engineering-definition.md")

BLOCK = """
### 11.32 规则 33 — **偏好训练对罚不到"两侧共模"的行为**；门禁所测的每一维都必须是训练对的判别轴（2026-09-30 晚实证，M3 失败根因）

**实证**：M3 DPO 训练完成（1803/1803 步，epoch 1.0，loss 曲线健康），
但**部署格式重测**显示契约保留率从起点的 **70/168（41.7%）崩到 20/168（11.9%）**
⇒ 按预注册 MUST-B（≥63/168）**不过**。

**根因不是超参，是数据集的判别结构**（`reports/m3-rootcause-dpo-data-defects.md`）：

1. `data/lf/dpo_m3_final.jsonl` 的 **28,842 对中，100.0% 的 chosen 与 rejected 两侧都含
   字面 `VERDICT` 块**（8 个 `dpo_class` 无一例外）。
   ⇒ 该契约块是**共模量**，在偏好梯度里被约掉：**DPO 对它施加零压力**。
2. 而 `carrier_*` 四类（6,000 对 = 20.8%）**100% 长度混杂**：
   chosen 中位比 rejected 长 **3.92×–4.89×**（`carrier_inject_hollow`：
   chosen 608 字符 vs rejected 120 字符）。
   ⇒ DPO 在"**写更长的散文**"上有**强而干净**的梯度。
3. **`carrier_inject_hollow` 的 chosen 中位（608 字符）超过部署生成预算**
   （`max_new_tokens=96`，实测中文墙上限约 450–509 字符）
   ⇒ **即使完美模仿 chosen 也会在 VERDICT 块之前被截断**。
4. **`VERDICT` 在 100% 的训练 prompt 与 100% 的评估 prompt 里被明示要求**
   （"输出必须以 VERDICT 行结尾"）——**仍然没有梯度**：
   prompt 规定**不等于**偏好对可分。

**机制闭合**（与训练期标量独立自洽）：`chosen` 无趋势（r²=0.005，**因为它正是共模的那部分**）、
`rejected` 猛沉（−4.37 nats/100 步，r²=0.882，**因为它是唯一有差异的部分**）、
step 1300 出现 `acc=1.0` 而 `chosen=−0.20`（**没有绝对水平可抬，只能拉开相对差**）。

**要求**：
1. **任何门禁所测量的行为维度，必须在训练对里是判别轴**。
   发射偏好训练**之前**，必须跑一次"**判别轴审计**"：对每一个将被门禁读取的行为维度，
   报告 chosen/rejected 中该维度的**联合分布**（两侧都有 / 仅 chosen / 仅 rejected / 都无）。
   **两侧都有的比例接近 100% ⇒ 该维度不受保护，不得指望偏好训练保住它。**
2. **同时审计长度**：报告每类的 chosen/rejected 长度中位与比值。
   **任何一类的 chosen 长度中位超过部署生成预算 ⇒ 该类的训练目标不可被产生**，
   必须裁剪或改写，否则模型学到的是"被截断的模仿"。
3. **长度混杂与标记共模必须分别修复并分别登记**（D1/D2/D3），
   **不得用长度正则化的算法变体（如 R-DPO/SimPO）去掩盖数据缺陷**——
   否则两个原因混淆，无法归因（规则 22 的同源要求）。
4. **"两侧共模即无梯度"与 prompt 的明确程度无关**：
   即使契约是全系统最显式的要求，**只要 chosen 与 rejected 都遵守**，它就不受保护。
   **不得以"prompt 里写了"为由认为契约有保障。**

**推论 33.1（门禁余量）**：预注册的 MUST-B 阈值 **63/168 只比起点自身水位 70/168 低 7 条**，
而**起点自身的契约保留率仅 41.7%**（`m2calib` 亦仅 50.0%）
⇒ **该门从设立起就几乎没有余量**，属"判据无分辨率"的又一实例（规则 32）。
**要求**：设定绝对阈值时，**必须同时登记起点水位与阈值之差**；
差额过小时，该门应改为**相对起点变化的判据**，而非绝对阈值。
（本次 20/168 远低于阈值，**FAIL 无歧义**；本条针对的是下一轮定阈值。）
"""


def main() -> int:
    txt = P.read_text(encoding="utf-8")
    if "### 11.32 规则 33" in txt:
        print("已存在 §11.32，跳过（幂等）")
        return 0
    if not txt.endswith("\n"):
        txt += "\n"
    before = len(txt.splitlines())
    P.write_text(txt + BLOCK, encoding="utf-8")

    back = P.read_text(encoding="utf-8")
    after = len(back.splitlines())
    marks = [m for m in ("浠讳綍", "缈昏浆", "鐨勭粺", "鈽", "娴佺▼") if m in back]
    print(f"✅ 已追加 §11.32：{before} 行 → {after} 行（+{after-before}）")
    print(f"   双重编码特征串 = {marks if marks else '无'} ✓")
    for k in ("### 11.32 规则 33", "判别轴审计", "推论 33.1"):
        print(f"   {'✓' if k in back else '✗'} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
