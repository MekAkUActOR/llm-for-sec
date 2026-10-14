# M3 偏好数据集 v0(sec_dpo_m3)

生成:scripts/build_dpo_m3.py(seed=20260928);原料与设计见脚本
docstring。LLaMA-Factory sharegpt ranking 格式;stage dpo 内部走
stage="rm"+ranking=true;**不默认启用**(无 config 引用,dataset_info
已注册 sec_dpo_m3)。

## 配比(总 47,948 对)

| 类 | 条数 | 占比 | 说明 |
|---|---|---|---|
| A 政策条件化对 | 14,688 | 30.6% | 同查询异包双向对称;差异化设计主体 |
| B 储备直通对 | 30,807 | 64.3% | 四源清洗(哈希复检+去重+定容) |
| B2 储备衍生拒绝对 | 1,913 | 4.0% | bt330 chosen=None 行以政策化拒绝合成 |
| C 拒绝质量对 | 300 | 0.6% | 带理由+替代 vs 生硬拒绝(双侧同 VERDICT) |
| D 校准偏好对 | 240 | 0.5% | 诚实弃权 vs 过度自信 |

**政策条件化对占比 30.6%(下限 30%)**;
zh:en = 23614:24334(49%:51%);
包分布 {"conservative": 5889, "professional": 5547, "default": 36512}。

## 储备清洗统计

载入 59,482 → 排除哈希复检(hh/cv/pku/bt-30k 上游已滤,
预期 0;bt330 上游未检、此处补剔:bt330_blocked=2)
→ 无效剔除 8 / 同侧 0
→ 去重(精确 21 / 近重 12337)
→ 定容采样 cap=32,720。

## 设计决策(供复核)

1. **hardfloor/direction/attack_dict 不入偏好对**(父指令+实测:三包同拒
   无偏好结构;attack_dict 1,860 行全拒且响应仅模板级差异);
2. **实质差异过滤兜底**(剥 VERDICT 后相似度 ≥0.88 不入,任何源);
3. **bt330 行 chosen=None**(上游仅 rejected 材料):合成政策化拒绝 chosen
   (包轮换,上限 6,000)——独立统计,可整体剔除重跑;
4. **储备定容公式** B ≤ A(1-p)/p − C − D(p=0.3),保政策对
   不被稀释;
5. 储备对响应**不加 VERDICT 行**(第三方文本不编造结构声明;类 A/C/D
   双侧自带 VERDICT);
6. 排除哈希复检逐源 replay 装配器 id 语义(hh=行号/cv=文件+行号/
   pku=目录+行号/bt=prompt 分组/bt330=n330 计数)。

## 启用(stage dpo,届时另建 config)

```yaml
stage: dpo
dataset: sec_dpo_m3        # dataset_dir: data/lf(已注册)
pref_beta: 0.1
```
