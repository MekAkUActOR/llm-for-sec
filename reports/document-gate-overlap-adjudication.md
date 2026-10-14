# document 门禁的重叠扫描：父代理独立判定（2026-09-30 晚）

**要回答的问题**：document 门禁套件（`data/heldout/v0.6-document/`）的
"未见机理 / 未见内容"声明，是否被训练语料污染？
检查器报出的关键一条是 `raw_hits_long_content_share=17558 != 0`。

**方法**：只读复算盘上产物 `data/heldout/v0.6-document/_work/overlap-full.json`
（脚本 `scripts/probe_document_overlap.py`）。**不采信任何自述，也不依赖检查器。**

## 一、结论：**不是污染**（结论 (a)）

| 键 | 值 | 判读 |
|---|---|---|
| `rev` | **6** | ★**盘上产物已是 rev=6**；陈旧的 `rev=5` 只存在于 **manifest** 里 |
| `hits_content_vs_corpus_count` | **0** | 语料内容重叠 = 0 |
| `raw_hits_content_overlap` | **0**（len） | 同上 |
| `prose_share_hits` | **0**（len） | 散文内容共享 = 0 |
| `authored_content_hits` | **0**（len） | 自撰内容命中 = 0 |
| `short_fragment_hits` | **0**（len） | 短片段命中 = 0 |
| **`shared_content_max`** | **8 字节** | ★最长只共享 **8 字节** |
| `content_min` | 12 字节 | 内容窗口阈值 |
| `raw_hits_long_content_share` | **17558**（len） | 桶名为"long content"，**实测最长共享 8 字节** |
| `raw_hits_total` / `raw_hits_schema_region` / `raw_hits_sub_window` | 176644 / 102966 / 56120 | 结构/模式区命中，属**预期**（文档骨架共享） |

⇒ **17,558 条命中的最长共享内容只有 8 字节**，即公共词 / JSON 标点 / HTML 标签级的
**亚词片段**，而**五个真正的内容重叠计数器全为 0**。
**证据链自洽**：rev=6 已把"长共享"拆出 `prose_share_hits`（=0），
而未拆分的旧桶 `raw_hits_long_content_share` 被原样保留并被记录成 17558。

**⇒ document 门禁的"未见内容"声明不受损。** 这一点现在是**独立验证过的**，
不是套件作者的自述。

## 二、由此判定检查器的一条断言**写错了**（规则 25 的教科书案例）

`scripts/check_document_gate.py` L526：`("raw_hits_long_content_share", 0)`。
**该桶的名字与它实际测量的对象不一致**：名字说 "long content"，
实际测的是"共享窗口**命中条数**"，而这些命中的**共享长度上限只有 8 字节**。
⇒ **期望它为 0 是错的断言**，且它此前把这条报成"重叠"会把评审引向"门禁被污染"的错误结论。

正确的断言是其一（**二选一都必须登记理由**）：
1. 断言 **`shared_content_max` 不超过某个显式阈值**（阈值口径须写明）；
2. 断言**真正的内容重叠键**为 0：
   `hits_content_vs_corpus_count` / `raw_hits_content_overlap` / `prose_share_hits` /
   `authored_content_hits` / `short_fragment_hits`。

若选 1，**必须同时把该桶改名**（如 `raw_hits_shared_window_hits`），
并在 manifest 里写清"最长共享 8 字节 ⇒ 非内容重叠"。
**不得**只是把 17558 改成 17558 然后放过，**也不得**为了让检查器变绿而放宽断言。

## 三、`rev=5 != 6` 那一簇的根因 = 清单滞后（时序问题）

盘上 mtime：`document.jsonl` = **15:11:10**，`manifest.json` = **15:08:28**
⇒ **jsonl 在 manifest 写完之后又被改过**，而**重叠扫描产物本身已是 rev=6**
⇒ manifest 里记的 `rev=5`、`prose_share_hits=None`、`raw_hits_long_content_share=17558`
**全是旧值**。

处置：**从当前 rev=6 产物重新生成 manifest**（**不要**重跑 `--overlap`，盘上那份已是 rev=6，
重跑只会浪费约 20 分钟并可能引入新差异）；并把顺序固定为**先冻结产物、再生成清单**；
在检查器里加一条**具名**规则
`if jsonl.mtime > manifest.mtime → FAIL "清单滞后于产物"`——
现在报成 "sha256 不一致" 会把人引向错方向（**症状不是原因**）。

## 四、仍未闭合的内容缺口

`split_site_directive` **无对应的干净负例**。
这是**内容**问题（不是检查器问题），必须**补样本**或在 manifest 里**显式登记为已知缺口**，
**不得静默消失**。

## 五、我对本套件的当前判定

| 项 | 判定 |
|---|---|
| 78 条构成（52 鲁棒 + 26 对齐；46 未见机理 + 6 已训位点阳性对照；zh 39/en 39） | ✅ 已核 |
| 8 个声明的未见机理 vs census 盘上事实 | ✅ 一致（`train_structure_sites_live` 仅 `body-visible-text` 1000 + `html-comment-in-body` 888 非零） |
| 按产物分列的载体暴露（`soup-a050: carrier_seen=false`；`m3-dpo: claim_allowed_unseen_carrier=false`） | ✅ 符合规则 24 |
| **未见内容**（本次独立验证） | ✅ **未被污染**（五个内容重叠计数器全 0；最长共享 8 字节） |
| 检查器 | ❌ **FAIL errors=14**（其中 1 条断言写错、13 条为清单滞后；输出已从 58,384 行收敛到 104 行） |
| `split_site_directive` 干净负例 | ❌ 缺 |

⇒ **套件内容可用，校验器未通过**。在 `errors=0` 之前，
该套件**不得**被引用为"已通过门禁的证据"。
