# 事故：M3 后评测链在第 1 步被自己的守卫误杀（2026-09-30 晚）

**结论先行**：M3 训练**成功**（1803/1803）；**评测链在第 1 步被误杀**，
**step 0–5（全部行为门禁）被整段跳过**，step 7 在无产物的情况下产出 **PENDING** 裁定。
**测量层本身表现正确**（fail-closed，未产出假 PASS）。根因是**一条守卫违反了本项目自己的规则 19**。

---

## 一、事故经过

15:24:24 M3 训练完成（`Training completed`，`model.safetensors` 2,273.8 MB 落盘）⇒
waiter 正确检测到 GPU 作业消失并发射 `eval_m3_post.ps1` ✓ ⇒ 链在 **step 1** 调用
`eval_needlefix.ps1`，后者**在入口守卫处中止**：

```
[needlefix-eval] 显存占用 = 1437 MiB（应 < 1024）
[needlefix-eval] 检测到 1 个 python 进程 → 中止
   pid=9232
```

`m3-post-gates.log` 到此为止（198 字节）。但 `eval_m3_post.ps1` **继续往下跑**：
step 6（三族在分布观测）执行完毕并产出 `family-indistribution.json`，
step 7 产出 `topup-verdict-m3-dpo.json`（15:27:56，2,759 字节）。

## 二、三个缺陷（**不是同一个**）

### 缺陷 1（**致命**）：守卫按**进程名**判定，违反规则 19
`scripts/eval_needlefix.ps1` 原 L34：
```powershell
$other = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'")
if ($other.Count -gt 0) { ... exit 2 }
```
⇒ **只要有任何 `python.exe` 就中止**。
而被它逮到的 `pid=9232` 是 **`scripts\build_document_gate.py --overlap`**——
**一个纯 CPU 作业**（文档门禁子代理的扫描，实测 CPU 193 s、显存 0）⇒
**把 CPU 作业误判为 GPU 作业，杀掉了整条 GPU 评测链。**

**这是本项目规则 19（docs/01 §11.18「作业识别必须按命令行」）的**直接违反**。**

#### 1.1 ★为什么偏偏是这一个文件：**规则只被回填到新脚本**
我逐个查了全部 8 处 `Name='python.exe'`：

| 脚本 | 判定方式 | 合规 |
|---|---|---|
| `wait_then_post_m3.ps1` | 命令行 `llamafactory\|probe_\|baseline_eval\|score_heldout\|train ` | ✓ |
| `post_m3_safety_net.ps1` | 命令行（同上） | ✓ |
| `run_needlefix.ps1` | 命令行 `probe_\|baseline_eval\|llamafactory` | ✓ |
| `eval_m3_post.ps1` | 命令行（同上） | ✓ |
| **`eval_needlefix.ps1`** | **任意 python.exe** | ❌ **唯一违规者** |

⇒ **规则 19 被应用到了所有较新的脚本上，而最早写的那个（`eval_needlefix.ps1`）
从未被回填**。事故不是"规则没人知道"，而是"**规则没有回溯适用到既存代码**"。
**这是一类可复发的组织性缺陷，不是一次性疏忽。**

### 缺陷 2（**放大伤害**）：外层脚本在子脚本失败后**继续执行**
`eval_m3_post.ps1` 用 `$ErrorActionPreference='Continue'`，
调用 `eval_needlefix.ps1` **不检查退出码** ⇒ 子脚本 `exit 2` 之后，
外层照常执行 step 6/7。
**后果**：不是"链没跑"（那会立刻被发现），而是
**"链跑完了、还出了裁定文件，只是其中一半的输入从未被测量"**——
**这是最危险的失败形态**：产物存在、格式合法、内容是 PENDING。

### 缺陷 3（**误导排查**）：提示文本与代码不一致
L32 打印 `（应 < 1024）`，L33 实际判 `$used -gt 3072`。
**我据此一度误判"显存是中止原因"**，实际 1437 MiB 完全合规，
真因是 python 进程检查。⇒ **日志文本是排查的第一手依据，写错会把排查引向错误方向。**

### 缺陷 4（**修复守卫后才暴露，且比缺陷 1 更影响 objective ①**）：
### `probe_longctx.py` 的 **chat 口径从未成功运行过**

修好守卫、重跑链后，step 0（基线 chat needle）**立刻又失败**，全量 traceback
在 `reports/logs/nf-eval-needle-soup-a050-chat.log`：

```
File "scripts\probe_longctx.py", line 221, in chat_affixes
    from secfm.eval.promptfmt import system_for
ModuleNotFoundError: No module named 'secfm'
```

**根因**：`probe_longctx.py` 定义了 `ROOT = Path(__file__).resolve().parent.parent`（L39），
但**从未把 `ROOT` 插入 `sys.path`**。而 `sys.path.insert(0, str(ROOT))` 是**本仓库的 house style**——
`grep` 实测出现 **221 次**，覆盖几乎每个脚本与测试。
**`probe_longctx.py` 是唯一漏掉它的脚本。**

**后果（★这不是"少跑一步"，是"一个口径从未存在"）**：
只有 `--prompt-format chat` 会走 `chat_affixes()`；
`raw` 口径不导入 `secfm` ⇒ **raw 一直正常，chat 一直崩**。
而 `topup_verdict.py --needle-format chat` 需要的正是 `longctx-<tag>-chat.json`。
**证据**：`reports/` 下**不存在任何** `longctx-*-chat.json`（我逐个查过，只有 raw 的
`longctx-soup-a050.json` 等）。
⇒ **objective ① 的"部署格式渲染 probe_longctx"这一项，此前被记为已完成，实际从未产出过任何产物。**
⇒ 且因 `eval_needlefix.ps1` 在 needle 命令后**不检查 `$LASTEXITCODE`**，
该失败**每次都被静默吞掉**，链继续往下跑。

**已修**：在 `ROOT` 定义后加入
```python
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```
自证：`py_compile rc=0`；无 BOM（首 3 字节 `22 22 22` = `"""`）；
`from secfm.eval.promptfmt import system_for` 在本机 **import OK** ✓。

**★与缺陷 1 同型**：两处都是"**全局约定被普遍遵守，唯独一个较老的脚本漏掉**"。
缺陷 1 是规则 19（按命令行识别作业），缺陷 4 是 `sys.path` house style。
⇒ 这**不是一个家伙的两次疏忽，而是一类组织性缺口**，见规则 29。

## 三-b、影响评估（更正）

`longctx-*-chat.json` 的不存在，意味着**SHOULD-2（needle ≥0.75 且 ≥起点−0.10）在 chat 口径下
从未被测量过**，`topup_verdict.py --needle-format chat` 必然报"缺 needle 报告"——
**这正是本次残废裁定 5 个阻断项中的一项**。
它此前被解释为"M3 还没跑完所以没测"，**真实原因是探针脚本坏了**。
⇒ **在 chat 口径 needle 成功产出之前，任何"M3 的 SHOULD-2 通过/未通过"的陈述都是无效的。**


| 项 | 状态 |
|---|---|
| M3 训练 | ✅ 成功：1803/1803、epoch 1.0、1:24:24、末模型 2,273.8 MB |
| step 0（基线 chat needle） | ❌ **未跑** |
| step 1–5（v0.3-gen / needle / v0.2.1 / toolout / PPL） | ❌ **全部未跑** |
| step 6（三族在分布观测） | ✅ 跑了，产出 `family-indistribution.json` |
| step 7（裁定） | ⚠️ 跑了，但输入不完整 ⇒ **PENDING（无效裁定）** |

**残废裁定内容**（`topup-verdict-m3-dpo.json`）：`decision = PENDING（fail-closed）`，
5 个阻断项 = 缺未见载体判分文件 / 缺 needle 报告 / 缺 PPL 读数 general_en / general_zh /
缺 v0.4-toolout 鲁棒性读数。`must = {}`、`must_gate_fail = []`、
`must_blockers = ['缺未见载体判分文件…']`。

**★正面结论**：**fail-closed 设计与 MUST 门的 fail-closed 逻辑都生效了**——
脚本**没有**因为输入缺失而给出假 PASS，而是明确 PENDING 并列出阻断项 ✓。
若沿用修复前的 MUST-B/C（惰性），这次会输出一个**看起来完整的假裁定**。

**附带观测**（不构成判据）：三族 eval_loss
t2_mechanism 5.029→**4.7769（−0.2521）**、doc_structure 4.1268→**3.911（−0.2158）**、
t9_phish 4.6785→**4.8136（+0.1351）** ⇒ **2/3 族同向改善**，
达到探针 README 的观测规则；但它是观测，**不得**被引为 M3 通过的证据。

## 四、已实施的修复

1. **`scripts/eval_needlefix.ps1` 守卫改为按命令行识别**（与其余四个脚本一致）：
   ```powershell
   $gpuPat = 'llamafactory|probe_|baseline_eval|score_heldout|pack_consistency|eval_family_indistribution'
   $other = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
     Where-Object { $_.CommandLine -and $_.CommandLine -match $gpuPat })
   ```
   实测：在 `build_document_gate.py --overlap` 正在跑的情况下，新守卫匹配 **0** 个进程 ✓
   ⇒ **CPU 作业不再误杀 GPU 链**。
2. **修正误导性提示文本**：改为 `（WDDM 桌面基线 ~1.4 GB；阈值 3072）`，与代码一致。
3. **BOM 与语法**：`edit` 工具会剥掉 BOM（规则 12）⇒ 已补回并 parse-check：
   首 3 字节 = `EF BB BF`、`parse_errors = 0`、`FIX-PS1-BOM=PASS` ✓。
4. **新增 `scripts/recover_m3_chain.ps1`**：等残废链退出 → 等 GPU 真空闲 → **重跑整条链**。
   `eval_m3_post.ps1` 对已存在产物会跳过 ⇒ 重跑 = **补齐缺失步骤且不重复计算**（幂等）。
   ★该脚本的自身排除按**自身 + 全部祖先 PID**实现（不是只排除自身）——
   因为它的命令行里含 `eval_m3_post`，只排除自身会匹配到父壳，
   **正是我在 `reports/process-selfmatch-pitfall.md` 登记的陷阱**。

## 五、应加入的规则（草案，交 docs/01）

**规则 29（草案）——新增的安全检查/守卫规则必须**回溯**适用于既存脚本。**
任何"全局性纪律"（按命令行识别作业、BOM 要求、幂等要求）在写入 docs/01 时，
必须同时产出一份**既存脚本的合规扫描**（如本次的 8 处 `Name='python.exe'` 逐处判定），
并对不合规者**当场回填**。
理由：本次事故中规则 19 **早已存在且被四个脚本正确实现**，
唯一未回填的旧脚本恰好是链上最关键的一环，
**"知道规则"与"遵守规则"之间存在一个无人负责的缺口**。

**规则 30（草案）——编排脚本必须检查子脚本退出码，不得 `Continue` 越过失败。**
理由：本次缺陷 2 把"链没跑"（易发现）变成了
"链跑完并出裁定、但一半输入从未测量"（**极难发现**）。
编排脚本的每个 GPU 步骤后必须 `if ($LASTEXITCODE -ne 0) { 记录并中止 }`；——**"某步被跳过"必须比"链失败"更响亮，而不是更安静。**

**规则 31（草案）——日志中的阈值必须与代码中的阈值同源。**
不得出现"提示写 1024、代码判 3072"这类不一致；阈值应当以变量形式**只定义一次**并同时用于判定与打印。
