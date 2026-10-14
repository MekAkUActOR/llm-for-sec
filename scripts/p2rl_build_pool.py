# -*- coding: utf-8 -*-
r"""P2-RL prompt 池构建器（v1，n=3,000 → data/rlvr/p2rl-pool-v01.jsonl + manifest）。

规格唯一权威：reports/p2rl-grpo-preregistration.md §4（构成/配比/隔离红线）。
纯 CPU 实现件，不触 GPU、不训练。

## 构成（§4.1，配比钉死）

| 类 | n | 占比 | 来源 |
|---|---|---|---|
| A 载体风险题 | 900 | 30% | gen_rlvr_tasks.gen_inj_detect **新生成**（独立 RNG 流），只取风险在场侧 |
| B 载体良性题 | 600 | 20% | 同生成器 clean 载体侧（良性侧显式扩产） |
| C 通用域良性 | 750 | 25% | general_qa/writing/translation/code/summary 五域新模板，显式无风险判断教学（verdict=clean） |
| D 多轮良性骨架 | 300 | 10% | 2–4 轮良性追问骨架（写作/代码迭代/翻译润色），末轮期望 answer |
| E policy_ruling | 300 | 10% | tasks-v01 抽样（M3.5 遗产复用，schema 已 dump 核实） |
| F pii + carrier_classify | 150 | 5% | tasks-v01 抽样（判断教学：裁决词 + 定位） |

- 良性总量 1,650（55%）> 风险 900（30%）✓（m5-plan v2）；
- en ≥ 50% 全池（A/B/C/D 语言配额制 + E/F 按库存抽样配额），C/D 内 en ≥ 50%；
- prompt 长度：单轮 p99 ≤ 1024 tok、多轮 p99 ≤ 2048 tok（建池 assert，
  soup checkpoint tokenizer 实测；max_prompt_length=2048 兜底）。

## 与 heldout 隔离 ✗（§4.2 红线，建池即扫）

1. 物理隔离：只读 data/rlvr/tasks-v01.jsonl；heldout 全系只进**隔离索引**（读入
   仅为证明不重叠，不进任何训练行）；
2. 内容隔离：规范化 8-gram 连续共享游程 vs **全部 heldout 套件** ≤ 30
   （check_sft_contamination normalize/ngrams 机制，check_rlvr_tasks 精神的双侧扩展）；
3. 攻击族隔离：v0.7 套件 150 行整体不入训练——8-gram ≤30 vs v0.7 + 全池正文
   对 v0.7 turns/goal 的规范化子串零命中双断言；D 类骨架按良性追问构造；
4. 新鲜性：独立 RNG 流（--seed 派生，manifest 登记 sha256 与全部派生种子）。

## 输出契约（每行）

    {"id": "p2rl-<cls>-<seq>", "pool_class": "A|B|C|D|E|F", "task_type": ...,
     "policy_pack": ..., "lang": "zh|en",
     "messages": [{role, content}, ...],           # system + user(+历史)，parity 门用
     "prompt": "<预渲染 ChatML 串>",                 # TRL str prompt 原样使用（§7.4①）
     "p2rl_task_json": "<p2rl_reward 任务元数据 JSON 串>",
     "reward_pack": "<pack>"}

预渲染 = render_chatml（promptfmt.chat_prompt 的多轮自然扩展：单轮与
secfm.eval.promptfmt.chat_prompt **逐字节一致**，建池对全部单轮行断言；
训练/评测渲染零漂移 = 规格 §7.4 开口项①的解法）。

用法：
    python scripts/p2rl_build_pool.py                    # 默认 seed=20261008
    python scripts/p2rl_build_pool.py --seed N --force   # 目标存在时默认 exit 4（防覆写）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

import gen_rlvr_tasks as grt  # noqa: E402  inj_detect 生成器复用（零 fork）
import gen_sft_v0 as g0  # noqa: E402  POLICY_SYSTEM（政策包共享契约）
from check_sft_contamination import normalize, ngrams  # noqa: E402

# ---------------------------------------------------------------- 常量 --------
P2RL_SEED = 20261008
POOL_N = 3000
CLASS_QUOTAS = {"A": 900, "B": 600, "C": 750, "D": 300, "E": 300, "F": 150}
# en 语言配额（zh = 类配额 − en）；C/D 内 en ≥ 50%，全池 en ≥ 50%
LANG_EN_QUOTAS = {"A": 450, "B": 300, "C": 375, "D": 150, "E": 160, "F": 80}
E_QUOTA = 300
F_SPLIT = {"pii_discover": 75, "carrier_classify": 75}
F_EN_SPLIT = {"pii_discover": 40, "carrier_classify": 40}
BENIGN_TOTAL = 1650   # B+C+D（§4.1：55% > 风险 30%）
RISK_TOTAL = 900      # A
LONGEST_RUN_MAX = 30  # 8-gram 游程阈值（房屋新鲜性线，feasibility §4.6）
SINGLE_TOK_P99_MAX = 1024
MULTI_TOK_P99_MAX = 2048
HELDOUT_ROOT = ROOT / "data" / "heldout"
TASKS_V01 = ROOT / "data" / "rlvr" / "tasks-v01.jsonl"
DEFAULT_OUT = ROOT / "data" / "rlvr" / "p2rl-pool-v01.jsonl"
DEFAULT_MANIFEST = ROOT / "data" / "rlvr" / "p2rl-pool-v01.manifest.json"
TOKENIZER_PATH = ROOT / "checkpoints" / "soup-needlefix-a050"
# 派生种子（manifest 登记；int 派生保证跨进程确定性——str 播种受 PYTHONHASHSEED 影响 ✗）
DERIVED_SEEDS = {
    "A": P2RL_SEED * 100 + 1, "B": P2RL_SEED * 100 + 2,
    "C": P2RL_SEED * 100 + 3, "D": P2RL_SEED * 100 + 4,
    "EF": P2RL_SEED * 100 + 5,
}
GENERATOR = "scripts/p2rl_build_pool.py"


# ------------------------------------------------------------ ChatML 渲染 ----
def render_chatml(messages: list[dict]) -> str:
    """messages → 预渲染 ChatML 串（末尾 assistant 头，不插 think 块）。

    单轮 [system, user] 与 secfm.eval.promptfmt.chat_prompt 逐字节一致
    （建池断言 + run_p2rl_grpo --dry-run 20 条 parity 门双覆盖）。
    """
    parts = [f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
             for m in messages]
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def _vline(action="answer", verdict="clean", confidence=0.9,
           findings=(), policy="default") -> str:
    return "VERDICT: " + json.dumps(
        {"action": action, "verdict": verdict, "confidence": confidence,
         "findings": list(findings), "policy": policy}, ensure_ascii=False)


# ================================================================ C 类模板 ====
# 五域通用良性（v0.2.3 ORR 分维重灾域：general_code/general_writing 等）。
# 主题与 heldout 仅领域同类（设计内：教会"无风险/放行"判断本身，规则 44.3），
# 措辞全新——8-gram 隔离扫描建池断言 ≤30。
C_CONTRACT = {
    "zh": "\n\n完成后按输出契约在末尾单独一行给出 VERDICT：本题判定无风险，"
          "action=answer、verdict=clean（confidence、findings、policy 字段齐全）。",
    "en": "\n\nWhen done, end with a single VERDICT line per the output "
          "contract: this request is risk-free, so use action=answer and "
          "verdict=clean (with confidence, findings and policy fields).",
}
C_SURFACES = {
    "zh": ["{q}", "通用任务：{q}", "（日常支持）{q}"],
    "en": ["{q}", "General task: {q}", "(Daily support) {q}"],
}
C_ORDER = ("general_qa", "general_writing", "general_translation",
           "general_code", "general_summary")
C_TOPICS = {
    "general_qa": {
        "zh": ["零信任架构里最要紧的几条原则是什么？",
               "TLS 1.3 相比 1.2 在握手阶段做了哪些简化？",
               "为什么密码存储要先加盐再哈希？",
               "CSRF 和 XSS 的成因有什么本质区别？",
               "最小权限原则在实践中如何落地？",
               "DLP（数据防泄漏）通常覆盖哪些通道？",
               "什么是横向移动，为什么它难以被发现？",
               "日志审计里的“四眼原则”指什么？",
               "DNS over HTTPS 会带来哪些新的安全考量？",
               "供应链攻击为什么难以用传统手段防御？"],
        "en": ["Which principles matter most in a zero-trust architecture?",
               "How does TLS 1.3 simplify the handshake compared to 1.2?",
               "Why should passwords be salted before hashing?",
               "What is the essential difference between CSRF and XSS?",
               "How is the principle of least privilege applied in practice?",
               "Which channels does DLP typically cover?",
               "What makes lateral movement hard to detect?",
               "What does the four-eyes principle mean in log auditing?",
               "What new considerations does DNS over HTTPS introduce?",
               "Why do supply-chain attacks resist traditional defenses?"],
    },
    "general_writing": {
        "zh": ["写一段面向全员的备份纪律提醒（80 字以内）。",
               "起草一封催办安全补丁更新的邮件正文。",
               "写一份值班交接纪要的模板框架。",
               "为新员工写一段安全意识培训的开场白。",
               "起草一条关于门禁卡挂失流程的内部通知。",
               "写一段面向客户的产品安全特性介绍文案。",
               "起草一份月度安全例会的议程草稿。",
               "写一段关于“离开工位请锁屏”的轻松提醒。",
               "起草一份演练复盘会议的邀请说明。",
               "写一段内部 Wiki 安全规范页的编者按。"],
        "en": ["Write a short all-staff reminder about backup discipline "
               "(under 80 words).",
               "Draft the body of an email chasing a pending patch rollout.",
               "Outline a template for a shift-handover security log.",
               "Write an opening paragraph for new-hire security training.",
               "Draft an internal notice about the badge-loss procedure.",
               "Write customer-facing copy for a product security feature.",
               "Draft an agenda outline for the monthly security review.",
               "Write a light-hearted reminder about locking your screen.",
               "Draft an invitation note for a drill retrospective.",
               "Write an editor's note for the internal wiki security page."],
    },
    "general_translation": {
        "zh": ["把下述中文句子翻译成英文：请在变更窗口结束后确认所有节点已恢复。",
               "把下述中文句子翻译成英文：这份报告的结论部分还需要法务同事复核。",
               "把下述中文句子翻译成英文：备份任务的完成时间比预期晚了四十分钟。",
               "把下述中文句子翻译成英文：值班表已更新，请查收最新版本。",
               "把下述中文句子翻译成英文：新的访问申请需要在系统里走三级审批。",
               "把下述中文句子翻译成英文：演练复盘会议定在周四下午两点。",
               "把下述中文句子翻译成英文：这批设备的验收报告已归档。",
               "把下述中文句子翻译成英文：工单系统今晚有例行维护。",
               "把下述中文句子翻译成英文：请把这份通知同步给外包团队。",
               "把下述中文句子翻译成英文：培训材料已经上传到内网门户。"],
        "en": ["Translate this sentence into Chinese: Please confirm that "
               "all nodes have recovered after the change window.",
               "Translate this sentence into Chinese: The conclusion "
               "section of this report still needs legal review.",
               "Translate this sentence into Chinese: The backup job "
               "finished forty minutes later than expected.",
               "Translate this sentence into Chinese: The on-call roster "
               "has been updated; please check the latest version.",
               "Translate this sentence into Chinese: New access requests "
               "require three-level approval in the system.",
               "Translate this sentence into Chinese: The drill "
               "retrospective is scheduled for Thursday at 2 p.m.",
               "Translate this sentence into Chinese: The acceptance "
               "report for this batch of devices has been archived.",
               "Translate this sentence into Chinese: The ticketing system "
               "has routine maintenance tonight.",
               "Translate this sentence into Chinese: Please forward this "
               "notice to the contractor team.",
               "Translate this sentence into Chinese: The training "
               "materials have been uploaded to the intranet portal."],
    },
    "general_code": {
        "zh": ["用 Python 统计一段文本里每个单词各出现多少次。",
               "实现一个函数，检查输入文本正读和反读是否一致。",
               "写一个脚本，把 CSV 文件转换成 JSON 数组。",
               "实现一个函数，从访问日志行里提取来源地址和状态码。",
               "写一个简单的口令强度检查器（长度与字符类别打分）。",
               "用 Python 写一个目录树打印工具（缩进展示层级）。",
               "实现一个按序号批量重命名文件的小工具。",
               "写一个函数，计算两个日期之间的工作日天数。",
               "用 Python 实现一个简易的待办事项命令行程序。",
               "写一个解析 YAML 配置并打印全部键路径的小脚本。"],
        "en": ["In Python, write a function that counts how often each word "
               "appears in a text.",
               "Implement a function that checks whether a text reads the "
               "same forwards and backwards.",
               "Write a script that converts a CSV file into a JSON array.",
               "Implement a function that extracts the source address and "
               "status code from an access-log line.",
               "Write a simple passphrase strength checker (length and "
               "character-class scoring).",
               "Write a Python utility that prints a directory tree with "
               "indentation.",
               "Implement a small tool that renames files by sequence "
               "number.",
               "Write a function that counts working days between two "
               "dates.",
               "Implement a minimal to-do command-line program in Python.",
               "Write a script that parses a YAML config and prints all "
               "key paths."],
    },
    "general_summary": {
        "zh": ["总结以下内容要点：全量备份每周日执行，增量备份每日凌晨两点执行；"
               "备份保留 30 天；每季度做一次恢复演练。",
               "总结以下内容要点：每季度各部门提交权限清单，安全组比对岗位说明，"
               "差异项经负责人确认后回收。",
               "总结以下内容要点：严重问题 7 天内修复，高危 30 天，中危 90 天；"
               "超期项自动升级到风险委员会。",
               "总结以下内容要点：新员工第一天完成账号与门禁开通，第三天前完成"
               "培训与考试，第 30 天完成转正复核。",
               "总结以下内容要点：生产变更需提前两个工作日提单并附回滚方案；"
               "紧急变更须在 24 小时内补齐手续。",
               "总结以下内容要点：边界设备日志保留 180 天，应用日志保留 90 天；"
               "导出需走审批。",
               "总结以下内容要点：口令最小长度 12 位且含三类字符，90 天轮换，"
               "禁止复用最近 5 次。",
               "总结以下内容要点：事件分四级，二级以上 30 分钟内成立响应小组，"
               "每半年演练一次。",
               "总结以下内容要点：数据分公开、内部、机密、绝密四级；机密级外发"
               "必须加密并留痕。",
               "总结以下内容要点：外部服务商须签署安全协议，接入走专用通道，"
               "每年复审一次。"],
        "en": ["Summarize the key points: full backups run every Sunday; "
               "incremental backups run daily at 02:00; retention is 30 "
               "days; a restore drill is held quarterly.",
               "Summarize the key points: each department submits its "
               "permission list quarterly; the security team compares it "
               "with job descriptions; deltas are revoked after owner "
               "confirmation.",
               "Summarize the key points: critical issues are fixed within "
               "7 days, high within 30, medium within 90; overdue items "
               "escalate to the risk committee.",
               "Summarize the key points: accounts and badges on day one; "
               "awareness training and quiz within three days; "
               "confirmation review on day 30.",
               "Summarize the key points: production changes need a ticket "
               "two business days ahead with a rollback plan; emergency "
               "changes must be documented within 24 hours.",
               "Summarize the key points: perimeter logs are kept for 180 "
               "days and application logs for 90; export requires "
               "approval.",
               "Summarize the key points: minimum passphrase length 12 "
               "with three character classes; rotation every 90 days; "
               "reuse of the last five is blocked.",
               "Summarize the key points: four severity levels; level-two "
               "and above require a response team within 30 minutes; "
               "drills twice a year.",
               "Summarize the key points: public, internal, confidential, "
               "restricted tiers; confidential data must be encrypted and "
               "logged when leaving the environment.",
               "Summarize the key points: vendors sign a security "
               "agreement; connections use dedicated channels; annual "
               "re-review."],
    },
}
C_PHRASES = {  # 3 措辞/域/语
    "general_qa": {
        "zh": ["请回答下面的问题：{t}", "下面是一个知识性问题，请简要作答：{t}",
               "作为团队参考资料，请解答：{t}"],
        "en": ["Please answer the following question: {t}",
               "Here is a knowledge question — answer briefly: {t}",
               "As reference material for the team, please explain: {t}"],
    },
    "general_writing": {
        "zh": ["{t}", "写作任务——{t}", "（内部沟通）{t}"],
        "en": ["{t}", "Writing task — {t}", "(Internal communication) {t}"],
    },
    "general_translation": {
        "zh": ["{t}", "翻译练习——{t}", "（语言支持）{t}"],
        "en": ["{t}", "Translation practice — {t}", "(Language support) {t}"],
    },
    "general_code": {
        "zh": ["{t}", "编程任务——{t}", "（内部工具）{t}"],
        "en": ["{t}", "Coding task — {t}", "(Internal tooling) {t}"],
    },
    "general_summary": {
        "zh": ["{t}", "阅读后提炼要点——{t}", "（材料摘要）{t}"],
        "en": ["{t}", "Read and distill the key points — {t}",
               "(Material summary) {t}"],
    },
}


# ================================================================ D 类骨架 ====
# 2–4 轮良性追问（写作/代码迭代/翻译润色），骨架模式与 v0.7 攻击族（F1–F6
# 渐进升级/人格注入/虚构框架/编码混淆/切片/权威伪造）零同源：纯良性协作追问，
# 无任何升级、人格、虚构、混淆、切片、权威要素。末轮期望 answer（放行+ 多轮保持）。
D_SURFACES = {
    "zh": ["{q}", "继续刚才的任务：{q}", "接着改：{q}"],
    "en": ["{q}", "Continuing the earlier task: {q}", "Next tweak: {q}"],
}
D_FAMILIES = ("writing", "code", "translation")
# 每族每语：2 主题 × 4 T0 措辞；A0 按主题配对；追问链 3 对（topic 中性）
D_DATA = {
    "writing": {
        "zh": {
            "topics": [
                ["帮我写一段关于备份纪律的内部提醒文案。",
                 "帮我起草一条备份纪律提醒，面向全体同事。",
                 "请写一段内部提醒，主题是备份纪律。",
                 "给全员写一条简短的备份纪律提醒。"],
                ["帮我起草一封催办安全补丁更新的邮件。",
                 "写一封邮件正文，催一下待更新的安全补丁。",
                 "请起草催办补丁更新的邮件。",
                 "帮我拟一封补丁更新催办邮件。"]],
            "a0": [
                "好的，初稿如下：「各位同事：本周日起全量备份窗口调整至凌晨"
                "两点，请各团队提前确认作业排期，避免与变更窗口冲突。如有"
                "疑问请联系安全组。」篇幅与语气可再调整。\n" + _vline(),
                "好的，邮件初稿如下：「各位好：上轮发布的安全补丁仍有部分"
                "主机未完成更新，请各负责人于本周五前完成重启确认并回复"
                "本邮件，逾期项将汇总上报。」可按需调整称呼与期限。\n"
                + _vline()],
            "followups": [
                ("把篇幅压缩到一半。",
                 "好的，已压缩到一半，只保留行动项与截止时间两块核心信息，"
                 "可直接取用；还要改就告诉我。\n" + _vline()),
                ("语气改得更正式一些。",
                 "好的，已改为正式公文语气，敬语与落款都按内部规范补齐了，"
                 "这一版可以直接发文。\n" + _vline()),
                ("在结尾加一句针对远程办公同事的提醒。",
                 "好的，结尾已补上远程办公同事的对应注意事项，本地与远程"
                 "口径保持一致。\n" + _vline()),
            ],
        },
        "en": {
            "topics": [
                ["Help me write an internal reminder about backup "
                 "discipline.",
                 "Draft a short all-staff reminder on backup discipline.",
                 "Please write an internal note reminding people of the "
                 "backup rules.",
                 "Write a brief reminder for everyone about backup "
                 "discipline."],
                ["Help me draft an email chasing the pending patch "
                 "rollout.",
                 "Draft an email body chasing the outstanding security "
                 "patch updates.",
                 "Please draft a patch-rollout reminder email.",
                 "Write an email nudging owners about pending patches."]],
            "a0": [
                "Sure — first draft: \"Team: starting this Sunday the full-"
                "backup window moves to 02:00. Please confirm your job "
                "schedules in advance so they don't collide with change "
                "windows. Questions welcome at the security desk.\" Happy "
                "to adjust tone or length.\n" + _vline(),
                "Sure — draft: \"Hi all: a number of hosts still need this "
                "round of security patches. Please complete the updates "
                "and confirm by Friday EOD; anything outstanding will be "
                "summarised for the weekly report.\" Adjust the deadline "
                "or greeting as needed.\n" + _vline()],
            "followups": [
                ("Cut the length in half.",
                 "Done — halved it and kept only the action items and the "
                 "deadline; use it as is, or tell me what else to trim.\n"
                 + _vline()),
                ("Make the tone more formal.",
                 "Done — rewritten in a formal register with proper "
                 "salutation and sign-off, ready to send.\n" + _vline()),
                ("Add a closing line aimed at remote workers.",
                 "Done — added a closing note covering remote colleagues, "
                 "with the same wording for on-site and remote staff.\n"
                 + _vline()),
            ],
        },
    },
    "code": {
        "zh": {
            "topics": [
                ["写一个 Python 函数，统计一段文本中每个单词的出现次数。",
                 "用 Python 实现单词计数函数，输入一段文本即可。",
                 "请实现一个函数：统计文本里各单词出现多少次。",
                 "帮我写个函数做词频统计，Python 版。"],
                ["写一个函数，计算两个日期之间的工作日天数。",
                 "用 Python 计算两个日期之间隔了多少个工作日。",
                 "请实现工作日天数计算函数（跳过周末）。",
                 "帮我写个函数数一数两个日期间的工作日。"]],
            "a0": [
                "好的，思路：按空白切分文本、统一小写、用字典累加计数，"
                "最后返回计数字典。核心逻辑十几行即可，边界（空文本）返回"
                "空字典。需要完整代码或加上排序输出都可以。\n" + _vline(),
                "好的，思路：逐日推进起点到终点，跳过周六周日，计数即得；"
                "用标准库 datetime 即可，注意区间开闭口径先约定。需要完整"
                "实现或加节假日表都可以。\n" + _vline()],
            "followups": [
                ("给函数加上类型注解。",
                 "好的，签名与返回值都补上了类型注解，内部变量也顺带标了，"
                 "IDE 检查已通过。\n" + _vline()),
                ("处理空输入的情况并说明行为。",
                 "好的，空输入分支已处理：返回空结果并附一行说明，文档"
                 "字符串里也写明了约定。\n" + _vline()),
                ("把输出改成按次数降序排列。",
                 "好的，输出已改为按计数降序，相同次数按字典序稳定排列，"
                 "示例输出也更新了。\n" + _vline()),
            ],
        },
        "en": {
            "topics": [
                ["In Python, write a function that counts how often each "
                 "word appears in a text.",
                 "Implement a word-count function in Python that takes a "
                 "block of text.",
                 "Please implement a function counting how often each word "
                 "occurs.",
                 "Help me write a word-frequency function in Python."],
                ["Write a function that counts working days between two "
                 "dates.",
                 "Count the working days between two dates in Python.",
                 "Please implement a working-day counter (skip weekends).",
                 "Help me write a function that counts business days."]],
            "a0": [
                "Sure — the idea: split on whitespace, lowercase, "
                "accumulate counts in a dict, return the dict. The core is "
                "about a dozen lines; empty input returns an empty dict. "
                "Happy to provide the full code or sorted output.\n"
                + _vline(),
                "Sure — the idea: walk day by day from start to end, skip "
                "Saturdays and Sundays, and count. The standard datetime "
                "library is enough; just agree on inclusive/exclusive "
                "bounds first. Full implementation or a holiday table on "
                "request.\n" + _vline()],
            "followups": [
                ("Add type annotations to the function.",
                 "Done — added type hints to the signature and return "
                 "value, annotated the internals too; it passes the IDE "
                 "checks.\n" + _vline()),
                ("Handle empty input and explain the behavior.",
                 "Done — empty input now returns an empty result with a "
                 "one-line note, and the docstring documents the "
                 "convention.\n" + _vline()),
                ("Sort the output by count in descending order.",
                 "Done — output is now sorted by count descending, ties in "
                 "stable lexical order; the example output is updated "
                 "too.\n" + _vline()),
            ],
        },
    },
    "translation": {
        "zh": {
            "topics": [
                ["把这句话翻译成英文：请在变更窗口结束后确认所有节点已恢复。",
                 "翻译成英文：请在变更窗口结束后确认所有节点已恢复。",
                 "帮我把这句话译成英文：请在变更窗口结束后确认所有节点已恢复。",
                 "这句翻成英文怎么说：请在变更窗口结束后确认所有节点已恢复？"],
                ["把这句话翻译成英文：新的访问申请需要三级审批。",
                 "翻译成英文：新的访问申请需要三级审批。",
                 "帮我把这句话译成英文：新的访问申请需要三级审批。",
                 "这句翻成英文怎么说：新的访问申请需要三级审批？"]],
            "a0": [
                "好的，译文：\"Please confirm that all nodes have recovered "
                "after the change window.\" 语域为中性运维口径；如需更口语"
                "或更正式的版本可以继续调。\n" + _vline(),
                "好的，译文：\"New access requests require three-level "
                "approval.\" 审批层级译法与内网术语表一致；需要调整语域"
                "请说。\n" + _vline()],
            "followups": [
                ("换一个更口语化的译法。",
                 "好的，口语版已给出，用词更日常，语气也放松了一档；两版"
                 "差异主要在语域。\n" + _vline()),
                ("给出两个备选译法并说明差异。",
                 "好的，给了直译与意译两个备选，并各附一句差异说明（重点"
                 "在主被动与术语选择）。\n" + _vline()),
                ("按正式公文的语气重译。",
                 "好的，已按正式公文语域重译，措辞与句式都收紧了，可直接"
                 "用于书面材料。\n" + _vline()),
            ],
        },
        "en": {
            "topics": [
                ["Translate this sentence into Chinese: Please confirm "
                 "that all nodes have recovered after the change window.",
                 "Render this into Chinese: Please confirm that all nodes "
                 "have recovered after the change window.",
                 "How would you translate this into Chinese: Please "
                 "confirm that all nodes have recovered after the change "
                 "window?",
                 "Put this into Chinese for me: Please confirm that all "
                 "nodes have recovered after the change window."],
                ["Translate this sentence into Chinese: New access "
                 "requests require three-level approval.",
                 "Render this into Chinese: New access requests require "
                 "three-level approval.",
                 "How would you translate this into Chinese: New access "
                 "requests require three-level approval?",
                 "Put this into Chinese for me: New access requests "
                 "require three-level approval."]],
            "a0": [
                "Sure — here it is: 「请在变更窗口结束后确认所有节点已恢"
                "复。」 The register is neutral ops language; I can make it "
                "more colloquial or more formal.\n" + _vline(),
                "Sure — here it is: 「新的访问申请需要三级审批。」The "
                "approval-tier wording matches the internal glossary; say "
                "the word if you want a different register.\n" + _vline()],
            "followups": [
                ("Give a more colloquial version.",
                 "Done — a colloquial version is provided, with more "
                 "everyday wording and a lighter tone; the main difference "
                 "from the first pass is register.\n" + _vline()),
                ("Offer two alternatives and explain the difference.",
                 "Done — a literal and a freer alternative, each with a "
                 "one-line note on the difference (mainly voice and term "
                 "choice).\n" + _vline()),
                ("Redo it in a formal register.",
                 "Done — retranslated in a formal register with tighter "
                 "diction, suitable for written documents.\n" + _vline()),
            ],
        },
    },
}


# ================================================================ 行组装 ======
def _row(pool_class: str, seq: int, task_type: str, pack: str, lang: str,
         messages: list[dict], meta: dict) -> dict:
    meta = {"task_type": task_type, **meta, "pool_class": pool_class}
    return {
        "id": f"p2rl-{pool_class.lower()}-{seq:06d}",
        "pool_class": pool_class, "task_type": task_type,
        "policy_pack": pack, "lang": lang, "messages": messages,
        "prompt": render_chatml(messages),
        "p2rl_task_json": json.dumps(meta, ensure_ascii=False),
        "reward_pack": pack,
    }


def _gen_inj_side(rng: random.Random, side: bool, n_en: int,
                  cls: str) -> list[dict]:
    """A/B 类：gen_inj_detect 新生成，按 (side, lang) 配额过滤收行。"""
    want = {"en": n_en, "zh": CLASS_QUOTAS[cls] - n_en}
    got = {"en": 0, "zh": 0}
    rows: list[dict] = []
    seq = 0
    while (got["en"] < want["en"] or got["zh"] < want["zh"]) and seq < 500000:
        r = grt.gen_inj_detect(rng, seq)
        seq += 1
        gt = r["ground_truth"]
        risk = gt["verdict"] == "contains-injection"
        if risk != side or got[r["lang"]] >= want[r["lang"]]:
            continue
        got[r["lang"]] += 1
        meta = {"risk_present": risk, "expected_action": gt["action"],
                "verdict_gt": gt["verdict"], "locate": gt["locate"],
                "src": "fresh"}
        rows.append(_row(cls, len(rows), "inj_detect", r["policy_pack"],
                         r["lang"], r["messages"], meta))
    if got["en"] < want["en"] or got["zh"] < want["zh"]:
        raise RuntimeError(f"{cls} 类配额未满足: {got} < {want}")
    return rows


def build_c(rng: random.Random) -> list[dict]:
    """C 类：五域通用良性 + 显式无风险判断教学（verdict=clean）。"""
    rows: list[dict] = []
    for lang in ("zh", "en"):
        combos = [(d, ti, pi, si) for d in C_ORDER
                  for ti in range(len(C_TOPICS[d][lang]))
                  for pi in range(len(C_PHRASES[d][lang]))
                  for si in range(len(C_SURFACES[lang]))]
        need = CLASS_QUOTAS["C"] // 2
        if len(combos) < need:
            raise RuntimeError("C 类组合不足")
        for d, ti, pi, si in rng.sample(combos, need):
            topic = C_TOPICS[d][lang][ti]
            q = C_PHRASES[d][lang][pi].format(t=topic)
            user = C_SURFACES[lang][si].format(q=q) + C_CONTRACT[lang]
            messages = [
                {"role": "system", "content": g0.POLICY_SYSTEM["default"][lang]},
                {"role": "user", "content": user}]
            meta = {"risk_present": False, "expected_action": "answer",
                    "verdict_gt": "clean", "locate": [], "src": "fresh"}
            rows.append(_row("C", len(rows), "general_benign", "default",
                             lang, messages, meta))
    return rows


def build_d(rng: random.Random) -> list[dict]:
    """D 类：2–4 轮良性追问骨架，末轮期望 answer（骨架与 v0.7 攻击族零同源）。"""
    rows: list[dict] = []
    for lang in ("zh", "en"):
        combos = [(fam, ti, t0i, si, depth) for fam in D_FAMILIES
                  for ti in range(2)
                  for t0i in range(4)
                  for si in range(len(D_SURFACES[lang]))
                  for depth in (2, 3, 4)]
        need = CLASS_QUOTAS["D"] // 2
        if len(combos) < need:
            raise RuntimeError("D 类组合不足")
        for fam, ti, t0i, si, depth in rng.sample(combos, need):
            data = D_DATA[fam][lang]
            t0 = D_SURFACES[lang][si].format(q=data["topics"][ti][t0i])
            msgs = [
                {"role": "system", "content": g0.POLICY_SYSTEM["default"][lang]},
                {"role": "user", "content": t0},
                {"role": "assistant", "content": data["a0"][ti]}]
            for k in range(depth - 1):
                u, a = data["followups"][k]
                msgs.append({"role": "user", "content": u})
                if k < depth - 2:
                    msgs.append({"role": "assistant", "content": a})
            meta = {"risk_present": False, "expected_action": "answer",
                    "verdict_gt": None, "locate": [], "src": "fresh",
                    "n_user_turns": depth}
            rows.append(_row("D", len(rows), "multi_turn_benign", "default",
                             lang, msgs, meta))
    return rows


def build_ef(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """E/F 类：tasks-v01 抽样（schema 已实测 dump：messages/reward_task_json/
    reward_pack/ground_truth/policy_pack/lang；不猜 ✗）。"""
    src = {"policy_ruling": [], "pii_discover": [], "carrier_classify": []}
    for line in TASKS_V01.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d["task_type"] in src:  # inj_detect 不入 E/F（A/B 新生成替代）
            src[d["task_type"]].append(d)
    e_rows, f_rows = [], []

    def _sample(pool, n_en, n_zh):
        by = {"en": [r for r in pool if r["lang"] == "en"],
              "zh": [r for r in pool if r["lang"] == "zh"]}
        return rng.sample(by["en"], n_en) + rng.sample(by["zh"], n_zh)

    for r in _sample(src["policy_ruling"], LANG_EN_QUOTAS["E"],
                     E_QUOTA - LANG_EN_QUOTAS["E"]):
        gt = r["ground_truth"]
        pack = r["policy_pack"]
        meta = {"risk_present": gt.get("action") != "answer",
                "expected_action": gt.get("action"),
                "actions": gt.get("actions"), "verdict_gt": None,
                "locate": [], "src": "tasks-v01", "src_id": r["id"]}
        e_rows.append(_row("E", len(e_rows), "policy_ruling", pack,
                           r["lang"], r["messages"], meta))
    for tt in F_SPLIT:
        for r in _sample(src[tt], F_EN_SPLIT[tt],
                         F_SPLIT[tt] - F_EN_SPLIT[tt]):
            gt = r["ground_truth"]
            meta = {"risk_present": False,
                    "expected_action": gt.get("action"),
                    "verdict_gt": gt.get("verdict"), "locate": gt.get("locate"),
                    "src": "tasks-v01", "src_id": r["id"]}
            f_rows.append(_row("F", len(f_rows), tt, r["policy_pack"],
                               r["lang"], r["messages"], meta))
    return e_rows, f_rows


# ================================================================ 隔离扫描 ====
import re  # noqa: E402  隔离扫描用（契约样板剥离）

# VERDICT 行 = 输出契约样板（设计内共享，同 POLICY_SYSTEM 先例——gen_rlvr
# 「新鲜性断言只针对 user 侧文本」的同类豁免）：双侧剥离后再做 8-gram 扫描，
# 散文部分照扫。D 类骨架的 canned assistant 末行即此样板（v0.5-topup 家族
# 的任务说明内嵌 VERDICT 示例，不剥离则必然伪命中）。
_VERDICT_JSON = re.compile(r"(?i)verdict:\s*\{.*\}")


def _strip_contract(text: str) -> str:
    return _VERDICT_JSON.sub(" ", text)


def _suite_texts() -> dict[str, list[str]]:
    """全部 heldout 套件的评测侧文本（user 侧；system/政策包文本按设计共享不计）。"""
    suites: dict[str, list[str]] = {}

    def _add(suite: str, text: str):
        if text and text.strip():
            suites.setdefault(suite, []).append(text)

    for p in sorted(HELDOUT_ROOT.rglob("*.jsonl")):
        suite = p.parent.name
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            for key in ("query", "text", "frag", "goal"):
                if isinstance(d.get(key), str):
                    _add(suite, d[key])
            if isinstance(d.get("turns"), list):
                for t in d["turns"]:
                    if isinstance(t, str):
                        _add(suite, t)
            if isinstance(d.get("messages"), list):
                for m in d["messages"]:
                    if isinstance(m, dict) and m.get("role") != "system" \
                            and isinstance(m.get("content"), str):
                        _add(suite, m["content"])
    return suites


def scan_isolation(rows: list[dict]) -> dict:
    """8-gram 游程 vs 全部 heldout 套件（≤30）+ v0.7 子串零命中双断言。

    两侧先剥 VERDICT 契约样板（_strip_contract，见上注）；v0.7 子串断言
    不剥离（全文本口径，更保守）。
    """
    suites = _suite_texts()
    v07_texts = [normalize(t) for t in suites.get("v0.7-jailbreak", [])]
    grams_by_suite = {
        s: {g for t in texts for g in ngrams(normalize(_strip_contract(t)))}
        for s, texts in suites.items()}
    pool_texts = []
    for r in rows:
        for m in r["messages"]:
            if m["role"] != "system":
                pool_texts.append((r["id"], normalize(_strip_contract(m["content"]))))
    max_run = {s: 0 for s in suites}
    worst = {s: "" for s in suites}
    for rid, text in pool_texts:
        gs = ngrams(text)
        for s, idx in grams_by_suite.items():
            best = cur = 0
            for g in gs:
                cur = cur + 1 if g in idx else 0
                if cur > best:
                    best = cur
                if best > max_run[s]:
                    max_run[s] = best
                    worst[s] = rid
    # v0.7 子串断言（全池正文 vs v0.7 turns/goal 规范化子串）
    v07_sub_hits = []
    if v07_texts:
        norm_pool = [(rid, t) for rid, t in pool_texts if t]
        for vt in v07_texts:
            if len(vt) < 16:
                continue
            for rid, pt in norm_pool:
                if vt in pt:
                    v07_sub_hits.append(rid)
    return {"per_suite_max_run": max_run, "overall_max_run": max(max_run.values()),
            "worst_row": worst, "n_suites": len(suites),
            "v07_substring_hits": sorted(set(v07_sub_hits)),
            "v07_texts_indexed": len(v07_texts)}


# ================================================================ 主流程 ======
def _p99(vals: list[int]) -> int:
    s = sorted(vals)
    return s[min(len(s) - 1, int(0.99 * len(s)))]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parity_promptfmt(rows: list[dict]) -> int:
    """全部单轮行 vs promptfmt.chat_prompt 逐字节一致（返回校验条数）。"""
    from secfm.eval.promptfmt import chat_prompt
    n = 0
    for r in rows:
        msgs = r["messages"]
        if len(msgs) != 2:
            continue
        expect = chat_prompt(msgs[1]["content"], pack=r["policy_pack"],
                             lang=r["lang"])
        assert r["prompt"] == expect, (
            f"parity 破坏：{r['id']} 预渲染串 != promptfmt.chat_prompt 输出")
        n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P2-RL prompt 池构建器（v1）")
    ap.add_argument("--seed", type=int, default=P2RL_SEED)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--force", action="store_true",
                    help="目标已存在时强制覆写（默认 exit 4 防覆写）")
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    manifest = Path(args.manifest).resolve()
    for tgt in (out, manifest):
        if tgt.exists() and not args.force:
            print(f"[FATAL] 目标已存在，拒绝覆写（防覆写纪律）：{tgt}"
                  f"（--force 可显式覆盖）")
            return 4
    if args.seed != P2RL_SEED:  # 派生种子随 --seed 派生
        for i, k in enumerate(("A", "B", "C", "D", "EF"), start=1):
            DERIVED_SEEDS[k] = args.seed * 100 + i

    print(f"[build] seed={args.seed} 派生={DERIVED_SEEDS}")
    rng_a = random.Random(DERIVED_SEEDS["A"])
    rng_b = random.Random(DERIVED_SEEDS["B"])
    rng_c = random.Random(DERIVED_SEEDS["C"])
    rng_d = random.Random(DERIVED_SEEDS["D"])
    rng_ef = random.Random(DERIVED_SEEDS["EF"])

    rows = []
    rows += _gen_inj_side(rng_a, True, LANG_EN_QUOTAS["A"], "A")
    rows += _gen_inj_side(rng_b, False, LANG_EN_QUOTAS["B"], "B")
    rows += build_c(rng_c)
    rows += build_d(rng_d)
    e_rows, f_rows = build_ef(rng_ef)
    rows += e_rows + f_rows

    # ---- 结构断言（fail-closed）----
    n = len(rows)
    assert n == POOL_N, f"池大小 {n} != {POOL_N}"
    cls_counts = Counter(r["pool_class"] for r in rows)
    assert dict(cls_counts) == CLASS_QUOTAS, f"配比破坏: {cls_counts}"
    lang_counts = Counter(r["lang"] for r in rows)
    en_share = lang_counts["en"] / n
    assert en_share >= 0.5, f"en 占比 {en_share:.4f} < 50%"
    for c in ("C", "D"):
        en_c = sum(1 for r in rows if r["pool_class"] == c and r["lang"] == "en")
        assert en_c >= CLASS_QUOTAS[c] / 2, f"{c} 类 en < 50%"
    benign = sum(CLASS_QUOTAS[c] for c in ("B", "C", "D"))
    assert benign == BENIGN_TOTAL and CLASS_QUOTAS["A"] == RISK_TOTAL
    for r in rows:  # 行契约
        assert r["prompt"] == render_chatml(r["messages"]), r["id"]
        meta = json.loads(r["p2rl_task_json"])
        if meta["task_type"] == "policy_ruling":
            assert isinstance(meta.get("actions"), dict), r["id"]
        else:
            assert isinstance(meta.get("risk_present"), bool), r["id"]
        assert r["reward_pack"] == r["policy_pack"]
    n_parity = _parity_promptfmt(rows)

    # ---- 隔离扫描（8-gram ≤30 vs 全 heldout + v0.7 双断言）----
    print("[scan] 8-gram 游程 vs 全部 heldout 套件 ...")
    iso = scan_isolation(rows)
    assert iso["overall_max_run"] <= LONGEST_RUN_MAX, (
        f"隔离破坏：最长共享游程 {iso['overall_max_run']} > {LONGEST_RUN_MAX}；"
        f"逐套件 {iso['per_suite_max_run']}；worst={iso['worst_row']}")
    assert not iso["v07_substring_hits"], (
        f"v0.7 全套不入训练断言失败：{iso['v07_substring_hits'][:5]}")
    v07_run = iso["per_suite_max_run"].get("v0.7-jailbreak", 0)

    # ---- p99 token 长度（soup checkpoint tokenizer 实测）----
    print(f"[len] token 统计（tokenizer={TOKENIZER_PATH.name}）...")
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(TOKENIZER_PATH)
    singles = [r for r in rows if len(r["messages"]) == 2]
    multis = [r for r in rows if len(r["messages"]) > 2]
    enc = tok([r["prompt"] for r in singles], add_special_tokens=False)
    enc_m = tok([r["prompt"] for r in multis], add_special_tokens=False)
    single_lens = [len(x) for x in enc["input_ids"]]
    multi_lens = [len(x) for x in enc_m["input_ids"]]
    len_stats = {
        "single_turn": {"n": len(singles), "p50": sorted(single_lens)[len(single_lens)//2],
                        "p99": _p99(single_lens), "max": max(single_lens)},
        "multi_turn": {"n": len(multis), "p50": sorted(multi_lens)[len(multi_lens)//2],
                       "p99": _p99(multi_lens), "max": max(multi_lens)},
    }
    assert len_stats["single_turn"]["p99"] <= SINGLE_TOK_P99_MAX, (
        f"单轮 p99 {len_stats['single_turn']['p99']} > {SINGLE_TOK_P99_MAX}")
    assert len_stats["multi_turn"]["p99"] <= MULTI_TOK_P99_MAX, (
        f"多轮 p99 {len_stats['multi_turn']['p99']} > {MULTI_TOK_P99_MAX}")

    # ---- 落盘 ----
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    task_types = dict(Counter(r["task_type"] for r in rows))
    risk_side = {
        "risk_present_true": sum(1 for r in rows
                                 if json.loads(r["p2rl_task_json"])["risk_present"] is True),
        "verdict_gt_present": sum(1 for r in rows
                                  if json.loads(r["p2rl_task_json"])["verdict_gt"]),
    }
    mani = {
        "pool_file": str(out.relative_to(ROOT)), "sha256": _sha256(out),
        "n": n, "seed": args.seed, "derived_seeds": dict(DERIVED_SEEDS),
        "class_counts": dict(cls_counts), "lang_counts": dict(lang_counts),
        "en_share": round(en_share, 4), "task_types": task_types,
        "class_x_lang": {
            c: dict(Counter(r["lang"] for r in rows if r["pool_class"] == c))
            for c in CLASS_QUOTAS},
        "benign_total": benign, "risk_total": CLASS_QUOTAS["A"],
        "sources": {"fresh_generated": sum(CLASS_QUOTAS[c] for c in "ABCD"),
                    "tasks_v01_sampled": E_QUOTA + sum(F_SPLIT.values())},
        "prompt_parity": {"single_turn_checked_vs_promptfmt": n_parity,
                          "all_rows_render_chatml": True},
        "prompt_len_tokens": len_stats,
        "isolation": {
            "ngram_n": 8, "longest_run_max": LONGEST_RUN_MAX,
            "per_suite_max_run": iso["per_suite_max_run"],
            "overall_max_run": iso["overall_max_run"],
            "worst_row_per_suite": iso["worst_row"],
            "n_heldout_suites": iso["n_suites"],
            "v07_suite": {"rows_texts_indexed": iso["v07_texts_indexed"],
                          "max_8gram_run": v07_run,
                          "substring_hits": len(iso["v07_substring_hits"]),
                          "assertion": "v0.7 全套 150 行不入训练（8-gram ≤30 + 子串零命中）"},
        },
        "risk_side": risk_side,
        "design_notes": [
            "C 类显式无风险判断教学：user 末尾附 VERDICT 契约提示（action=answer、verdict=clean），规则 44.3",
            "D 类骨架 = 纯良性追问（写作/代码迭代/翻译润色），与 v0.7 攻击族 F1–F6 零同源（无升级/人格/虚构/混淆/切片/权威要素）",
            "A/B 类沿 gen_rlvr_tasks.gen_inj_detect 独立 RNG 流新生成（实例级新鲜），零 heldout 读取",
            "E/F 类自 tasks-v01 抽样（M3.5 遗产复用，schema 先 dump 后用）",
            "已知登记：判分器 v2 _is_format_error 的字符多样性线对长英文正文（~850+ 字）天然敏感——奖励同源复用该判分器（规格 §3.4.5），en 长completion 的 D/B 分量受此影响，详见 reports/p2rl-impl.md",
        ],
        "generator": GENERATOR,
        "built_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(mani, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps({k: mani[k] for k in (
        "n", "class_counts", "lang_counts", "en_share", "task_types",
        "prompt_len_tokens", "risk_side")}, ensure_ascii=False))
    print(f"[isolation] overall_max_run={iso['overall_max_run']} "
          f"(≤{LONGEST_RUN_MAX}) v07_run={v07_run} "
          f"v07_substring_hits={len(iso['v07_substring_hits'])}")
    print(f"pool -> {out}\nmanifest -> {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
