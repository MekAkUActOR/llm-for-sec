# F5-paired 施工简报（唯一读料 —— 全部设计事实压缩于此，勿读 p1.6-round5-design.md ✗✓）

目标：data\dpo\p16-calibration-r5\ 三件 + config + dataset_info + 拼接冒烟。配方（父代理已裁决）：**r3 良恶副本逐字节 + F5-paired 新件 2,000 行**（F4 回退不带入）。

## F5-paired 规格（1,000 对 = 2,000 行）
- 配额：4 风格×250 对；轮深 2/3/4 = 75/100/75 对；en/zh = 150/100 对；pack = 112/100/38 对（default/zh/en 包）
- 最小对：同一对内两行**前缀轮逐字节相同**，仅末轮 user 的载荷短语不同（良性孪生 vs 恶意孪生）
- 2×2 完全镜像（偏好轴 = 判断正确性）：
  - 良性孪生：chosen = 真交付正文（T_del 形态）+ VERDICT answer/no-risk；rejected = 拒绝正文（T_ref）+ VERDICT refuse 误套引用（75%）或悬置 deflect（25%）
  - 恶意孪生：chosen = 拒绝正文（T_ref）+ VERDICT refuse/上报正确；rejected = 交付正文（T_del 模式级顺从）+ VERDICT answer/no-risk 错误声明
- from 标签：system/human/gpt（**r4 死因**：assistant→gpt 归一化必须内置；计数断言 2000 gpt/6000 human/4000 system——按实际生成核）
- id 前缀 p16-F5-，与一~四轮零重叠；prompt 全局唯一 2,000/2,000

## 内容库（scripts\_p16_r5_paired\，拆 4 文件防耗尽）
- content_f5_themes.py：25 主题（zh/en 名 + 各 2–3 条良性载荷短语 + 2–3 条恶意载荷短语 + 风险类型；中英按配比）
- content_f5_skeletons.py：80 骨架（4 风格×20）：dict(id/风格/轮深/前缀轮消息〔{theme} 占位〕/末轮 user 模板〔{payload} 占位〕)
- content_f5_templates.py：40 响应模板（T_del/T_ref × zh/en × 正式/口语等；含 VERDICT 行渲染）
- content_f5_gold.py：4 金样本对（zh/en × 良/恶，从设计 §二.2 语义重制，builder 单测用）

## 断言与门禁（p16r5_spec.py，import 冻结 p16cef_common 零改动）
- 行级：每对两行前缀相同断言 / 载荷翻转断言 / 镜像四格 chosen-rejected 方向断言 / from 词表断言
- G9 官方代码路径双跑（parts + 落盘字节）对 68 冻结件 12,460 needle：**零命中硬门**
- 批：8 批×250 行（pair-major 不跨批）；manifest/sha 冻结锚；progress.md 每里程碑一行

## 收尾三件
1. configs\m5a-dpo-r5.yaml = m5a-dpo-r4.yaml 复制改 3 行（dataset_dir/dataset/output_dir→r5，output checkpoints\qwen3-06b-sec-m5a-dpo-r5）；非注释 diff 恰 3 行断言
2. data\m5a-r5-run\dataset_info.json：四注册（m4 基座 28,842 + benign 2,736 + malicious 2,880 + f5paired 2,000）纯 ASCII note
3. **拼接口径冒烟**：llamafactory _get_merged_dataset(stage=rm) 四条目 concatenate = **36,458 行零丢弃**（_prompt/_response 全非空）——r4 死因路径，必须过

产物：reports\p1.6-round5-build.md 尾标 P16-R5-BUILD=DONE。env：HF_HOME=J:\Projects\llm_for_sec\.cache\huggingface、HF_HUB_OFFLINE=1、PYTHONIOENCODING=utf-8。冻结件只读、零覆写。完成后报父代理（训练门禁另派）。
