# 探针集 v0.4（2026-09-30 凌晨重建）

来源隔离的固定文本样本。**永不入训练语料**（纪律同 v0.1.1/v0.3）。

v0.4 的动机来自 `docs/research/probe-contamination-audit.md`：v0.1.1/v0.3 的
**privacy 篇级 64.9% 污染**（探针取自 gdpr-info.eu 序言页，而训练语料 c0_gdpr
含完整 GDPR 含序言）与 **general_en 篇级 ~26% 重叠**（探针取自 enwiki dump，
而 C1-full 的 enwiki 回放未按探针标题排除）。两者使 privacy/general_en 的 PPL
**绝对幅度**失真（相对横向对比不受影响）。v0.4 只重建这两个域，其余六域字节
复制，以保住历史读数的纵向可比性。

## 构成

| 域 | 条数 | 文本字数 | 来源 | 与 v0.3 关系 |
|---|---|---|---|---|
| ais | 500 | — | v0.1.1 字节复制 | **字节同一**（sha256 见 `reports/probes-v04-build.json`） |
| aisafety | 144 | — | arXiv 同域互补类目 | **字节同一** |
| content | 263 | 391,299 | arXiv 同域互补类目 | **字节同一** |
| **general_en** | **300** | **3,362,393** | enwiki 池**哈希补集**重建 | 换源（v0.3: 297） |
| general_zh | 500 | 2,515,753 | zhwiki | **字节同一** |
| malware | 78 | 117,335 | arXiv 同域互补类目 | **字节同一** |
| **privacy** | **173** | **206,807** | **英国 ICO 指导页**（非 GDPR 原文） | 换源（v0.3: 173） |
| sec | 500 | 2,018,063 | GHSA/CVE 公告 | **字节同一** |

## general_en：严格互补 + 三重复核

生成器 `scripts/gen_probes_v04_general_en.py`；池 = `data/corpora/clean/c1_enwiki_gen.jsonl`。

1. **哈希补集（构造保证）**：C1-full 的 enwiki 回放按
   `md5("c1mix:" + title) % 10000 < 7400` 取 74%（`scripts/build_c1_mix.py`）。
   v0.4 取**补集** `>= 7400` → 该 26% 篇目按构造不在 C1-full 训练集内。
   池 277,025 行 → 补集 72,144 行 → 正文 ≥1200 字 66,971 篇。
2. **超采样 + 8-gram 剔除**：按 `md5("v04gen:" + title)` 序取前 600 篇，建 8-gram
   索引扫描训练侧，共享 ≥60 字符者剔除 → **37 篇命中 sft_m25**（说明 m1 的
   general 族确实含维基文本片段）、**0 篇命中 sec_c1_full 抽样 60,000 行**。
3. **成品复核（收尾断言）**：300 篇 → vs sft_m25 全量 137,670 行 **0 命中**；
   vs sec_c1_full 抽样 60,000 行 **0 命中**；训练侧 74% 标题重叠 **0**。
   字数 min/med/max = 1,240 / 5,732 / 116,544。

## privacy：非原文换源 + 单元级预筛

生成器 `scripts/gen_probes_v04_privacy.py`；来源 = `ico.org.uk` 的 UK GDPR 指导页
（改写式监管文本，非条款逐字；7 个种子入口，同域有界爬取 ≤90 页、深度 ≤3）。

1. **抓取 + 正文抽取**：stdlib `html.parser`，剥 `script/style/nav/footer/header/
   form/aside`，段落归并为 260~1400 字单元，模板/导航句（cookie、share this page、
   © 等）过滤 → 90 页得 **423 个原始单元**（v0.3 的同域文本夹带站点导航垃圾，本版不夹带）。
2. **单元级预筛（硬闸，项目既有纪律）**：423 单元建 8-gram 索引（132,303 keys），
   逐语料扫描，共享 ≥60 字符的**单元**（不是整页）即弃：

   | 训练侧语料 | 扫过文档 | 新增脏单元 |
   |---|---|---|
   | c0_gdpr（完整 GDPR，189,892 字，1 行） | 1 | **42** |
   | c0_cn-laws | 3 | 0 |
   | c0_cn-regs | 7 | 0 |
   | c2_privacy_arxiv | 2,680 | 0 |
   | c1_arxiv_full | 50,384 | 2 |
   | c1_zhwiki_sec | 1,951 | 0 |
   | sft_m25 | 137,670 | 5 |
   | **合计剔除** | | **49** |

3. **成品**：374 干净单元 → 跨页去重 → 按 md5 序取 **173 篇**（66 个不同 ICO 页面），
   字数 min/med/max = 280 / 1,286 / 1,400。

## 残留重叠（出货集全目录复核）

`scripts/check_probes_v04_vs_sft.py`（8 域 2,978 单元 × sft_m25 全量 137,670 行，
一次性记录见 `reports/probes-v04-vs-sft.json`）：

| 域 | 命中单元 | 判定 |
|---|---|---|
| **privacy（换源后）** | **0** | ✓ 干净（含 GDPR 引用的单元在预筛阶段已因 c0_gdpr 判脏剔除） |
| **general_en（互补后）** | **0** | ✓ 干净 |
| ais / content / general_zh / malware | 0 | ✓ 干净 |
| sec | 7 | 既有**已裁定类**：CISA KEV / GHSA 公告文本在探针与 m25 的 T3-risk/T4-grounding 行双侧出现（同 m1 的 `ADJUDICATED` 先例） |
| aisafety | 1 | 同上（arXiv cs.CY 类目文本双侧复用） |

**口径影响**：sec（及轻微 aisafety）的 PPL 对**所有**阶段等权（m1/m2/m25 都含同类
公共公告文本），跨模型横向比较仍有效；其绝对幅度与 privacy/general_en 一样只作
附注。中间件 `_raw_privacy_units.jsonl` 另有 27 个单元命中 sft_m25——它们是引用
GDPR 条文的 ICO 单元，预筛阶段已因 c0_gdpr 判脏（故在 sft_m25 那一轮记为"非新增"），
**不在出货集内**。

## 可比性口径（读报告时必须遵守）

- **v0.4 内部跨模型对比有效**（同探针集等权）。
- **v0.3 ↔ v0.4 的 privacy / general_en 绝对数值不可直接比较**——来源与难度都变了；
  需要纵向比较这两域时，须把历史模型在 v0.4 上**重测**（不是拿旧数对齐）。
- 其余六域字节同一 → base/c1-full/m15/m2*/m25 的纵向读数与历史**完全可比**。
- 已排期：v0.4 落地后对关键模型（至少 m15 与 m25-full）复测一次，用 v0.4 的
  privacy/general_en 数替换"受污染幅度"的解读。

## 落盘与构建记录

```
data/probes/v0.4/{ais,aisafety,content,general_en,general_zh,malware,privacy,sec}.jsonl
reports/probes-v04-build.json     # 每域行数/字数/sha256/是否与 v0.3 字节同一
reports/logs/v04-general-en.log   # general_en 构建+复核全过程
reports/logs/v04-privacy-crawl.log / v04-privacy-screen.log
data/probes/v0.4/_raw_privacy_units.jsonl  # privacy 抓取原始单元（中间件，含 src/unit）
```

组装时间：2026-09-30 凌晨（m25-full 训练窗口内，纯 CPU，未占用 GPU）。
