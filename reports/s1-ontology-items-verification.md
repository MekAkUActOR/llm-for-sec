# objective ③（S1 载体本体论）五项核实（2026-09-30 晚，父代理）

M3 训练收尾期间，逐项核对 objective ③ 的五项要求。**全部有产物，逐项附实测。**

## ① document 载体
`data/heldout/v0.6-document/`：`document.jsonl` 78 条（**52 鲁棒性 + 26 对齐**；
**46 未见机理 + 6 已训位点阳性对照**；zh 39 / en 39；security 27 / ai_safety 26 / privacy 25；
78 个唯一 id、0 重复）+ `manifest.json` + `README.md`。
**未见内容经我独立复算未被污染**（见 `reports/document-gate-overlap-adjudication.md`：
五个内容重叠计数器全 0，最长共享内容 8 字节）。
**未闭合**：校验器 `DOCUMENT-GATE-CHECK=FAIL errors=14`（已从 109,781 收敛）；
`split_site_directive` 缺干净负例。⇒ **产物可用，校验器未通过。**

## ② 结构/行为层样本 ✓ **存在**（本次实测）
`data/sft/m2.5-staging/doc_structure.jsonl` = **1,200 行 / 4.00 MB**，顶层键
`['id','task','pack','lang','messages']`。

层级构成（关键词计数，因为**该文件没有显式的 `layer` 字段**）：
| 关键词 | 出现次数 |
|---|---|
| `structure` | 2,611 |
| `结构` | 1,718 |
| `behaviour`（英式拼写） | 919 |
| `行为` | 944 |
| `behavior`（美式拼写） | **0** |

⇒ 结构层与行为层样本**都存在**；英文侧用**英式拼写** `behaviour`。
**登记的次要缺口**：无显式 `layer` 字段 ⇒ "哪些行属结构层、哪些属行为层"
**不可机读**，只能靠关键词统计。建议补 `layer: structure|behaviour` 字段
（不阻塞任何判据，但会让"结构/行为层样本"这一项从"可辩称"变成"可计数"）。

## ③ T2 机制解释族 ✓
`data/sft/m2.5-staging/t2_mechanism.jsonl` = **1,200 行 / 3.43 MB**；
另有在分布探针 `data/heldout/v0.5-topup-families/t2_mechanism.jsonl`。

## ④ T9 扩容 ✓
`data/sft/m2.5-staging/t9_phish_expand.jsonl` = **1,500 行 / 4.85 MB**（扩容后），
对照原 `t9_phishing.jsonl` = 50 行 ⇒ **30 倍扩容**。

## ⑤ manifest 结账 ✓ **PASS**
`python scripts/check_staging_manifest.py` ⇒ `STAGING-MANIFEST=PASS errors=0`
（结账记录 **14 族**；SECTION 标记块 12 个；裸 jsonl 引用 14 个）。
`check_carrier_ontology.py` ⇒ `CARRIER-ONTOLOGY-CHECK=PASS errors=0`。

## 附：staging 14 族的**真实行数**（此前用 `Get-Content -ReadCount 0 | Measure-Object`
## 统计会一律得到"1 行"——那是我自己的方法错误，正法见下）
| 族 | 行数 |
|---|---|
| `fG_t6_devign_ext.jsonl` | 12,000 |
| `fA_policy_v0x2.jsonl` | 7,776 |
| `fC_cvpku_release.jsonl` | 7,602 |
| `fB_t4ground.jsonl` | 6,720 |
| `fD_t6.jsonl` | 5,001 |
| `fE_t3t12t11.jsonl` | 4,500 |
| `t14_authinject.jsonl` | 2,500 |
| `t13_retrieval.jsonl` | 1,500 |
| `t9_phish_expand.jsonl` | 1,500 |
| `doc_structure.jsonl` | 1,200 |
| `t2_mechanism.jsonl` | 1,200 |
| `t1_injection.jsonl` | 375 |
| `t13_retrieval_longctx.jsonl` | 200 |
| `t9_phishing.jsonl` | 50 |
| **合计** | **52,124** |

**方法更正**：`Get-Content -ReadCount 0 | Measure-Object` 把整个文件作为**一个**数组对象
返回 ⇒ 永远报 1 行。正确的 CPU 安全做法是逐行计数
（`sum(1 for l in f.read_text().splitlines() if l.strip())`，见
`scripts/check_doc_structure_layer.py`）。**这是本会话我第三次在"计数方法"上出错**
（前两次：`Substring` 越界、`$_` 作用域）——**计数类断言必须用能被复核的方法**。
