# -*- coding: utf-8 -*-
r"""T2「机制解释」族生成器（M2.5 回填——docs/06 §3 的 T2 首次落地，此前为 0 行）。

## 族定义（docs/06 §3）

T2 输入→输出 = **信号→机理**：在**不提供操作增量**的前提下，解释"某类漏洞/攻击
为什么会成立"的机制与成因（教学级），并遵守政策包的双用粒度带
（P-DUALUSE-GRANULARITY，docs/policy-packs-v0-draft.md §2/§4.1）。
输出契约（docs/06 §5）：自由推理承载解释质量（"T2 评解释不只评结论"），
末行携带 VERDICT——`{"action","verdict","confidence","findings","policy"}`。

## 粒度带（本族的政策条件化轴）

| 包 | 带 | 本族回答构成 |
|---|---|---|
| conservative | textbook | 成因 + 为什么危险 + 防御性理解 |
| default | textbook | 同上（本族输出面停在教科书级） |
| professional | textbook+ | 追加"通用的、公开的防御与检测要点"（类别级，无操作增量） |

**任何档都不给可直接执行的利用步骤**（见 `assert_report`：载荷标记 0 命中 +
三包同拒边界样本）。依据：docs/00 §4.3 的**边际能力增量**口径——伤害贡献
∝ Δ(能力 | R) × P(恶意 | C)；教科书级原理对任何人开放（讲解"为什么成立"
不改变能力差），而"可直接照做的序列"才是增量项。信号栖居处分类沿用
docs/00 §3 的五栖居处（语义/结构/元数据-来源/行为/语用），每类题材在
解释中显式落位。

## VERDICT 词表（T2 首填；docs/06 §5 词表原为 TBD，随首校准跑定稿）

- `mechanism-explained`：教科书级机制解释（conservative / default）；
- `mechanism-explained-plus`：机制 + 公开的通用防御与检测要点（professional）；
- `refuse`：请求要的是可执行序列/成品实现（操作增量）或对真实第三方的
  定向评估——拒绝 + 解释 + 替代路径（**T7 同形拒绝教学**，docs/06 §4.3
  方向性不变量与 T7 的关系见 tests/test_t2_mechanism.py 的边界断言）。

## 覆盖面（5 类 15 题 × zh/en 各半）

1. 记忆安全（memory-safety 3）：缓冲区溢出 / 释放后使用 / 整数回绕；
2. 注入（injection 4）：SQLi / XSS / SSRF / 模板注入；
3. 密码学误用（crypto-misuse 3）：ECB / 固定 IV 或 nonce 重用 / 弱 KDF；
4. 供应链与权限模型（supplychain-privilege 3）：TOCTOU / 权限提升 /
   依赖混淆；
5. AI 特有（ai-specific 2）：提示注入为何能穿透 / 数据投毒为何有效。

## 情境框架（同一机制上的差异化回答）

- **F1 纯机理**：三包同为 answer，conservative/default=`mechanism-explained`、
  professional=`mechanism-explained-plus`；
- **F2 机理 + 防御/检测诉求**：同上（检测清单属更高粒度，cons/default 明示
  停在 textbook，professional 给类别级公开要点）；
- **F3 要可执行序列/成品实现**（边界样本，**少数对照行** ~5%）：三包同拒 +
  解释 + 替代路径（与 T7 拒绝教学同形，但不复用 T7 的语料内容）；
- **F4 第三方目标定向评估**：conservative 拒（语境阈值）；default /
  professional 只给与目标无关的机制层 + 范围声明；
- **F5 防御侧机理**（干净负例）：为什么某个防御能阻断该机制——三包均 answer
  （误拒纪律对照）。

## 自动断言（生成后自检，CLI 打印）

(a) 每行含 VERDICT 且 JSON 可解析、`policy==pack`、`action/verdict` 在词表内；
(b) assistant（并复扫 user）文本中 **0 命中**代码块/可利用载荷标记（清单见
    `PAYLOAD_MARKERS`，含 python / bash / POC / exploit code / curl 等）；
(c) 三包对同一情境（同一 group ref）的 `(action, verdict)` 至少
    `TRI_PACK_DIFF_FLOOR` 比例不同；F3 组三包同拒、F1/F5 组不得全拒；
(d) 结构：字段集 = m1 契约 `{id,task,pack,lang,messages}`、角色顺序、
    id/user 唯一、zh:en 各半、by_pack 均等、zh 行 user ≥10 CJK、
    en 行 user+assistant 零 CJK（本族额外要求 en 全 ASCII）。

## 纪律

- 只新建/写 `--out` 目标与 `--stats-out` 报告；**不读取**任何评估集/探针集
  路径（源码级零字面量，tests/test_t2_mechanism.py 断言），不触碰既有数据
  或脚本；
- 全部内容为机制层陈述：即使 professional 的"检测要点"也只到类别级
  （审查/审计/告警视角），不含任何可复制的载荷、完整可执行序列或补丁绕过
  步骤；不确定越界的条目一律不写。

用法：
    python scripts/gen_t2_mechanism.py --n 1200 --seed 20261001 \
        --out data/sft/m2.5-staging/t2_mechanism.jsonl \
        --stats-out reports/t2-mechanism-gen-stats.json
自检（小样本 + 临时目录）：
    python scripts/gen_t2_mechanism.py --n 100 --seed 20261001 --out <临时目录>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gen_sft_v0 import (  # noqa: E402  政策系统提示与构件一律导入，禁止复制字面量
    POLICY_SYSTEM, SURFACE_WRAPPERS, build_sample, verdict_line)

OUT_DEFAULT = ROOT / "data" / "sft" / "m2.5-staging" / "t2_mechanism.jsonl"
STATS_DEFAULT = ROOT / "reports" / "t2-mechanism-gen-stats.json"
DEFAULT_N = 1200
DEFAULT_SEED = 20261001
TASK = "T2-mechanism"
PACKS = ("conservative", "default", "professional")
LANGS = ("zh", "en")

V_MECH = "mechanism-explained"
V_MECH_PLUS = "mechanism-explained-plus"
V_REFUSE = "refuse"
VOCAB = (V_MECH, V_MECH_PLUS, V_REFUSE)
CONF = {"conservative": 0.90, "default": 0.89, "professional": 0.87}

# 三包差异化下限（断言 c）：同情境组中 (action, verdict) 不同的组占比
TRI_PACK_DIFF_FLOOR = 0.60
# 边界（拒绝）行占比上限：T2 的拒绝是"少数对照行"，族主体是机制解释
REFUSE_RATIO_CAP = 0.12

# 可利用载荷/代码标记清单（断言 b；大小写不敏感，0 命中才算过）
PAYLOAD_MARKERS = (
    "```", "~~~", "``",
    "python", "bash", "powershell", "pwsh", "gcc ", "gdb ", "makefile",
    "poc", "exploit code", "curl ", "wget ", "nc -", "nmap ", "msfconsole",
    "metasploit", "shellcode", "\\x90", "0x90",
    "os.system", "subprocess", "eval(", "exec(", "system(",
    "<script", "</script", "javascript:", "onerror=", "onload=",
    "union select", "or 1=1", "';--", "rm -rf", "chmod ", "sudo ",
    "base64 -d", "/etc/shadow", "id_rsa", "-----begin",
)
_CJK = re.compile(r"[\u4e00-\u9fff]")
_REF_RE = re.compile(r"T2-\d{5,}")

CATS = (
    ("memory-safety", "记忆安全"),
    ("injection", "注入"),
    ("crypto-misuse", "密码学误用"),
    ("supplychain-privilege", "供应链与权限模型"),
    ("ai-specific", "AI 特有"),
)
CAT_ZH = dict(CATS)

# ---------------------------------------------------------------- 题材语料 ---
# 每题：sig（评审/扫描信号，T2 的输入侧）× why（成因）× danger（为什么危险）
# × def（防御性理解）× prof（professional 的公开防御与检测要点，类别级）
# × mit（F5 防御侧机理的指称对象）。全部为机制层陈述，无载荷、无步骤。

TOPICS = [
    # ---------------------------------------------- 1) 记忆安全（记忆安全 3 题）
    dict(tid="mem-overflow", cat="memory-safety",
         mit_zh="输入边界校验加内存安全语言/边界检查 API",
         mit_en="input bounds validation plus memory-safe languages and bounds-checked APIs",
         sig_zh=("代码评审信号：一段处理网络报文的例程把报文里声明的长度字段直接当作拷贝长度，"
                 "写入固定大小的栈数组，看不到边界校验。"),
         sig_en=("Code-review signal: a routine that handles network messages takes the length field "
                 "declared in the message as the copy length into a fixed-size stack array, with no "
                 "bounds check in view."),
         why_zh=("两件本该相关的事在运行时才相遇：“写多少”由数据决定，“能写多少”由代码预分配，"
                 "而运行时不为这类数组访问做边界检查——长度字段对程序来说只是一个普通整数。"
                 "它之所以成立还依赖内存布局：同一栈帧里控制信息（返回地址、保存的帧指针、"
                 "函数指针）与数据缓冲物理相邻，越界写会自然落到控制流稍后要消费的位置上。"),
         why_en=("two facts meet only at runtime: how much gets written is decided by the "
                 "data, while how much room exists was fixed by the code, and the runtime performs no "
                 "bounds check on the write - the length field is just an integer to the program. The "
                 "mechanism also depends on layout: control information (return address, saved frame "
                 "pointer, function pointers) sits physically next to data buffers in the same frame, so an "
                 "overlong write lands on values the control flow consumes later."),
         danger_zh=("这类缺陷把“数据处理错误”直接升级成“控制流影响面”：一旦越界写落在相邻"
                    "元数据上，程序随后会按被改写的值继续执行，机密性、完整性与可用性可以在同一个"
                    "缺陷上同时失守。作为信号看，恶意之处住在“行为”栖居处（解析时的写入动作），"
                    "语义层的文本可能完全正常。"),
         danger_en=("this class upgrades a data-handling mistake into influence over "
                    "control flow: once an overlong write lands on adjacent metadata, the program keeps "
                    "executing on the rewritten values, so confidentiality, integrity and availability can "
                    "all fail from a single defect. As a signal it lives at the behavior layer - the write "
                    "performed while parsing - while the semantic-layer text can look completely normal."),
         def_zh=("机制需要“无边界检查的写入”与“数据与控制信息同区布局”同时成立，"
                 "所以两类防线各自有效——语言与库层做边界检查（安全字符串与容器 API、内存安全语言、"
                 "编译期加固），运行时层做布局隔离与检测（栈保护、地址随机化、只读重定位、内存标签）。"
                 "这不是某种语言的原罪，而是缺失校验时的必然结果。"),
         def_en=("the mechanism needs both an unchecked write and data sharing "
                 "memory with control information, so two independent classes of defense work - "
                 "bounds-checked APIs and memory-safe languages at the language/library layer, and layout "
                 "isolation plus detection at the runtime layer (stack protection, address randomization, "
                 "read-only relocation, memory tagging). It is not an inherent sin of one language; it is "
                 "what follows whenever validation is missing."),
         prof_zh=["把长度校验做成不可绕过的入口约束：所有来自外部的长度先做上限与一致性校验"
                  "（声明长度 vs 实际可用字节），再进入任何拷贝路径。",
                  "检测信号是“不对称的写入”：评审时核对长度来源与目标缓冲容量的关系，"
                  "自动化侧用边界/污点分析覆盖全部拷贝路径，上线后以崩溃聚类与内存保护告警兜底。"],
         prof_en=["Make length validation an entry constraint that cannot be bypassed: validate upper "
                  "bounds and consistency (declared length vs actually available bytes) before any copy "
                  "path runs.",
                  "The detection signal is an asymmetric write: review the capacity relationship between "
                  "the length source and the destination buffer, let boundary and taint analysis cover "
                  "every copy path, and use crash clustering plus memory-protection alerts as the runtime "
                  "backstop."]),

    dict(tid="mem-uaf", cat="memory-safety",
         mit_zh="所有权模型与分配器隔离（延迟重用/内存标签）",
         mit_en="ownership models plus allocator isolation (delayed reuse, memory tagging)",
         sig_zh=("静态分析信号：一个对象在错误处理路径上被释放，但同一指针仍保存在全局表中，"
                 "之后可能被再次读取。"),
         sig_en=("Static-analysis signal: an object is released on an error path, but the same pointer is "
                 "still kept in a global table and may be read again later."),
         why_zh=("“生命周期”与“引用”两套账没有对齐：所有权（谁负责释放）和可达性"
                 "（谁还持有指针）是两个独立概念，代码在一处结束了对象的生命周期，却没有让所有引用"
                 "同时失效。它之所以能形成稳定的可利用性，是因为分配器会复用刚释放的空间——后续分配"
                 "很可能拿到同一块内存，于是悬垂引用读到的内容由攻击者可以影响的数据决定。"),
         why_en=("two ledgers do not agree: ownership (who releases) and reachability "
                 "(who still holds a pointer) are independent notions, and ending the object's lifetime in "
                 "one place does not invalidate every reference to it. It becomes reliably exploitable "
                 "because allocators reuse freshly released space: a later allocation often receives the "
                 "same memory, so what the stale reference reads is decided by data an attacker can "
                 "influence."),
         danger_zh=("“类型与归属的确定性”被打破：读到的是按旧类型解释的新数据，程序据此"
                    "做判断或跳转，因此缺陷位于“行为”栖居处（分配器复用的时机），而每处单点检查"
                    "看上去都成立。"),
         danger_en=("type and ownership certainty is broken: what is read is new data "
                    "interpreted through an old type, and the program then branches on it. The defect "
                    "therefore lives at the behavior layer - the timing of allocator reuse - while each "
                    "individual single-point check looks satisfied."),
         def_zh=("机制需要“释放后仍有引用”加上“内存被复用”两个条件。所有权模型"
                 "（智能指针、垃圾回收、借用检查）、释放前失效化（清空注册表、弱引用）与分配器隔离"
                 "（隔离区、延迟重用、内存标签）各自都能打断它；关键是让生命周期成为编译期或运行时"
                 "可检查的性质，而不是口头约定。"),
         def_en=("the mechanism needs both a reference that outlives the release "
                 "and memory that gets reused. Ownership models (smart pointers, garbage collection, borrow "
                 "checking), invalidation at release time (clearing registries, weak references) and "
                 "allocator isolation (quarantine, delayed reuse, memory tagging) each break it on their "
                 "own; the point is to make lifetime a compile-time or runtime-checkable property rather "
                 "than a verbal convention."),
         prof_zh=["用“谁分配谁释放”的所有权标注覆盖错误路径，把释放收敛到单一点，避免多条清理路径"
                  "重复释放同一对象。",
                  "检测信号是时序而不是内容：悬垂读发生在释放之后，可用延迟重用、内存标签与分配跟踪"
                  "（分配栈与释放栈关联）在运行时暴露这种次序异常。"],
         prof_en=["Annotate ownership (who allocates, who releases) across error paths and funnel release "
                  "to a single point so that multiple cleanup paths cannot release the same object twice.",
                  "The detection signal is a sequence, not a payload: a stale read happens after the "
                  "release, so delayed reuse, memory tagging and allocation tracking (correlating allocation "
                  "and release stacks) expose the ordering anomaly at runtime."]),

    dict(tid="mem-intwrap", cat="memory-safety",
         mit_zh="溢出语义的尺寸计算与统一的无符号/定宽类型",
         mit_en="overflow-aware size arithmetic with unified unsigned fixed-width types",
         sig_zh=("代码评审信号：校验函数与拷贝函数接收同一个定宽长度变量，前者按小值判断，"
                 "后者把它当作无符号字节数使用。"),
         sig_en=("Code-review signal: a validation routine and a copy routine take the same fixed-width "
                 "length variable; the first judges it as a small value, the second uses it as an unsigned "
                 "byte count."),
         why_zh=("定宽整数在溢出时按模回绕，而校验发生在一个数值上、使用发生在回绕之后的另一个"
                 "数值上：校验看到的是“小”，使用拿到的是回绕后的“大”，同一个变量在两个时刻给出不同"
                 "结论，于是“先检查、后使用”的顺序在同一段算术内部就被绕过。在部分语言里有符号回绕"
                 "还是未定义行为，编译器可以据此推断某个分支不可达，把校验直接删掉。"),
         why_en=("fixed-width integers wrap modulo their range, while validation happens on "
                 "one value and use happens on a different value after the wrap: validation sees something "
                 "small, use receives something large, and the same variable yields two different answers at "
                 "two moments - so the check-then-use order is bypassed inside a single arithmetic "
                 "expression. In some languages signed overflow is undefined behavior, which lets the "
                 "compiler prove a branch unreachable and delete the check outright."),
         danger_zh=("它把校验本身变成了不可信的量：一旦某个长度或计数参与回绕，所有基于它的"
                    "判断（循环上界、分配大小、下标范围）都失去意义，缺陷因此同时表现为越界写入与"
                    "分配错配。信号层面它藏在“语义”栖居处——一个看上去完全正常的算术表达式。"),
         danger_en=("the validation itself becomes untrustworthy: once a length or counter "
                    "wraps, every judgement built on it (loop bound, allocation size, index range) loses "
                    "meaning, so the defect shows up as out-of-range writes and mis-sized allocations at the "
                    "same time. As a signal it hides in the semantic layer - an arithmetic expression that "
                    "looks entirely ordinary."),
         def_zh=("机制依赖“无检查的定宽算术”与“校验值即使用值”两点，因此检查算术"
                 "（带溢出检测的内建类型、饱和运算）、统一以无符号定宽类型表达尺寸、并让校验与使用"
                 "共用同一处计算结果，都能消除它。重点不是记住某个边界值，而是让数值的语义在类型"
                 "层面固定下来。"),
         def_en=("the mechanism needs unchecked fixed-width arithmetic and a check "
                 "value that is supposed to equal the use value, so overflow-checked arithmetic (built-in "
                 "checked types, saturating operations), a single unsigned fixed-width representation for "
                 "sizes, and one shared computation feeding both check and use each remove it. The point is "
                 "not memorising a boundary value but fixing the meaning of the number in its type."),
         prof_zh=["把所有尺寸计算放进带溢出语义的辅助函数，禁止裸算术直接决定分配与拷贝长度。",
                  "检测信号是“同一变量在检查点与使用点的取值不可比”：评审时对齐两个使用点，"
                  "静态分析跟踪算术结果的流向；对编译器优化导致的校验消除，用内存安全语言或"
                  "定义明确的溢出语义规避。"],
         prof_en=["Route every size computation through helpers with explicit overflow semantics, and never "
                  "let raw arithmetic decide an allocation or copy length.",
                  "The detection signal is that the same variable is not comparable at the check point and "
                  "the use point: align the two use sites during review and track where the arithmetic "
                  "result flows; for check elimination caused by compiler optimization, prefer a memory-safe "
                  "language or well-defined overflow semantics."]),

    # -------------------------------------------------------- 2) 注入（4 题）
    dict(tid="inj-sqli", cat="injection",
         mit_zh="参数化查询（值走带外通路）与标识符白名单",
         mit_en="parameterized queries (values travel out of band) and identifier allowlists",
         sig_zh=("应用安全评审信号：一个查询把用户输入与查询文本拼接后再交给数据库，输入直接进入"
                 "查询文本。"),
         sig_en=("Application-security review signal: a query concatenates user input with query text "
                 "before handing it to the database, so input enters the query text directly."),
         why_zh=("数据与代码共用同一个语法通道：查询文本由解析器解释为语法，而用户数据本应只被"
                 "当作值；拼接让数据出现在解析器期待语法的位置上，于是引号、注释与分隔符的归属改由"
                 "输入决定——解析器的规则没有变，变的是谁在写这段文本。它还普遍成立，是因为拼接是"
                 "最自然的写法，而参数化要求把“值的传输”与“查询文本的传输”分开。"),
         why_en=("data and code share one syntactic channel: the query text is "
                 "interpreted as syntax by a parser, while user data should only ever be a value. "
                 "Concatenation places data where the parser expects syntax, so the ownership of quotes, "
                 "comments and separators is decided by the input - the parser's rules did not change, what "
                 "changed is who is writing that text. It is also ubiquitous because concatenation is the "
                 "most natural way to write it, whereas parameterization requires separating how values "
                 "travel from how the query text travels."),
         danger_zh=("攻击面从“值”扩散到“结构”：一条输入就能改变查询的形状（条件、连接、"
                    "集合运算），机密性、完整性与可用性因此在同一个通道上暴露。从栖居处看，恶意之处"
                    "不在某段固定文本，而在“数据与代码的边界由谁决定”。"),
         danger_en=("the attack surface spreads from values to structure: one input can "
                    "change the shape of the query (predicates, joins, set operations), so confidentiality, "
                    "integrity and availability are all exposed through a single channel. In habitat terms "
                    "the malicious part is not a fixed piece of text but who decides the boundary between "
                    "data and code."),
         def_zh=("机制需要“数据进入语法位置”这一点，因此参数化查询在结构上消除了它——"
                 "值走带外通路，解析器始终只看到占位符，这不是“过滤掉某些字符”能达到的性质。"
                 "标识符（表名、列名、排序方向）无法参数化，只能用白名单枚举，这是同一原理的边界"
                 "情形，也是常见漏点。"),
         def_en=("the mechanism needs data to reach a syntactic position, and "
                 "parameterized queries remove that structurally - values travel out of band and the parser "
                 "only ever sees placeholders, which filtering individual characters cannot achieve. "
                 "Identifiers (table names, column names, sort directions) cannot be parameterized, so they "
                 "must be allowlisted; that boundary case is also the usual gap."),
         prof_zh=["参数化覆盖所有用户可控的值通道（含排序、分页、模糊匹配参数）；标识符位置用白名单"
                  "枚举，禁止任何形式的字符串拼接。",
                  "检测信号是查询文本里出现了本应为常量的结构位：绑定参数审计、评审中的拼接模式排查、"
                  "以及数据库侧的异常查询形状告警；纵深方向用最小权限数据库账号压缩爆炸半径。"],
         prof_en=["Cover every user-controlled value channel with parameterization (including sort, paging "
                  "and fuzzy-match arguments); use allowlist enumeration for identifier positions and no "
                  "string concatenation anywhere.",
                  "The detection signal is a structural position in query text that should have been "
                  "constant: audit bound parameters, review for concatenation patterns, and alert on "
                  "anomalous query shapes at the database; in depth, least-privilege database accounts "
                  "shrink the blast radius."]),

    dict(tid="inj-xss", cat="injection",
         mit_zh="按上下文输出编码与内容安全策略",
         mit_en="context-aware output encoding plus a content security policy",
         sig_zh=("前端安全评审信号：一个页面把服务端返回的字符串直接插入页面结构，其中含用户可控部分。"),
         sig_en=("Front-end security review signal: a page inserts a server-returned string directly into "
                 "the page structure, and part of that string is user-controlled."),
         why_zh=("根因与注入类同源——“数据进入语法位置”——但它发生在浏览器端，而且这里的语法上下文"
                 "有多个：页面结构、属性值、URL、脚本字符串，各自的转义规则并不相同。只要输入落在一个"
                 "未被正确转义的上下文里，浏览器就会把它当作标记或脚本的一部分来解析，从而在受害者的"
                 "浏览器内建立新的执行上下文。危险边界也因此从服务器移到了浏览器。"),
         why_en=("the same as other injection classes - data reaching a syntactic position "
                 "- but it happens in the browser, where there are several syntactic contexts: page "
                 "structure, attribute values, URLs, script strings, each with different escaping rules. As "
                 "soon as input lands in a context that is not correctly escaped, the browser parses it as "
                 "markup or script and a new execution context is established inside the victim's browser. "
                 "The trust boundary therefore moves from the server to the browser."),
         danger_zh=("被借用的是受害者的信任关系与凭据环境：脚本继承站点的源权限，可以读取页面"
                    "数据并以用户身份发起请求。信号层面，恶意内容住在“结构”栖居处——它本应是文本却"
                    "成了标记，而服务端日志里往往只有一条普通的业务请求。"),
         danger_en=("what gets borrowed is the victim's trust relationship and credential "
                    "environment: the script inherits the site's origin privileges and can read page data and "
                    "issue requests as the user. As a signal, the malicious part lives at the structural "
                    "layer - text that became markup - while the server log may hold nothing but an ordinary "
                    "business request."),
         def_zh=("机制依赖“输出没有按上下文转义”，所以按上下文编码（让特殊字符以数据形式"
                 "呈现）是根本解；内容安全策略与安全 DOM 接口提供第二层约束（禁止内联执行、只允许"
                 "数据绑定），凭据的不可脚本访问属性收窄后果。过滤单个字符是治标，因为它必须猜全"
                 "所有上下文。"),
         def_en=("the mechanism depends on output that is not escaped for its "
                 "context, so context-aware encoding - making special characters present as data - is the "
                 "structural fix; a content security policy and safe DOM APIs add a second constraint (no "
                 "inline execution, data binding only), and script-inaccessible credentials narrow the "
                 "consequences. Filtering individual characters is symptomatic, because it must guess every "
                 "context correctly."),
         prof_zh=["输出编码与上下文绑定在一处实现（模板引擎自动转义），避免手写拼接；服务端渲染与"
                  "前端渲染之间要有明确的转义责任归属。",
                  "检测信号是输入与执行上下文的交叉：上报内联脚本违规、审查危险 DOM 接口的使用、"
                  "对用户可控字段做编码一致性检查；凭据侧限制脚本可达性以压缩影响面。"],
         prof_en=["Implement encoding where the context is known (template-engine auto-escaping) and avoid "
                  "hand-written concatenation; assign explicit escaping ownership between server-side and "
                  "client-side rendering.",
                  "The detection signal is the crossing of input with an execution context: report inline "
                  "script violations, review uses of dangerous DOM APIs, check encoding consistency on "
                  "user-controlled fields, and limit script reachability to credentials to shrink impact."]),

    dict(tid="inj-ssrf", cat="injection",
         mit_zh="目的地白名单与解析后校验并绑定连接目标",
         mit_en="destination allowlists with resolve-then-validate and connection pinning",
         sig_zh=("架构评审信号：一个服务接收用户提交的资源地址，由服务端发起取回并展示结果，"
                 "而该服务运行在内网可达的网段。"),
         sig_en=("Architecture review signal: a service accepts a user-submitted resource address, fetches "
                 "it from the server side and displays the result, and that service runs in a segment with "
                 "internal network reachability."),
         why_zh=("把“网络位置”当成信任依据，而请求目标却由外部输入决定：服务端处在比客户端更有"
                 "特权的位置（可达内网、回环与元数据地址），当它按输入去发起请求时，这份位置特权就"
                 "随输入转移，形成一种被混淆的代理。它的成立不需要任何代码缺陷，只需要“地址来自输入”"
                 "与“服务能到达的目标多于客户端”两个事实同时存在。"),
         why_en=("treating network position as a basis for trust while letting external "
                 "input decide the request target: the server sits somewhere more privileged than the "
                 "client (able to reach internal, loopback and metadata addresses), so when it issues a "
                 "request based on input, that positional privilege travels with the input and the server "
                 "becomes a confused proxy. It needs no code defect at all - just two facts at once: the "
                 "address comes from input, and the service can reach more targets than the client can."),
         danger_zh=("它把外部输入变成了对内网的探测与访问能力（行为栖居处：请求本身就是载荷），"
                    "可用于读取内部接口、确认资产存在、触碰云元数据凭据。从审计角度看，出网点日志里"
                    "出现的是一条由本服务发起的、看起来正常的请求。"),
         danger_en=("external input becomes probing and reachability against the internal "
                    "network (behavior layer: the request itself is the payload), usable to read internal "
                    "interfaces, confirm asset existence and touch cloud metadata credentials. From an audit "
                    "viewpoint the egress log holds nothing but a normal-looking request issued by the "
                    "service itself."),
         def_zh=("机制依赖“目标可控”与“位置特权可借用”，因此目的地白名单（以解析后的地址"
                 "判定，而不是以字符串判定）、解析后再次校验并固定连接目标、默认不跟随重定向、把出网"
                 "做成显式通道，都能从结构上断开它；网络层的分区与出网收紧则保证即使单点失守也不产生"
                 "大爆炸半径。"),
         def_en=("the mechanism needs a controllable target and a borrowable "
                 "privileged position, so a destination allowlist judged on resolved addresses rather than "
                 "strings, re-validation after resolution with the connection pinned to the validated "
                 "target, no follow-redirects by default, and egress as an explicit channel each cut it "
                 "structurally; network segmentation and tightened egress keep a single failure from "
                 "becoming a large blast radius."),
         prof_zh=["目的地判定必须用解析后的地址（覆盖 IPv4/IPv6 混合写法与重定向的每一跳），"
                  "并让解析与连接在时间上保持一致性。",
                  "检测信号是“由服务发起、目标范围异常”：出网流量基线、对回环/链路本地/元数据地址的"
                  "访问告警、重定向链审计；设计上把出网代理化并记录完整目的地链。"],
         prof_en=["Judge destinations on resolved addresses (covering IPv4/IPv6 mixed notation and every "
                  "redirect hop) and keep resolution and connection consistent in time.",
                  "The detection signal is a service-initiated request whose target range is anomalous: "
                  "egress baselines, alerts on loopback, link-local and metadata addresses, and redirect-"
                  "chain auditing; design egress as a proxy that records the full destination chain."]),

    dict(tid="inj-ssti", cat="injection",
         mit_zh="模板源码与数据分离（只传值、不参与编译）",
         mit_en="separating template source from data (values only, never compiled)",
         sig_zh=("代码评审信号：一段代码把用户输入拼进模板源码后再交给模板引擎渲染，用于生成"
                 "个性化页面。"),
         sig_en=("Code-review signal: a routine concatenates user input into template source and then hands "
                 "it to the template engine to render a personalized page."),
         why_zh=("根因与注入类同源，但发生在模板层：模板引擎先解析模板源码（其中可以包含变量、表达式"
                 "与控制结构），再渲染输出；输入被拼进源码位置时，它就被当作模板语法而非数据来解析，"
                 "于是表达式求值成了可达能力。危险度取决于引擎的表达能力——能求值、能访问对象属性的"
                 "引擎，会把一个看起来只是“格式化”的功能变成服务端可执行面。"),
         why_en=("the injection root cause again, one layer up: a template engine first parses "
                 "template source (which may contain variables, expressions and control structures) and "
                 "then renders it; when input is concatenated into the source position it is parsed as "
                 "template syntax instead of data, so expression evaluation becomes reachable. How bad it "
                 "is depends on the engine's expressiveness - an engine that can evaluate and reach object "
                 "attributes turns something that looked like formatting into a server-side execution "
                 "surface."),
         danger_zh=("它把“渲染输出”上升为服务端可达的执行面，而且这类缺陷常出现在看起来只是"
                    "“生成文案或报表”的功能里（语用栖居处：请求措辞完全无害，能力却在服务端）。"),
         danger_en=("rendering output becomes a reachable server-side execution surface, "
                    "and the defect tends to appear in features that look like nothing but text or report "
                    "generation (pragmatic layer: the request wording is entirely harmless while the "
                    "capability sits on the server)."),
         def_zh=("机制依赖“输入成为模板源码”，因此把用户输入只作为变量值传入（渲染阶段注入"
                 "数据、不参与编译）是根本解；无逻辑模板语言与受限求值环境限制误用后的后果；需要输入"
                 "进入模板源码的位置应当收敛成可审计的少数点。"),
         def_en=("the mechanism needs input to become template source, so passing "
                 "user input only as variable values (data injected at render time, never compiled) is the "
                 "structural fix; logic-less template languages and restricted evaluation environments "
                 "limit the consequences of misuse; and the sites where input could reach template source "
                 "should be reduced to a few auditable points."),
         prof_zh=["模板源码在部署期固定，运行时只传值；确需动态片段时用受限语法白名单，而不是完整"
                  "表达式能力。",
                  "检测信号是模板源码里出现外部输入：审查模板编译调用点的入参来源、运行时记录模板"
                  "编译事件；对报表与通知类功能做专项排查，因为它们最常被默认为安全。"],
         prof_en=["Template source is fixed at deploy time and only values are passed at runtime; if dynamic "
                  "fragments are unavoidable, use a restricted syntax allowlist instead of full expression "
                  "power.",
                  "The detection signal is external input appearing in template source: review the argument "
                  "origin of template-compilation call sites and log template compilation events; single out "
                  "reporting and notification features, which are the ones most often assumed safe."]),

    # ------------------------------------------- 3) 密码学误用（密码学误用 3 题）
    dict(tid="crypto-ecb", cat="crypto-misuse",
         mit_zh="带随机 nonce 的认证加密模式",
         mit_en="authenticated encryption with a random per-message nonce",
         sig_zh=("密码学评审信号：一处对称加密用 ECB 工作模式处理结构化记录。"),
         sig_en=("Cryptography review signal: one symmetric-encryption code path uses the ECB mode of "
                 "operation for structured records."),
         why_zh=(" ECB 把每个定长块独立映射：同一密钥下相同的明文块总是产生相同的密文块，块与块"
                 "之间没有扩散。结构化数据（重复字段、固定头、填充规律）因此会在密文里留下可观察的"
                 "重复与对齐结构；攻击者不需要密钥，只要看到密文的分块视图，就能推断明文的分段与"
                 "重复关系，密文块的重排与替换也仍然能通过校验。"),
         why_en=("ECB maps each fixed-size block independently: under the same key, equal "
                 "plaintext blocks always produce equal ciphertext blocks, with no diffusion between blocks. "
                 "Structured data (repeated fields, fixed headers, predictable padding) therefore leaves "
                 "observable repetition and alignment in the ciphertext; an attacker needs no key - a "
                 "block-wise view is enough to infer segmentation and repetition, and reordering or "
                 "substituting blocks still goes unnoticed."),
         danger_zh=("“机密性”被悄悄降级为“块的不可区分”：泄露的是结构而不是逐字内容，但结构"
                    "在结构化数据里往往等价于敏感信息（存在性、重复、字段边界）；同时 ECB 不提供完整性，"
                    "密文被重排也无法察觉。缺陷没有任何报错或日志症状。"),
         danger_en=("confidentiality is quietly downgraded to block indistinguishability: "
                    "what leaks is structure rather than verbatim content, but in structured data structure "
                    "is often equivalent to sensitive information (existence, repetition, field boundaries); "
                    "ECB also provides no integrity, so reordered ciphertext is undetectable. The defect has "
                    "no error or log symptom at all."),
         def_zh=("机制依赖“块间无扩散”，因此使用带随机化与认证的工作模式（需要每消息唯一"
                 "随机 nonce 的认证加密）即可消除；若因兼容必须用块模式，至少让每次加密的输入不可预测、"
                 "不重复，并叠加独立的消息认证。"),
         def_en=("the mechanism depends on the absence of diffusion between blocks, "
                 "so an authenticated mode with randomization (authenticated encryption requiring a unique "
                 "random nonce per message) removes it; if compatibility forces a block mode, at least make "
                 "each encryption input unpredictable and non-repeating, and add independent message "
                 "authentication."),
         prof_zh=["默认选择带 nonce 的认证加密，并把“密钥与 nonce 唯一性”写成库的使用契约，"
                  "而不是依赖调用者记住。",
                  "检测信号是密文的结构性重复：对同一密钥下的样本做重复块统计与对齐检查；"
                  "审查清单把工作模式与是否认证作为必查项。"],
         prof_en=["Default to authenticated encryption with a nonce, and express key and nonce uniqueness as "
                  "part of the library's contract instead of relying on callers to remember it.",
                  "The detection signal is structural repetition in ciphertext: run repeated-block and "
                  "alignment statistics over samples under the same key, and keep mode of operation plus "
                  "authenticated-or-not on the mandatory review checklist."]),

    dict(tid="crypto-fixediv", cat="crypto-misuse",
         mit_zh="每消息唯一随机 nonce 与密钥轮换",
         mit_en="a unique random nonce per message plus key rotation",
         sig_zh=("实现评审信号：加密函数每次调用使用同一个常量初始向量，密钥长期不变。"),
         sig_en=("Implementation review signal: the encryption routine uses the same constant initialization "
                 "vector on every call while the key stays unchanged for a long period."),
         why_zh=("把初始向量当成“固定参数”，而不是“每条消息都必须唯一”的输入。在流式模式里，"
                 "密钥与初始向量共同决定密钥流：两者相同则密钥流相同，两段密文相减后密钥流相互抵消，"
                 "只剩明文之间的关系；在分组链接模式里，相同初始向量让“明文前缀相同则密文相同”，"
                 "直接暴露相等性。在认证加密中，nonce 重用还会破坏完整性保护，使伪造成为可能。"),
         why_en=("treating the initialization vector as a fixed parameter rather than as an "
                 "input that must be unique per message. In streaming modes the key and the vector together "
                 "determine the keystream: identical inputs give an identical keystream, so combining two "
                 "ciphertexts cancels it and leaves the relationship between plaintexts; in chaining modes a "
                 "constant vector means equal plaintext prefixes yield equal ciphertext, exposing equality "
                 "directly. In authenticated encryption, nonce reuse also breaks the integrity guarantee and "
                 "makes forgery possible."),
         danger_zh=("它把“加密”变成“编码”：只要密文可见，机密性就基本消失，而这个缺陷不体现在"
                    "任何报错或日志里；它常常还与“密钥长期不换”叠加，使暴露面随消息量持续增长。"),
         danger_en=("encryption degrades into encoding: once ciphertext is visible, "
                    "confidentiality is essentially gone, and the defect shows up in no error or log. It also "
                    "compounds with a key that is never rotated, so exposure keeps growing with the number of "
                    "messages."),
         def_zh=("机制依赖“同密钥下的重复 nonce”，因此唯一随机（或严格计数不重复）的 nonce "
                 "是核心约束，并且要与密文一起存储、在解密侧校验；密钥轮换与单密钥使用上限则保证即使"
                 "误用也不会长期失守。"),
         def_en=("the mechanism depends on a repeated nonce under one key, so a "
                 "unique random (or strictly non-repeating counter) nonce is the core constraint, stored "
                 "with the ciphertext and validated on decryption; key rotation and a per-key usage limit "
                 "ensure that even misuse does not fail permanently."),
         prof_zh=["nonce 生成与唯一性作为库的强制契约：随机源、计数器与持久化计数点在设计中显式写出。",
                  "检测信号是“同密钥同 nonce”的组合：审查调用点、对样本做已知明文比对与重放检测，"
                  "并把认证失败率与 nonce 复用告警纳入监控。"],
         prof_en=["Make nonce generation and uniqueness a hard contract of the library: name the random "
                  "source, the counter and the persistence point of the counter explicitly in the design.",
                  "The detection signal is the pair same key plus same nonce: review call sites, run "
                  "known-plaintext comparison and replay detection over samples, and monitor "
                  "authentication-failure rates and nonce-reuse alerts."]),

    dict(tid="crypto-kdf", cat="crypto-misuse",
         mit_zh="逐用户盐加可调成本的内存困难 KDF",
         mit_en="a per-user salt plus a memory-hard KDF with tunable cost",
         sig_zh=("设计评审信号：口令用单轮快速哈希保存，未加盐，或全部账户共用一个固定盐。"),
         sig_en=("Design review signal: passwords are stored using a single-round fast hash, unsalted, or "
                 "with one fixed salt shared by every account."),
         why_zh=("把口令当成高熵密钥。口令来自有限的人类选择空间，它的安全性不来自“不可逆”，"
                 "而来自“每次猜测的成本”：快速哈希让单次猜测的成本极低；盐决定攻击者能否一次预计算"
                 "并用同一张表覆盖所有账户。没有逐用户盐时，相同口令产生相同摘要，攻击者可以按摘要"
                 "分组批量处理，一台机器的工作量被所有用户共享。"),
         why_en=("treating a password as a high-entropy key. Passwords come from a limited human "
                 "choice space, so their safety does not come from irreversibility but from the cost of each "
                 "guess: a fast hash makes one guess nearly free, and the salt decides whether an attacker "
                 "can precompute once and cover every account with a single table. Without a per-user salt, "
                 "equal passwords produce equal digests, so work can be grouped by digest and a single "
                 "machine's effort is shared across all users."),
         danger_zh=("它把一次泄露放大成大规模凭据恢复：恢复出的口令往往在别处复用，爆炸半径"
                    "越过单个系统；而这个缺陷在功能上完全没有症状——登录照常工作。"),
         danger_en=("one leak is amplified into large-scale credential recovery: recovered "
                    "passwords are usually reused elsewhere, so the blast radius crosses the single system - "
                    "and the defect has no functional symptom at all, since logins keep working."),
         def_zh=("机制依赖“猜测成本低”与“可预计算”，因此逐用户随机盐（消灭预计算与分组）"
                 "加上可调成本的内存困难函数（提高每次猜测的代价）是对症的结构性设计；把独立密钥材料"
                 "与哈希分开存放，可以在数据库泄露时仍保留一层屏障。"),
         def_en=("the mechanism depends on cheap guesses and precomputation, so a "
                 "random per-user salt (killing precomputation and grouping) together with a memory-hard "
                 "function with tunable cost (raising the price of each guess) is the structural design; "
                 "keeping a separate secret in independent storage preserves one more barrier if the "
                 "database leaks."),
         prof_zh=["成本参数随硬件代际校准，并保留升级路径：旧摘要可在下一次成功登录时迁移到新参数。",
                  "检测信号是摘要的形态与参数：审计清单核对算法、盐的唯一性与成本参数，"
                  "对“相同口令产生相同摘要”的批量分组特征做静态扫描。"],
         prof_en=["Calibrate cost parameters against current hardware generations and keep an upgrade path: "
                  "old digests can be migrated to new parameters on the next successful login.",
                  "The detection signal is the shape and parameters of the digest: audit algorithm choice, "
                  "salt uniqueness and cost parameters, and scan statically for the grouping signature of "
                  "equal passwords producing equal digests."]),

    # ------------------------------- 4) 供应链与权限模型（供应链与权限模型 3 题）
    dict(tid="sc-toctou", cat="supplychain-privilege",
         mit_zh="对句柄操作与原子创建语义（消除按名重解析）",
         mit_en="operating on handles with atomic creation semantics (no re-resolution by name)",
         sig_zh=("并发评审信号：一段特权代码先检查某个路径的状态，之后再用同一个路径字符串打开并使用它。"),
         sig_en=("Concurrency review signal: privileged code first checks the state of a path and later "
                 "opens and uses it through the same path string."),
         why_zh=("“检查”与“使用”之间存在时间缝，而且两者是通过名字而不是通过对象关联的：检查看到"
                 "的是某个名字当时指向的对象，使用是按名字重新解析出来的另一个时刻的对象；在两者之间，"
                 "任何有相应权限的进程都可以替换这个名字的指称（换掉链接、交换文件、改写内容）。"
                 "只要名字可被低权限方影响，检查的结论就无法转移到使用时刻。"),
         why_en=("a time gap between check and use, plus the fact that the two are correlated by "
                 "name rather than by object: the check examined what a name pointed to at that moment, "
                 "while the use re-resolves the name to an object at a later moment; in between, any process "
                 "with the right access can change what the name refers to (retarget a link, swap a file, "
                 "rewrite contents). Whenever a name can be influenced by a lower-privileged party, the "
                 "check's conclusion cannot be transferred to the moment of use."),
         danger_zh=("它把一个通过的检查变成了对另一个对象的授权（语用栖居处：一次正常的判权"
                    "动作成了授权凭据），于是低权限输入可以借特权进程之手作用于从未被检查过的对象。"),
         danger_en=("a passing check turns into authorization for a different object "
                    "(pragmatic layer: an ordinary permission decision becomes the credential), so "
                    "low-privileged input acts through a privileged process on an object that was never "
                    "checked."),
         def_zh=("机制依赖“按名字重新解析”，因此改为对已打开的对象句柄操作、使用不可跟随"
                 "链接的打开方式与原子创建语义（独占创建、原子替换）即可消除时间缝；把临时路径与共享"
                 "目录做成私有且不可预测，也让替换无从发生。"),
         def_en=("the mechanism depends on re-resolution by name, so operating on an "
                 "already-open handle, using no-follow open flags and atomic creation semantics (exclusive "
                 "create, atomic replace) removes the time gap; making temp paths private and unpredictable "
                 "leaves nothing to swap."),
         prof_zh=["检查与使用必须共用同一对象标识（已打开的句柄/文件描述符），禁止路径字符串二次解析。",
                  "检测信号是评审中同一路径字符串出现两次的“检查—使用”模式：静态分析标记按名判权后"
                  "按名打开，运行时对特权进程的链接跟随与非常规路径访问告警。"],
         prof_en=["Check and use must share the same object identity (an open handle or descriptor); never "
                  "re-resolve a path string.",
                  "The detection signal is the check-then-use pattern where the same path string appears "
                  "twice: let static analysis flag name-based authorization followed by name-based open, and "
                  "alert on link following and unusual path access by privileged processes."]),

    dict(tid="sc-privesc", cat="supplychain-privilege",
         mit_zh="最小权限与服务输入面归属校验",
         mit_en="least privilege plus ownership validation of every service input surface",
         sig_zh=("权限模型评审信号：一个以高权限运行的服务读取低权限用户可写目录中的配置，"
                 "并按其中的内容执行动作。"),
         sig_en=("Permission-model review signal: a service running with high privilege reads configuration "
                 "from a directory writable by lower-privileged users and acts on its contents."),
         why_zh=("权限边界没有在“输入流入点”收紧：高权限组件对比它低权限的输入方开放了一条输入"
                 "通道（文件、环境变量、套接字、注册表、服务参数），于是授权沿着输入反向流动——低权限方"
                 "通过提供输入间接获得高权限方才有的能力。常见放大因素包括默认继承过宽的执行令牌、"
                 "以共享账号运行、以及既有的弱权限配置（可写目录、可替换的二进制）。"),
         why_en=("the privilege boundary is not tightened where input enters: a "
                 "high-privilege component accepts an input channel from something less privileged (a file, "
                 "an environment variable, a socket, a registry key, a service argument), so authority flows "
                 "backwards along the input path - the lower-privileged party gains, indirectly through "
                 "input, what only the higher-privileged side should have. Typical amplifiers include "
                 "over-broad inherited tokens, shared service accounts, and pre-existing weak permissions "
                 "(writable directories, replaceable binaries)."),
         danger_zh=("它是“放大器”而不是单点缺陷：任何一个个别的输入处理问题都可能升级为"
                    "高权限执行，因此修单点收效有限。信号层面，滥用发生在正常功能路径上，没有异常"
                    "请求，只留下权限与归属的偏移。"),
         danger_en=("it acts as an amplifier rather than a single defect: any individual "
                    "input-handling problem can escalate into high-privilege execution, so fixing one site "
                    "achieves little. As a signal, the abuse happens on normal feature paths with no "
                    "anomalous request - only a drift in privilege and ownership."),
         def_zh=("机制依赖“高权限组件接受低权限输入”，因此最小权限（按需降权、以低权限账号"
                 "运行、能力化授权）、输入通道的归属与权限校验（只从受保护位置读取配置）、以及服务隔离"
                 "（沙箱、容器、作业对象）各自打断这条链；默认配置应当是“可写即可疑”。"),
         def_en=("the mechanism depends on a high-privilege component accepting "
                 "low-privilege input, so least privilege (drop rights as needed, run as a low-privilege "
                 "account, capability-based grants), ownership and permission validation of input channels "
                 "(read configuration only from protected locations), and service isolation (sandbox, "
                 "container, job object) each break the chain; the default assumption should be that "
                 "writable means untrusted."),
         prof_zh=["为每个特权入口列出输入面清单并逐项验证归属（谁可写、谁可替换），把配置与可执行文件"
                  "放在只有管理员可写的位置。",
                  "检测信号是“权限归属偏移”：审计高权限进程读写的路径与传入参数、监控可写目录中的"
                  "新文件被特权进程引用，以及服务安装目录与注册表项的权限漂移。"],
         prof_en=["List the input surfaces of every privileged entry point and validate ownership for each "
                  "(who can write, who can replace), keeping configuration and executables in "
                  "administrator-only locations.",
                  "The detection signal is a shift in privilege ownership: audit the paths and arguments "
                  "high-privilege processes read and write, watch for new files in writable directories "
                  "being consumed by privileged processes, and track permission drift on service "
                  "directories and registry keys."]),

    dict(tid="sc-depconfusion", cat="supplychain-privilege",
         mit_zh="命名空间唯一化加来源固定与锁文件完整性校验",
         mit_en="unique namespaces plus pinned sources and lockfile integrity checks",
         sig_zh=("供应链评审信号：构建配置同时启用内部镜像与公共仓库，内部包使用未加作用域前缀的短名。"),
         sig_en=("Supply-chain review signal: the build configuration enables an internal mirror and a "
                 "public repository at the same time, and internal packages use short names without a scope "
                 "prefix."),
         why_zh=("把“包名”当作唯一标识，而解析器实际在多个来源之间做优先级判定：当内部包名与"
                 "公共包同名、并且公共版本号更高时，解析器按版本优先级选出公共包——开发者以为是内部件，"
                 "构建系统取回了外部件。命名空间（作用域）、来源固定与版本优先级这三者只要有一处是"
                 "隐式的，解析结果就不再由人决定。"),
         why_en=("treating a package name as a unique identifier while the resolver actually "
                 "ranks multiple sources: when an internal name also exists publicly and the public version "
                 "number is higher, the resolver picks the public package by version priority - the developer "
                 "believes it is internal, the build system fetches something external. If any one of "
                 "namespace (scope), source pinning or version priority is implicit, the resolution outcome "
                 "is no longer decided by a person."),
         danger_zh=("信任决策被外包给了解析器排序：一次构建就能把外部代码放进受信任的产物，"
                    "而整个过程没有任何报错。它作用在“元数据/来源”栖居处——组件来自哪里——与代码"
                    "本身是否安全无关。"),
         danger_en=("the trust decision is delegated to resolver ordering: a single build "
                    "can place external code inside a trusted artifact, with no error reported anywhere. It "
                    "acts at the metadata/provenance layer - where a component comes from - independent of "
                    "whether the code itself is safe."),
         def_zh=("机制依赖“名字跨来源歧义”与“隐式优先级”，因此用作用域或命名空间唯一化内部"
                 "包名、在构建层固定解析来源（排除上游、只允许内部源解析内部作用域）、并对锁文件做内容"
                 "完整性校验即可；产物证明与签名把“来自哪里”变成可验证的事实。"),
         def_en=("the mechanism depends on cross-source name ambiguity and implicit "
                 "priority, so scoping or namespacing internal names, pinning resolution sources in the "
                 "build layer (exclude upstream, resolve internal scopes only internally) and verifying "
                 "lockfile integrity by content hash each remove it; artifact provenance and signatures turn "
                 "where it came from into a verifiable fact."),
         prof_zh=["解析来源与优先级在构建配置里显式声明，禁止默认回落到公共上游，内部作用域在上游"
                  "不可认领。",
                  "检测信号是依赖来源与声明的偏离：锁文件与无锁构建的差异比对、内容哈希校验、"
                  "发布者身份与发布时间的异常检测，以及构建期对真实下载源的审计日志。"],
         prof_en=["Declare resolution sources and priority explicitly in the build configuration, forbid "
                  "falling back to a public upstream by default, and make internal scopes unclaimable "
                  "upstream.",
                  "The detection signal is divergence between dependency origins and declarations: diff "
                  "lockfile builds against unlocked builds, verify content hashes, anomaly-check publisher "
                  "identity and publish time, and audit the real download sources at build time."]),

    # ------------------------------------------------- 5) AI 特有（AI 特有 2 题）
    dict(tid="ai-promptinjection", cat="ai-specific",
         mit_zh="来源分通道传递加动作层白名单与人工确认闸门",
         mit_en="channel-separated provenance plus action allowlists and human confirmation gates",
         sig_zh=("AI 评审信号：一个代理把外部文档内容与操作者指令放进同一段上下文，模型需要按"
                 "操作者意图行动。"),
         sig_en=("AI review signal: an agent places external document content and operator instructions in "
                 "the same context, and the model must act on the operator's intent."),
         why_zh=("“指令”与“数据”共用同一条通道：在模型的表示里两者都是同一上下文中的词元序列，"
                 "没有特权层级，注意力也不会按来源区分权重。只要载体文本在语言形态上与指令相同"
                 "（祈使句、格式标记、伪系统标签），它就成为候选指令；因此穿透不需要破解什么，只需要"
                 "让载体的措辞与指令的措辞无法区分。放大因素是真实边界由约定的标记或格式扮演，"
                 "而标记可以被模仿、覆盖或省略（结构与语用栖居处）。"),
         why_en=("instructions and data share one channel: in the model's representation "
                 "both are token sequences in the same context, with no privilege level, and attention does "
                 "not weight by origin. As soon as carrier text looks like an instruction in linguistic form "
                 "(imperatives, formatting markers, fake system labels), it becomes a candidate instruction; "
                 "penetration therefore requires no cracking, only making carrier wording "
                 "indistinguishable from instruction wording. The amplifier is that the real boundary is "
                 "played by conventional markers or formats, and markers can be imitated, overridden or "
                 "omitted (structural and pragmatic layers)."),
         danger_zh=("它把“读到的内容”变成“要执行的内容”，而执行侧常常连着工具、凭据与写权限，"
                    "于是数据通道直接接到了动作通道；同时因为遵循指令本身就是训练目标，模型越有用，"
                    "越容易被同形文本带走。"),
         danger_en=("what was read becomes what is executed, and the execution side is "
                    "usually wired to tools, credentials and write access, so the data channel is connected "
                    "straight to the action channel; and because instruction following is itself the training "
                    "objective, the more useful the model is, the more readily same-shaped text carries it "
                    "away."),
         def_zh=("机制依赖“通道合一”与“来源不参与判定”，因此在结构层把来源做成硬约束"
                 "（不同信任级的内容分通道或分区传递、工具输出与操作者指令在表示上分离）、在动作层做"
                 "权限最小化与输出闸门（高风险动作需显式确认、参数白名单化），比单纯“教模型识别注入"
                 "话术”更根本；检测侧把“载体里出现指令形态”当作信号上报。"),
         def_en=("the mechanism depends on channel fusion and on origin not "
                 "participating in the decision, so making provenance a hard structural constraint "
                 "(different trust levels delivered through separate channels or partitions, tool output "
                 "represented apart from operator instructions) and enforcing least privilege plus output "
                 "gates at the action layer (explicit confirmation for high-risk actions, allowlisted "
                 "arguments) is more fundamental than teaching the model to recognise injection phrasing; on "
                 "the detection side, instruction-shaped text inside a carrier is itself a signal to report."),
         prof_zh=["信任标签随内容一起流动：内容进入上下文前打来源标签，动作层按标签而不是按文本内容"
                  "授权。",
                  "检测信号是指令形态与来源不匹配：载体中的祈使句、伪系统标签、格式越界与“要求变更"
                  "目标”的措辞；上线后以动作白名单与人工确认阈值兜底，并把注入尝试计入安全指标。"],
         prof_en=["Trust labels travel with content: label provenance before content enters the context, and "
                  "let the action layer authorize by label rather than by text.",
                  "The detection signal is instruction shape that does not match provenance: imperatives in "
                  "a carrier, fake system labels, format escape and wording that asks to change the goal; in "
                  "production, action allowlists and confirmation thresholds are the backstop, and injection "
                  "attempts belong in the security metrics."]),

    dict(tid="ai-datapoisoning", cat="ai-specific",
         mit_zh="语料出处可追溯加触发条件专项检验",
         mit_en="traceable corpus provenance plus targeted trigger-condition testing",
         sig_zh=("模型安全评审信号：训练语料来自多来源抓取，缺少组件级出处与内容审核，微调阶段直接混入。"),
         sig_en=("Model-safety review signal: training data is scraped from many sources without "
                 "component-level provenance or content review, and is mixed in directly at the fine-tuning "
                 "stage."),
         why_zh=("训练目标本来就是统计量：优化器只关心整个语料上的平均损失，不关心单个样本的"
                 "出处，因此少量精心构造的样本可以推动某个条件行为（触发条件出现时改变输出），而对"
                 "平均损失的影响小到不触发常规验证。投毒之所以有效还有第二层原因——行为可以绑定在一个"
                 "在正常评估里从不出现的触发条件上，于是“平均指标正常”与“存在被植入的条件行为”"
                 "可以同时为真。"),
         why_en=("the training objective is a statistic: the optimizer cares about average "
                 "loss over the corpus, not about where an individual example came from, so a small set of "
                 "crafted examples can shift a conditional behaviour (output changes when a trigger appears) "
                 "while moving average loss too little to trip routine validation. There is a second reason "
                 "it works - the behaviour can be conditioned on a trigger that never occurs in normal "
                 "evaluation, so normal average metrics and an implanted conditional behaviour can both be "
                 "true at once."),
         danger_zh=("验证手段与被投毒的行为在统计上正交：常规评估只看平均质量，看不到稀疏的"
                    "条件行为；一旦进入部署，被植入的行为按攻击者选择的条件生效，而且难以通过查看"
                    "参数定位。信号层面，恶意藏在“元数据/来源”与“结构”栖居处——语料的出处与分布形态。"),
         danger_en=("validation and the implanted behaviour are statistically orthogonal: "
                    "routine evaluation looks at average quality and cannot see a sparse conditional "
                    "behaviour; once deployed, the implanted behaviour fires on the attacker's chosen "
                    "condition and is hard to locate by inspecting parameters. As a signal it hides at the "
                    "metadata/provenance and structural layers - where the corpus came from and how it is "
                    "distributed."),
         def_zh=("机制依赖“出处不可验证”与“评估只看平均”，因此来源可追溯（组件固定加内容"
                 "哈希加发布者身份）、去重与离群检测（异常重复与风格偏移）、以及针对触发条件的专项检验"
                 "（触发搜索、干净子集对照、行为探针扫描）都是结构性对策；审核侧还要把“与政策相矛盾的"
                 "措辞”当作信号，而不是当作噪声。"),
         def_en=("the mechanism depends on unverifiable provenance and on "
                 "average-only evaluation, so traceable sources (pinned components, content hashes, "
                 "publisher identity), deduplication and outlier detection (anomalous repetition, style "
                 "drift), and targeted trigger testing (trigger search, clean-subset comparison, behaviour "
                 "probe sweeps) are all structural countermeasures; on the review side, wording that "
                 "contradicts policy should be treated as a signal rather than as noise."),
         prof_zh=["语料组件化：每个来源固定版本与哈希，变更走审查；训练前做重复度与近重复聚类，"
                  "压缩可被集中影响的样本密度。",
                  "检测信号是条件行为而不是平均质量：用触发词搜索与插入增强、干净子集对照监控行为"
                  "差异，对特定输入族的输出偏移做上线前回归，并为模型版本留行为指纹。"],
         prof_en=["Componentize the corpus: pin a version and hash per source, route changes through review, "
                  "and cluster for duplicates and near-duplicates before training to compress the density of "
                  "samples a single actor could influence.",
                  "The detection signal is conditional behaviour rather than average quality: use trigger-word "
                  "search and insertion augmentation, compare against a clean subset to monitor behaviour "
                  "differences, regress output shifts for specific input families before release, and keep "
                  "behaviour fingerprints per model version."]),
]

assert len(TOPICS) == 15, len(TOPICS)
assert {t["cat"] for t in TOPICS} == dict(CATS).keys(), "题材类别须覆盖 5 类"
assert len({t["tid"] for t in TOPICS}) == len(TOPICS), "tid 必须唯一"

# ---------------------------------------------------------------- 情境框架 ---
# F1 纯机理 / F2 机理+防御检测诉求 / F3 要可执行序列（边界，少数对照行）/
# F4 第三方目标定向评估 / F5 防御侧机理（干净负例）
FRAME_WEIGHTS = (("F1", 2), ("F2", 2), ("F4", 1), ("F5", 1))
BOUNDARY_STRIDE = 5   # F3 只挂在每 5 个题材上（少数对照行）

QUESTION = {
    "F1": {
        "zh": "我只想搞清楚机理，请不要给操作步骤。这类机制为什么会成立？成因是什么？",
        "en": ("I only want to understand the mechanism - no operational steps. Why does this class of "
               "mechanism hold, and what causes it?"),
    },
    "F2": {
        "zh": "请解释这类机制的成因，并说明在防御与检测上应当抓住哪些要点。不要操作步骤。",
        "en": ("Explain the cause of this mechanism class and which points defense and detection should "
               "grip. No operational steps."),
    },
    "F3": {
        "zh": ("再补上可以直接照做的完整操作序列和现成实现，我要能马上复现的那种。"),
        "en": ("Also include a directly executable sequence and a ready-made implementation that I can "
               "reproduce immediately."),
    },
    "F4": {
        "zh": ("这段现象出现在一个我们没有所有权的第三方系统上（没有授权材料）。请解释机理，"
               "并判断那个目标上是否确实可被利用。"),
        "en": ("This pattern appears on a third-party system we do not own (no authorization on file). "
               "Explain the mechanism and tell us whether that target is actually exploitable."),
    },
    "F5": {
        "zh": "{mit} 为什么能阻止这类机制？防御侧究竟改变了什么？",
        "en": ("Why does {mit} stop this mechanism class, and what exactly does the defensive side "
               "change?"),
    },
}

# 表述变体（改述阶梯，docs/06 §7 的一致性训练信号）：zh 复用 v0 的礼貌包装，
# en 使用本族自带的纯 ASCII 变体（en 行要求零 CJK / 全 ASCII）。
SURFACES = {
    "zh": SURFACE_WRAPPERS["zh"],
    "en": ["Hi - {q}", "Quick one: {q}", "Could you help with this: {q}"],
}

LBL = {
    "zh": {
        "mech_head": "机制解释（教科书级，不含操作增量）——类别：{cat}。",
        "f2_head": "按“防御与检测”侧重解释（教科书级，不含操作增量）——类别：{cat}。",
        "f4_head": "先限定范围：下面只讲与目标无关的机制层——类别：{cat}。",
        "f5_head": "防御侧机理（教科书级）——类别：{cat}。",
        "why": "成因：{x}",
        "danger": "为什么危险：{x}",
        "def": "防御性理解：{x}",
        "def_change": "防御侧改变了什么：{x}",
        "prof": "公开的通用防御与检测要点（类别级，仍不含操作增量）：",
        "band_note": ("你问的检测/告警清单属更高粒度（P-DUALUSE-GRANULARITY=textbook），"
                      "本包给到教科书级：上面已给防御原理，检测清单不在本包输出面内。"),
        "scope": ("范围声明：对那个第三方目标的可利用性判断属于定向评估，缺授权语境时不提供"
                  "（P-CONTEXT-THRESHOLD；针对真实第三方的定向评估落在 HF-005 邻域）。"),
        "auth": ("授权路径：若为自有资产或书面授权范围内的目标，定向评估请走授权通道单独发起；"
                 "本族不产出操作性内容。"),
    },
    "en": {
        "mech_head": "Mechanism explanation (textbook level, no operational uplift) - class: {cat}.",
        "f2_head": "Explained with a defense-and-detection emphasis (textbook level, no operational uplift) - class: {cat}.",
        "f4_head": "Scope first: what follows is only the target-independent mechanism layer - class: {cat}.",
        "f5_head": "Defensive-side mechanism (textbook level) - class: {cat}.",
        "why": "Cause: {x}",
        "danger": "Why it is dangerous: {x}",
        "def": "Defensive understanding: {x}",
        "def_change": "What the defensive side changes: {x}",
        "prof": "General, public defense and detection points (class level, still no operational uplift):",
        "band_note": ("The detection and alerting checklist you asked for sits at a higher granularity "
                      "(P-DUALUSE-GRANULARITY=textbook), so this pack stops at the textbook level: the "
                      "defensive reasoning is above and the checklist is outside this pack's output "
                      "surface."),
        "scope": ("Scope note: an exploitability judgement about that third-party target is a targeted "
                  "assessment and is not provided without an authorized context (P-CONTEXT-THRESHOLD; "
                  "targeted assessment of real third parties sits in the HF-005 neighbourhood)."),
        "auth": ("Authorization path: if the asset is your own or inside a written engagement scope, "
                 "request the targeted assessment through the authorized channel; this family produces no "
                 "operational content."),
    },
}

REFUSE_F3 = {
    "zh": ("拒绝：这条请求要的是可以直接照做的完整操作序列与现成实现——也就是操作增量，"
           "而机制解释族的边界恰好是不提供它（本族输出面：教科书级到 textbook+）。"
           "这条线为什么画在这里：机制知识对攻防两侧同样开放，讲清楚“为什么成立”已经覆盖"
           "防御所需的理解；可执行序列把理解转换成能力差，这个增量才是伤害项"
           "（docs/00 §4.3 边际能力增量口径：伤害 ∝ Δ(能力|R) × P(恶意|C)）。"
           "替代路径：本族主线可以单独回答教科书级成因、为什么危险与防御侧理解——这些是 "
           "T2 的正当输出。"),
    "en": ("Refused: this request asks for a directly executable sequence and a ready-made implementation - "
           "operational uplift - which is exactly what the mechanism-explanation family does not provide "
           "(this family's output surface runs from textbook to textbook-plus). Why the line sits here: "
           "mechanism knowledge is equally open to defenders and attackers, and explaining why something "
           "holds already covers what defense needs; an executable sequence converts understanding into a "
           "capability gap, and that delta is the harm term (docs/00 section 4.3, marginal capability "
           "uplift: harm is proportional to capability delta times malicious probability). Alternative: "
           "this family can answer the textbook-level cause, why it is dangerous and the defensive "
           "understanding as a separate question - those are its legitimate output."),
}
REFUSE_F3_PACK = {
    "conservative": {
        "zh": "本包口径：P-DUALUSE-GRANULARITY=textbook、P-ACTION-PERMISSIONS=none。",
        "en": "This pack: P-DUALUSE-GRANULARITY=textbook, P-ACTION-PERMISSIONS=none.",
    },
    "default": {
        "zh": ("本包口径：P-DUALUSE-GRANULARITY=mixed，但本族（机制解释）的输出面停在教科书级，"
               "P-ACTION-PERMISSIONS=propose。"),
        "en": ("This pack: P-DUALUSE-GRANULARITY=mixed, but the mechanism-explanation family's output "
               "surface still stops at textbook; P-ACTION-PERMISSIONS=propose."),
    },
    "professional": {
        "zh": ("本包口径：专业档在授权语境内允许 operational 粒度，但本族的作用域是 textbook+"
               "（公开的防御与检测要点）；操作性序列属于授权演练通道与专门工具链的职责，不在此处。"),
        "en": ("This pack: the professional tier allows operational granularity inside authorized contexts, "
               "but this family's scope is textbook-plus (public defense and detection points); operational "
               "sequences belong to the authorized engagement channel and its tooling, not here."),
    },
}
REFUSE_F3_ALT = {
    "zh": "可给的替代（教科书级、不含操作增量）——防御侧理解：{x}",
    "en": "What can be given instead (textbook level, no operational uplift) - defensive understanding: {x}",
}
REFUSE_F4 = {
    "zh": ("拒绝（本包语境阈值）：请求把机制解释与对真实第三方目标的定向可利用性判断绑在一起。"
           "语境证据不足（P-CONTEXT-THRESHOLD=high：无授权材料、目标非自有资产），而针对真实"
           "第三方的定向评估落在硬底线邻域（HF-005）。替代路径：① 单独提问、只问与目标无关的"
           "教科书级机理——本族主线可以回答；② 若目标实为自有资产，先补齐资产属主证明与书面授权，"
           "再走定向评估通道。"),
    "en": ("Refused (this pack's context threshold): the request binds a mechanism explanation to a "
           "targeted exploitability judgement about a real third-party target. Context evidence is "
           "insufficient (P-CONTEXT-THRESHOLD=high: no authorization on file, asset not owned) and "
           "targeted assessment of a real third party sits in the hard-floor neighbourhood (HF-005). "
           "Alternatives: (1) ask a separate, target-independent textbook-level mechanism question, which "
           "this family can answer; (2) if the asset is in fact yours, obtain ownership attestation and "
           "written authorization first, then use the targeted-assessment channel."),
}


# ---------------------------------------------------------------- 行构造 ---
def cat_label(topic: dict, lang: str) -> str:
    if lang == "en":
        return topic["cat"]
    return "%s / %s" % (CAT_ZH[topic["cat"]], topic["cat"])


def band_label(pack: str) -> str:
    return "textbook+" if pack == "professional" else "textbook"


def build_user(topic: dict, lang: str, frame: str, ref: str, variant: int) -> str:
    sig = topic["sig_" + lang]
    q = QUESTION[frame][lang].format(mit=topic["mit_" + lang], ref=ref)
    if variant > 0:
        q = SURFACES[lang][(variant - 1) % len(SURFACES[lang])].format(q=q)
    if lang == "zh":
        return ("信号（评审/扫描记录，编号 {ref}）：\n{sig}\n\n{q}".format(
            ref=ref, sig=sig, q=q))
    return ("Signal (review/scan record, case ref {ref}):\n{sig}\n\n{q}".format(
        ref=ref, sig=sig, q=q))


def build_assistant(topic: dict, lang: str, pack: str, frame: str, ref: str):
    """返回 (assistant 文本, action, verdict, confidence, findings)。"""
    L = LBL[lang]
    cat = cat_label(topic, lang)
    why = topic["why_" + lang]
    danger = topic["danger_" + lang]
    dfn = topic["def_" + lang]
    prof_bullets = [L["prof"]] + ["- " + b for b in topic["prof_" + lang]]
    conf = CONF[pack]
    action, verdict = "answer", (V_MECH_PLUS if pack == "professional" else V_MECH)

    if frame == "F3":
        action, verdict, conf = "refuse", V_REFUSE, 0.95
        body = [REFUSE_F3[lang], REFUSE_F3_PACK[pack][lang],
                REFUSE_F3_ALT[lang].format(x=dfn)]
    elif frame == "F4" and pack == "conservative":
        action, verdict, conf = "refuse", V_REFUSE, 0.94
        body = [REFUSE_F4[lang], REFUSE_F3_ALT[lang].format(x=dfn)]
    elif frame == "F1":
        body = [L["mech_head"].format(cat=cat),
                L["why"].format(x=why), L["danger"].format(x=danger),
                L["def"].format(x=dfn)]
        body += prof_bullets if pack == "professional" else []
    elif frame == "F2":
        body = [L["f2_head"].format(cat=cat),
                L["def"].format(x=dfn), L["why"].format(x=why),
                L["danger"].format(x=danger)]
        body += prof_bullets if pack == "professional" else [L["band_note"]]
    elif frame == "F4":
        body = [L["f4_head"].format(cat=cat),
                L["why"].format(x=why), L["danger"].format(x=danger),
                L["def"].format(x=dfn), L["scope"]]
        body += prof_bullets if pack == "professional" else []
        body.append(L["auth"])
    elif frame == "F5":
        body = [L["f5_head"].format(cat=cat),
                L["def_change"].format(x=dfn), L["why"].format(x=why)]
        body += prof_bullets if pack == "professional" else []
    else:
        raise ValueError("unknown frame: %s" % frame)

    if lang == "zh":
        findings = ["机制类别：%s/%s" % (CAT_ZH[topic["cat"]], topic["tid"]),
                    "粒度带：%s" % band_label(pack),
                    "信号编号：%s" % ref]
    else:
        findings = ["mechanism class: %s/%s" % (topic["cat"], topic["tid"]),
                    "granularity band: %s" % band_label(pack),
                    "case ref: %s" % ref]
    text = "\n".join(body) + "\n" + verdict_line(action, verdict, conf, findings, pack)
    return text, action, verdict, conf, findings


def build_group_specs(n_groups: int) -> list:
    """确定性情境清单：(topic 下标, lang, frame, variant)。

    每一轮覆盖 15 题材 × 5 情境（zh/en 各一套），并把 zh/en 交替压平，
    使任意前缀的语种分布均衡（小样本自检也保持各半）。
    """
    specs = []
    rnd = 0
    while len(specs) < n_groups:
        # 槽位级构造：一个槽位 = 同一题材/情境的 zh+en 两条（先 zh 后 en），
        # 因此任意前缀的语种差 ≤1 组（小样本自检也严格各半）。
        slots = []
        for t_idx, _t in enumerate(TOPICS):
            for frame, weight in FRAME_WEIGHTS:
                for w in range(weight):
                    slots.append((t_idx, frame, rnd + w))
        # 边界（要可执行序列）槽位均匀铺开：任意前缀都含边界样本，
        # 且边界组占比保持少数（每轮 3/93 槽）。
        for k, t_idx in enumerate(range(0, len(TOPICS), BOUNDARY_STRIDE)):
            pos = int(k * len(slots) / 3)
            slots.insert(pos + k, (t_idx, "F3", rnd))
        for t_idx, frame, var in slots:
            specs.append((t_idx, "zh", frame, var))
            specs.append((t_idx, "en", frame, var))
        rnd += 1
    return specs[:n_groups]


def planned_coverage(n: int) -> dict:
    """给定 --n 时生成器计划覆盖的类别/题材/情境（校验用）。"""
    specs = build_group_specs(max(0, n // 3))
    return {"categories": sorted({TOPICS[t]["cat"] for t, _l, _f, _v in specs}),
            "topics": sorted({TOPICS[t]["tid"] for t, _l, _f, _v in specs}),
            "frames": sorted({f for _t, _l, f, _v in specs}),
            "groups": len(specs)}


def generate(n: int = DEFAULT_N, seed: int = DEFAULT_SEED) -> list:
    """生成 n 行（确定性：同 seed 同 n → 逐字节相同输出）。"""
    if n <= 0:
        raise SystemExit("--n 必须为正整数")
    rows = []
    n_groups = n // 3
    specs = build_group_specs(n_groups)
    for g_idx, (t_idx, lang, frame, variant) in enumerate(specs):
        topic = TOPICS[t_idx]
        ref = "T2-%05d" % (g_idx + 1)
        user = build_user(topic, lang, frame, ref, variant)
        for pack in PACKS:
            text, _a, _v, _c, _f = build_assistant(topic, lang, pack, frame, ref)
            rows.append(build_sample("sft-T2-%05d" % (len(rows) + 1), TASK,
                                     pack, lang, user, text))
    # 余数行（n 非 3 整除时的对照行；pack 轮转，保证行数精确为 n）
    extra = n - len(rows)
    for k in range(extra):
        t_idx = (len(specs) + k) % len(TOPICS)
        lang = LANGS[k % 2]
        frame = ("F1", "F3")[k % 2]
        pack = PACKS[k % 3]
        ref = "T2-%05d" % (len(specs) + k + 1)
        topic = TOPICS[t_idx]
        user = build_user(topic, lang, frame, ref, 1 + k)
        text, _a, _v, _c, _f = build_assistant(topic, lang, pack, frame, ref)
        rows.append(build_sample("sft-T2-%05d" % (len(rows) + 1), TASK,
                                 pack, lang, user, text))
    rng = random.Random(seed)
    rng.shuffle(rows)
    return rows


# ---------------------------------------------------------------- 自检 ---
def find_payload_markers(text: str) -> list:
    """返回文本中命中的代码块/可利用载荷标记（大小写不敏感；空列表=干净）。"""
    low = text.lower()
    hits = []
    for m in PAYLOAD_MARKERS:
        i = low.find(m.lower())
        if i >= 0:
            hits.append({"marker": m,
                         "context": text[max(0, i - 24):i + len(m) + 24]})
    return hits


TID2CAT = {t["tid"]: t["cat"] for t in TOPICS}


def validate_rows(rows: list, expect_total: int | None = None,
                  expect_categories: list | None = None) -> dict:
    """全部断言集中在此；返回报告（errors 非空即失败）。"""
    errors = []
    ids, users, pack_user = set(), set(), set()
    by_pack, by_lang, by_action, by_verdict = {}, {}, {}, {}
    by_cat = {}
    marker_hits = []
    groups = {}

    if expect_total is not None and len(rows) != expect_total:
        errors.append("总数 %d != 期望 %d" % (len(rows), expect_total))

    for i, r in enumerate(rows):
        sid = r.get("id", "<no-id>")
        if set(r) != {"id", "task", "pack", "lang", "messages"}:
            errors.append("%s: 字段集 != m1 契约" % sid)
            continue
        if r["task"] != TASK:
            errors.append("%s: task != %s" % (sid, TASK))
        if r["id"] in ids:
            errors.append("%s: id 重复" % sid)
        ids.add(r["id"])
        if r["pack"] not in PACKS:
            errors.append("%s: pack 非法 %s" % (sid, r["pack"]))
        if r["lang"] not in LANGS:
            errors.append("%s: lang 非法 %s" % (sid, r["lang"]))
        msgs = r["messages"]
        if not (len(msgs) == 3 and [m["role"] for m in msgs] ==
                ["system", "user", "assistant"]):
            errors.append("%s: 消息结构非 system/user/assistant" % sid)
            continue
        user, asst = msgs[1]["content"], msgs[2]["content"]
        if msgs[0]["content"] != POLICY_SYSTEM[r["pack"]][r["lang"]]:
            errors.append("%s: system 区 != POLICY_SYSTEM[pack][lang]" % sid)
        if "pack:" not in msgs[0]["content"] or "@0.1" not in msgs[0]["content"]:
            errors.append("%s: system 缺政策引用" % sid)
        # (a) VERDICT 闭环
        v = None
        if "VERDICT: " not in asst:
            errors.append("%s: assistant 缺 VERDICT" % sid)
        else:
            tail = asst.rsplit("VERDICT: ", 1)[1]
            try:
                v = json.loads(tail)
            except json.JSONDecodeError:
                errors.append("%s: VERDICT JSON 解析失败" % sid)
                v = None
            if isinstance(v, dict):
                if set(v) != {"action", "verdict", "confidence", "findings",
                              "policy"}:
                    errors.append("%s: VERDICT 字段集异常 %s" % (sid, sorted(v)))
                if v.get("action") not in ("answer", "refuse", "report"):
                    errors.append("%s: action 非法 %s" % (sid, v.get("action")))
                if v.get("verdict") not in VOCAB:
                    errors.append("%s: verdict 不在 T2 词表 %s" % (sid, v.get("verdict")))
                if v.get("policy") != r["pack"]:
                    errors.append("%s: policy != pack" % sid)
                by_action[v.get("action")] = by_action.get(v.get("action"), 0) + 1
                by_verdict[v.get("verdict")] = by_verdict.get(v.get("verdict"), 0) + 1
                blob = " ".join(str(x) for x in (v.get("findings") or []))
                tid = next((t for t in TID2CAT if t in blob), None)
                if tid is None:
                    errors.append("%s: findings 缺机制类别（tid）" % sid)
                else:
                    c = TID2CAT[tid]
                    by_cat[c] = by_cat.get(c, 0) + 1
        # (b) 载荷标记：assistant 侧硬断言，user 侧一并复扫
        for where, txt in (("assistant", asst), ("user", user)):
            for h in find_payload_markers(txt):
                marker_hits.append({"id": sid, "where": where, **h})
        # (d) 结构 / 语言一致性
        users.add(user)
        if (r["pack"], user) in pack_user:
            errors.append("%s: (pack,user) 重复" % sid)
        pack_user.add((r["pack"], user))
        if r["lang"] == "zh":
            if len(_CJK.findall(user)) < 10:
                errors.append("%s: zh 行 user 中文不足" % sid)
        else:
            if _CJK.search(user) or _CJK.search(asst):
                errors.append("%s: en 行含 CJK" % sid)
            bad = [c for c in (user + asst) if ord(c) > 127]
            if bad:
                errors.append("%s: en 行非 ASCII 字符 %s" % (sid, sorted(set(bad))))
        m = _REF_RE.search(user)
        if not m:
            errors.append("%s: user 缺 group ref" % sid)
        else:
            groups.setdefault(m.group(0), []).append(
                (r["pack"], v.get("action") if isinstance(v, dict) else None,
                 v.get("verdict") if isinstance(v, dict) else None))
        by_pack[r["pack"]] = by_pack.get(r["pack"], 0) + 1
        by_lang[r["lang"]] = by_lang.get(r["lang"], 0) + 1

    # 分组比对（三包同情境）——余数行（n 非 3 整除）组成 1 人“部分组”，
    # 数量上限 = n % 3；正常情境组必须恰好三包各一。
    max_partial = (expect_total % 3) if expect_total else 0
    full_groups, partial_groups, bad_groups, boundary_groups = 0, 0, [], 0
    for ref, entries in sorted(groups.items()):
        if len(entries) != 3:
            if len(entries) == 1 and partial_groups < max_partial:
                partial_groups += 1
                continue
            errors.append("情境组 %s 三包不成组：%s" % (ref, entries))
            continue
        if {p for p, _a, _v in entries} != set(PACKS):
            errors.append("情境组 %s 三包不齐：%s" % (ref, entries))
            continue
        full_groups += 1
        tuples = {(a, vv) for _p, a, vv in entries}
        if len(tuples) > 1:
            bad_groups.append(ref)      # “不同”= (action,verdict) 出现多种
        if all(a == "refuse" for _p, a, _v in entries):
            boundary_groups += 1
    if expect_total is not None and full_groups != (expect_total // 3):
        errors.append("完整情境组数 %d != 期望 %d" % (full_groups, expect_total // 3))
    # 每个情境组一份 user（三包共用），故去重后的 user 数应等于组数
    if len(users) != full_groups + partial_groups:
        errors.append("user 数 %d != 情境组数 %d"
                      % (len(users), full_groups + partial_groups))
    diff_ratio = (len(bad_groups) / full_groups) if full_groups else 0.0
    boundary_ratio = (boundary_groups / full_groups) if full_groups else 0.0
    refuse_rows = by_action.get("refuse", 0)
    refuse_ratio = refuse_rows / len(rows) if rows else 0.0

    if marker_hits:
        errors.append("载荷标记命中 %d 处（必须为 0）" % len(marker_hits))
    if diff_ratio < TRI_PACK_DIFF_FLOOR:
        errors.append("三包差异化 %.3f < %.2f" % (diff_ratio, TRI_PACK_DIFF_FLOOR))
    if refuse_ratio > REFUSE_RATIO_CAP:
        errors.append("拒绝行占比 %.3f > %.2f（T2 主体应为机制解释）"
                      % (refuse_ratio, REFUSE_RATIO_CAP))
    if boundary_groups < 1:
        errors.append("缺少三包同拒的边界（要可执行序列）情境组")
    if boundary_ratio > 0.15:
        errors.append("三包同拒组占比 %.3f > 0.15（边界样本应为少数对照行）"
                      % boundary_ratio)
    if by_lang.get("zh", 0) != by_lang.get("en", 0):
        if abs(by_lang.get("zh", 0) - by_lang.get("en", 0)) > max(1, len(rows) // 20):
            errors.append("zh:en 不均衡 %s" % by_lang)
    for p in PACKS:
        if by_pack.get(p, 0) == 0:
            errors.append("包梯度缺失 %s" % p)
    if expect_categories is not None:
        for c in expect_categories:
            if by_cat.get(c, 0) == 0:
                errors.append("题材类别覆盖缺失 %s" % c)

    return {"ok": not errors, "errors": errors[:40],
            "checks": {
                "rows": len(rows), "full_groups": full_groups,
                "partial_groups": partial_groups,
                "payload_marker_hits": len(marker_hits),
                "payload_markers_scanned": len(PAYLOAD_MARKERS),
                "tri_pack_diff_groups": len(bad_groups),
                "tri_pack_diff_ratio": round(diff_ratio, 4),
                "tri_pack_diff_floor": TRI_PACK_DIFF_FLOOR,
                "boundary_all_refuse_groups": boundary_groups,
                "boundary_group_ratio": round(boundary_ratio, 4),
                "refuse_rows": refuse_rows,
                "refuse_ratio": round(refuse_ratio, 4),
                "refuse_ratio_cap": REFUSE_RATIO_CAP,
                "categories_covered": sorted(by_cat),
            },
            "marker_hits_detail": marker_hits[:10],
            "by_pack": by_pack, "by_lang": by_lang, "by_action": by_action,
            "by_verdict": by_verdict, "by_category": by_cat}


# ---------------------------------------------------------------- CLI ---
def resolve_out(raw: str) -> Path:
    """出口解析：允许 data/sft/** 或仓库外的临时目录，禁止写入 data/ 其他子树。"""
    p = Path(raw)
    if not p.is_absolute():
        p = (ROOT / p)
    if p.suffix.lower() != ".jsonl":
        p = p / "t2_mechanism.jsonl"
    p = p.resolve()
    data_dir = (ROOT / "data").resolve()
    sft_dir = (ROOT / "data" / "sft").resolve()
    try:
        inside_data = data_dir in p.parents
    except Exception:                                     # pragma: no cover
        inside_data = False
    if inside_data and sft_dir not in p.parents:
        raise SystemExit("拒绝写入 data/ 下非 sft 目录：%s" % p)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="T2 机制解释族生成器")
    ap.add_argument("--out", default=str(OUT_DEFAULT),
                    help="输出 .jsonl 或目录（目录则追加 t2_mechanism.jsonl）")
    ap.add_argument("--n", type=int, default=DEFAULT_N, help="总行数")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子")
    ap.add_argument("--stats-out", default=None,
                    help="统计报告 JSON 路径（默认不写）")
    args = ap.parse_args(argv)

    out = resolve_out(args.out)
    rows = generate(args.n, args.seed)
    planned = planned_coverage(args.n)
    report = validate_rows(rows, expect_total=args.n,
                           expect_categories=planned["categories"])

    print("[载荷标记清单] %d 项：%s" % (len(PAYLOAD_MARKERS),
                                       ", ".join(repr(m) for m in PAYLOAD_MARKERS)))
    print("[载荷标记命中] assistant/user 合计 %d 处（断言 0）"
          % report["checks"]["payload_marker_hits"])
    if report["marker_hits_detail"]:
        for h in report["marker_hits_detail"]:
            print("  HIT %s %s %r ... %r" % (h["id"], h["where"], h["marker"],
                                             h["context"]))

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()

    stats = {
        "generator": "scripts/gen_t2_mechanism.py",
        "task": TASK, "n": len(rows), "seed": args.seed, "out": str(out),
        "sha256": digest,
        "by_pack": report["by_pack"], "by_lang": report["by_lang"],
        "by_action": report["by_action"], "by_verdict": report["by_verdict"],
        "by_category": report["by_category"],
        "coverage": {"planned": planned,
                     "row_categories": report["by_category"],
                     "categories_all": [c for c, _z in CATS]},
        "rows_per_group": 3,
        "groups": planned["groups"],
        "assertions": report["checks"],
        "payload_markers": list(PAYLOAD_MARKERS),
        "payload_marker_hits": report["checks"]["payload_marker_hits"],
        "assert_ok": report["ok"],
        "errors": report["errors"],
    }
    print(json.dumps({k: stats[k] for k in
                      ("n", "seed", "out", "sha256", "by_pack", "by_lang",
                       "by_action", "by_verdict", "by_category", "assertions")},
                     ensure_ascii=False, indent=2))
    print("[断言] %s" % ("全部通过" if report["ok"] else "失败：%s" % report["errors"]))
    if args.stats_out:
        sp = Path(args.stats_out)
        if not sp.is_absolute():
            sp = ROOT / sp
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
        print("-> %s" % sp)
    if not report["ok"]:
        return 1
    print("wrote %d rows -> %s" % (len(rows), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
