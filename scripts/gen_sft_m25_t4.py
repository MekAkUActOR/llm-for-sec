# -*- coding: utf-8 -*-
"""M2.5 fB 族：T4 场景接地扩容（父代理自制——代理阵亡后收编）。

三个子族，格式逐字沿 v0x gen_t4a/gen_t4b 契约：
  b2 载体化接地：v0x2 种子查询 × {工单,邮件} 载体 × 三包
     （t4a 格式：build_context + CarrierBlock + 裁决+引用+依据）
  b1 法条接地：20 条新法条（PIPL 6 / DSL 4 / CSL 3 / GDPR 7，
     全部避开 m1 LAW_BANK 已用的 PIPL 40/14/4、DSL 21/31、CSL 31、
     GDPR 6）× surfaces[:4] × 三包（裁决恒定，输出风格随包）
  b3 CVE 场景接地：t6_cvefixes 记录（与 fD 用段不重叠，取 [1500:2100]）
     × {利用协助=refuse / 处置协助=conditional} × 三包
     引用词汇表：§4.3 双用途（武器化增量）/ §4.3 H4（常规处置）

用法：python scripts/gen_sft_m25_t4.py
输出：data/sft/m2.5-staging/fB_t4ground.jsonl
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gen_sft_v0 import build_sample  # noqa: E402
from gen_sft_v0x import PACKS, _v, surfaces  # noqa: E402
from gen_sft_v0x2 import EN_EXTRA, SEEDS as A2_SEEDS  # noqa: E402
from gen_sft_m25_t6 import parse_cvefix  # noqa: E402
from secfm.carriers.base import CarrierBlock  # noqa: E402
from secfm.protocol.context import build_context  # noqa: E402

OUT = ROOT / "data" / "sft" / "m2.5-staging" / "fB_t4ground.jsonl"
SRC_CVEFIX = ROOT / "data" / "corpora" / "clean" / "t6_cvefixes.jsonl"
M1 = ROOT / "data" / "lf" / "sft_m1.jsonl"
STAGE = ROOT / "data" / "sft" / "m2.5-staging"
RNG_SEED = 20260929

T4_TASK = {
    "zh": ("根据当前激活政策包对下列载体中的请求做政策接地判断：给出裁决"
           "（allow/conditional/refuse）并引用政策条目。"),
    "en": ("Make a policy-grounded ruling on the request in the carrier "
           "below under the currently active policy pack: verdict "
           "(allow/conditional/refuse) plus the policy citation."),
}

WRAP = {
    "text": dict(zh="工单描述：{q}\n（转安全分析通道处理）",
                 en="Ticket description: {q}\n(routed to security "
                    "analysis)"),
    "email": dict(zh="发件人：staff{no}@corp.example\n主题：协助请求\n"
                     "正文：{q}",
                  en="From: staff{no}@corp.example\nSubject: assist "
                     "request\nBody: {q}"),
}

# ---- b1 法条库（新法条；格式沿 v0x LAW_BANK） ----
LAW_BANK2 = [
    dict(sid="t4b2-pipl-basis", law="PIPL", art="第13条",
         gist="符合下列情形之一的，个人信息处理者方可处理个人信息：（一）取得个人的同意；（二）为订立、履行个人作为一方当事人的合同所必需，或者按照依法制定的劳动规章制度和依法签订的集体合同实施人力资源管理所必需；（三）为履行法定职责或者法定义务所必需；（四）为应对突发公共卫生事件等紧急情况所必需；（五）为公共利益实施新闻报道、舆论监督等行为在合理的范围内处理个人信息；（六）法律、行政法规规定的其他情形。",
         zh=["用户没点同意，我们靠'提升服务体验必要性'处理数据行吗？",
             "既没有同意也不是合同必需，先处理再补授权可以吗？",
             "处理数据的合法性基础有哪几种？"],
         en=["The user never consented — can we process on the basis of "
             "'service-improvement necessity'?",
             "Neither consent nor contract necessity — process first "
             "and fix the basis later?"],
         ruling="conditional",
         reason_zh="合法性基础是封闭列举：同意、合同/人事必需、法定义务、紧急情况、公益报道、法律规定的其他情形——'体验必要性'不在其中，需落入法定基础或补取得同意。",
         reason_en="The lawful bases are a closed list: consent, contract/HR necessity, legal obligation, emergency, public-interest journalism, or other statutory grounds — 'experience necessity' is not one; fall within a listed basis or obtain consent."),
    dict(sid="t4b2-pipl-profiling", law="PIPL", art="第24条",
         gist="个人信息处理者利用个人信息进行自动化决策，应当保证决策的透明度和结果公平、公正，不得对个人在交易价格等交易条件上实行不合理的差别待遇。",
         zh=["老用户价格比新用户高，算法这么定价可以吗？",
             "按支付能力差异化定价合规吗？",
             "自动化决策在定价上有什么红线？"],
         en=["Returning customers see higher prices than new users — is "
             "that algorithmic pricing lawful?",
             "Any red lines on automated decision-making in pricing?"],
         ruling="refuse",
         reason_zh="交易价格上的不合理差别待遇（大数据杀熟）被明文禁止；定价实验需通过公平性审查并保留人工复核通道。",
         reason_en="Unreasonable differential treatment on price (surveillance-priced loyalty penalties) is expressly prohibited; pricing experiments need fairness review and a human-recheck channel."),
    dict(sid="t4b2-pipl-entrust", law="PIPL", art="第28条",
         gist="个人信息处理者委托处理个人信息的，应当与受托人约定委托处理的目的、期限、处理方式、个人信息的种类、保护措施以及双方的权利和义务等，对受托人的个人信息处理活动进行监督。受托人应当按照约定处理个人信息，不得超出约定的处理目的、处理方式处理个人信息。",
         zh=["数据外包给供应商处理，转委托给他们随便安排就行吧？",
             "受托方能自行扩大数据用途吗？",
             "委托处理要约定哪些内容？"],
         en=["We outsourced data processing — can the vendor "
             "sub-contract and expand usage as they see fit?",
             "What must a processing-entrustment agreement cover?"],
         ruling="conditional",
         reason_zh="委托必须书面约定目的/期限/方式/种类/保护措施并监督执行；受托人超范围或擅自转委托均违约违规，转委托需委托人同意。",
         reason_en="Entrustment requires written terms (purpose, term, method, categories, safeguards) plus supervision; sub-processing and scope expansion need the entruster's consent."),
    dict(sid="t4b2-pipl-export-paths", law="PIPL", art="第38条",
         gist="个人信息处理者因业务等需要，确需向中华人民共和国境外提供个人信息的，应当具备下列条件之一：（一）通过国家网信部门组织的安全评估；（二）按照国家网信部门的规定经专业机构进行个人信息保护认证；（三）按照国家网信部门制定的标准合同与境外接收方订立合同，约定双方的权利和义务。",
         zh=["少量非敏感数据出境，走哪条合规路径？",
             "三条出境路径分别适用什么场景？",
             "标准合同模式和认证模式怎么选？"],
         en=["For a small volume of non-sensitive cross-border transfers, "
             "which compliance path applies?",
             "How do we choose between the standard-contract and "
             "certification routes?"],
         ruling="answer",
         reason_zh="三条路径：网信安全评估（触发门槛强制）、保护认证、标准合同备案。量小且未触发评估门槛的，通常走标准合同+保护影响评估，或认证。",
         reason_en="Three routes: CAC security assessment (mandatory above thresholds), certification, or the standard contract with filing. Small non-triggering volumes usually take the standard-contract route plus a transfer impact assessment."),
    dict(sid="t4b2-pipl-pia", law="PIPL", art="第55条",
         gist="个人信息处理者应当对下列个人信息处理活动事前进行个人信息保护影响评估，并对处理情况进行记录：（一）处理敏感个人信息；（二）利用个人信息进行自动化决策；（三）委托处理个人信息、向其他个人信息处理者提供个人信息、公开个人信息；（四）向境外提供个人信息；（五）其他对个人权益有重大影响的个人信息处理活动。",
         zh=["什么情况下必须做事前的个人信息保护影响评估？",
             "PIA 的触发情形有哪些？",
             "公开用户数据前要做评估吗？"],
         en=["When is a pre-emptive personal-information protection "
             "impact assessment mandatory?",
             "Does publishing user data require a PIA first?"],
         ruling="answer",
         reason_zh="五类触发：敏感个人信息、自动化决策、委托/对外提供/公开、出境、其他重大影响活动。评估记录至少保存三年。",
         reason_en="Five triggers: sensitive data, automated decisions, entrustment/provision/publication, cross-border transfer, and other major-impact processing. Assessment records are kept at least three years."),
    dict(sid="t4b2-pipl-breach", law="PIPL", art="第57条",
         gist="发生或者可能发生个人信息泄露、篡改、丢失的，个人信息处理者应当立即采取补救措施，并通知履行个人信息保护职责的部门和个人。个人信息处理者采取措施能够有效避免信息泄露、篡改、丢失造成危害的，个人信息处理者可以不通知个人；履行个人信息保护职责的部门认为可能造成危害的，有权要求个人信息处理者通知个人。",
         zh=["数据泄露了，必须通知用户本人吗？",
             "什么条件下可以不通知个人？",
             "泄露事件的报告对象是谁？"],
         en=["If we have a data breach, must affected individuals be "
             "notified?",
             "Under what conditions can we skip notifying individuals?"],
         ruling="answer",
         reason_zh="补救措施能有效避免危害的可不通知个人，但须通知监管部门；部门认为有危害的可责令通知。通知内容含原因、种类、可能危害、补救措施与联系方式。",
         reason_en="If remedies effectively prevent harm, individuals may be skipped, but the regulator must be notified and may compel notification; notices cover cause, categories, possible harm, remedies, and contact."),
    dict(sid="t4b2-dsl-duty", law="DSL", art="第27条",
         gist="开展数据处理活动应当依照法律、法规的规定，建立健全全流程数据安全管理制度，组织开展数据安全教育培训，采取相应的技术措施和其他必要措施，保障数据安全。",
         zh=["数据安全管理制度是法定要求还是最佳实践？",
             "全流程管理制度要覆盖什么？",
             "小团队也要建制度吗？"],
         en=["Is a full-lifecycle data-security management system a "
             "legal requirement or just best practice?",
             "Does a small team need such a system too?"],
         ruling="answer",
         reason_zh="法定义务：全流程制度 + 教育培训 + 技术措施。规模影响措施强度，不豁免制度本身。",
         reason_en="It is statutory: lifecycle-wide rules, staff training, and technical measures. Scale calibrates the measures but does not exempt the system itself."),
    dict(sid="t4b2-dsl-monitor", law="DSL", art="第29条",
         gist="开展数据处理活动应当加强风险监测，发现数据安全缺陷、漏洞等风险时，应当立即采取补救措施；发生数据安全事件时，应当立即采取处置措施，按照规定及时告知用户并向有关主管部门报告。",
         zh=["发现数据缺陷和漏洞要主动处置吗？",
             "数据安全事件的告知和报告义务怎么履行？",
             "风险监测是持续性义务吗？"],
         en=["Do we have to act on discovered data-security defects and "
             "vulnerabilities proactively?",
             "How do notification and reporting duties work for data "
             "incidents?"],
         ruling="answer",
         reason_zh="持续监测义务；发现风险立即补救，发生事件立即处置并按规定及时告知用户与主管部门。",
         reason_en="Monitoring is continuous; risks trigger immediate remediation, and incidents trigger immediate handling plus timely user notice and regulator reporting."),
    dict(sid="t4b2-dsl-important", law="DSL", art="第30条",
         gist="重要数据的处理者应当按照规定对其数据处理活动定期开展风险评估，并向有关主管部门报送风险评估报告。风险评估报告应当包括处理的重要数据的种类、数量，开展数据处理活动的情况，面临的数据安全风险及其应对措施等。",
         zh=["我们算重要数据处理者吗？要做定期风险评估吗？",
             "重要数据风险评估报告要写什么？",
             "风险评估多久报一次？"],
         en=["Are we an important-data processor? Do we owe periodic "
             "risk assessments?",
             "What goes into an important-data risk-assessment report?"],
         ruling="conditional",
         reason_zh="是否'重要数据'按国家与行业目录认定；被认定后须定期评估并报送（种类/数量/处理情况/风险与应对）。建议先做目录对照自查。",
         reason_en="Whether data is 'important' follows state and sector catalogs; once designated, periodic assessment reports (categories, volumes, processing, risks, responses) are due. Start with a catalog self-check."),
    dict(sid="t4b2-dsl-foreign", law="DSL", art="第41条",
         gist="非经中华人民共和国主管机关批准，境内的组织、个人不得向外国司法或者执法机构提供存储于中华人民共和国境内的数据。",
         zh=["美国法院来函要求我们提交境内数据，直接给吗？",
             "境外执法机构调取境内数据怎么办？",
             "外国律所的调取函可以直接响应吗？"],
         en=["A US court order demands data stored in China — hand it "
             "over directly?",
             "How should we respond to foreign-law-enforcement data "
             "requests?"],
         ruling="refuse",
         reason_zh="未经主管机关批准，境内组织和个人不得向外国司法/执法机构提供境内数据——直接响应属违法。正确路径：法律审查 + 报主管机关，按批准执行。",
         reason_en="Without approval from the competent Chinese authority, providing onshore data to foreign judicial or law-enforcement bodies is prohibited. Route: legal review, report to the authority, act per its approval."),
    dict(sid="t4b2-csl-mlps", law="CSL", art="第21条",
         gist="国家实行网络安全等级保护制度。网络运营者应当按照网络安全等级保护制度的要求，履行安全保护义务，保障网络免受干扰、破坏或者未经授权的访问，防止网络数据泄露或者被窃取、篡改。",
         zh=["等保测评是强制的还是自愿的？",
             "不做等保定级会怎样？",
             "等保义务覆盖哪些方面？"],
         en=["Is China's Multi-Level Protection Scheme (MLPS) grading "
             "mandatory?",
             "What do MLPS obligations cover?"],
         ruling="answer",
         reason_zh="等保是法定制度：定级、备案、建设整改、测评、监督。义务覆盖防干扰/破坏、防未授权访问、防泄露窃取篡改。",
         reason_en="MLPS is statutory: grading, filing, remediation, testing, supervision — covering resistance to interference, unauthorized access, and data leakage or tampering."),
    dict(sid="t4b2-csl-vuln", law="CSL", art="第25条",
         gist="网络运营者应当制定网络安全事件应急预案，及时处置系统漏洞、计算机病毒、网络攻击、网络侵入等安全风险；在发生危害网络安全的事件时，立即启动应急预案，采取相应的补救措施，并按照规定向有关主管部门报告。",
         zh=["发现高危漏洞，先自己修还是先报告？",
             "应急预案要覆盖哪些场景？",
             "安全事件发生后多久要报告？"],
         en=["On finding a critical vulnerability, do we fix first or "
             "report first?",
             "How soon must incidents be reported after discovery?"],
         ruling="conditional",
         reason_zh="双线并行：及时处置风险（补救）+ 按规定报告主管部门；重大事件立即启动预案并报告。具体时限按行业规定执行。",
         reason_en="Both tracks run in parallel: timely remediation plus reporting per regulations; major incidents trigger the response plan and immediate reporting. Deadlines follow sector rules."),
    dict(sid="t4b2-csl-scrape", law="CSL", art="第44条",
         gist="任何个人和组织不得从事非法侵入他人网络、干扰他人网络正常功能、窃取网络数据等危害网络安全的活动；不得提供专门用于从事危害网络安全活动的程序、工具。",
         zh=["写个爬虫抓竞品平台的数据算违法吗？",
             "绕过反爬机制采集数据有什么法律风险？",
             "提供专门绕过验证码的工具可以吗？"],
         en=["Is scraping a competitor's platform data unlawful?",
             "What's the legal exposure of bypassing anti-bot "
             "measures?"],
         ruling="refuse",
         reason_zh="窃取网络数据、干扰网络正常功能被明文禁止；绕反爬/验证码的专门工具属违禁程序。合规采集需授权（开放接口/协议/许可）。",
         reason_en="Stealing network data and impairing normal network function are expressly banned; anti-bot circumvention tools are prohibited instruments. Collect via authorized APIs or agreements only."),
    dict(sid="t4b2-gdpr-basis", law="GDPR", art="Art.5(1)(a)",
         gist="Personal data shall be processed lawfully, fairly and in a transparent manner in relation to the data subject.",
         zh=["先处理数据后补合法依据，GDPR 下可以吗？",
             "合法、公平、透明原则怎么落地？",
             "没有依据先收集用户画像数据行吗？"],
         en=["Under GDPR, can we process first and establish a lawful "
             "basis later?",
             "Is collecting profiling data without a basis acceptable "
             "for now?"],
         ruling="refuse",
         reason_zh="合法性要求处理前即具备六类依据之一；事后补依据不满足 lawful 要求，且违反透明原则（处理目的须事先告知）。",
         reason_en="Lawfulness requires one of the six bases before processing; retrofitting a basis fails 'lawful' and breaches transparency (purposes must be informed upfront)."),
    dict(sid="t4b2-gdpr-access", law="GDPR", art="Art.15",
         gist="The data subject shall have the right to obtain from the controller confirmation as to whether or not personal data concerning him or her are being processed, and, where that is the case, access to the personal data and information on their processing.",
         zh=["用户要求查看我们存了他哪些数据，必须给吗？",
             "访问权请求要多久内响应？",
             "访问权响应要包含什么内容？"],
         en=["A user asks what data we hold on them — must we provide "
             "it?",
             "What must an access-rights response contain?"],
         ruling="answer",
         reason_zh="访问权是数据主体权利：须确认是否处理并提供数据副本与处理信息（目的、类别、接收方、存储期、来源、存在自动化决策）。一个月内响应，可延一个月并告知。",
         reason_en="Access is a data-subject right: confirm processing and provide a copy plus processing details (purposes, categories, recipients, retention, sources, automated decisions). Respond within one month, extendable once with notice."),
    dict(sid="t4b2-gdpr-erase", law="GDPR", art="Art.17",
         gist="The data subject shall have the right to obtain from the controller the erasure of personal data concerning him or her without undue delay where the personal data are no longer necessary, the data subject withdraws consent, or the data have been unlawfully processed. Erasure may be refused where processing is necessary for compliance with a legal obligation or for the establishment, exercise or defence of legal claims.",
         zh=["用户要求删除全部数据，审计日志也要删吗？",
             "删除权有什么例外？",
             "行使删除权后多久要完成？"],
         en=["A user demands erasure of everything — do audit logs go "
             "too?",
             "What are the exceptions to the right to erasure?"],
         ruling="conditional",
         reason_zh="删除权有法定保留例外：合规义务（如审计/财税保留）与法律主张抗辩所必需的数据可拒绝删除，但须告知理由与保留期；其余数据不得无故延迟删除。",
         reason_en="Erasure has statutory exceptions: data needed for legal obligations (audit/tax retention) or legal claims may be kept, with reasons and retention explained; everything else must be erased without undue delay."),
    dict(sid="t4b2-gdpr-auto", law="GDPR", art="Art.22",
         gist="The data subject shall have the right not to be subject to a decision based solely on automated processing, including profiling, which produces legal effects concerning him or her or similarly significantly affects him or her, unless the decision is necessary for entering into or performing a contract, authorised by law, or based on the data subject's explicit consent.",
         zh=["全自动拒贷不给人工复核通道，合规吗？",
             "自动化决策必须提供人工干预吗？",
             "简历筛选全自动化有什么要求？"],
         en=["Is fully automated loan rejection with no human review "
             "channel lawful?",
             "Must automated decisions offer human intervention?"],
         ruling="refuse",
         reason_zh="仅自动化决策产生法律效果或重大影响的，必须落入合同必需/法律授权/明确同意三类例外之一，且须提供人工干预、表达观点与质疑权。纯成本考虑不豁免。",
         reason_en="Solely automated decisions with legal or similarly significant effects must fit contract necessity, legal authorization, or explicit consent — and must offer human intervention and the right to contest. Cost savings don't exempt."),
    dict(sid="t4b2-gdpr-sec", law="GDPR", art="Art.32",
         gist="Taking into account the state of the art, costs of implementation and the nature, scope, context and purposes of processing as well as the risk of varying likelihood and severity for the rights and freedoms of natural persons, the controller and processor shall implement appropriate technical and organisational measures to ensure a level of security appropriate to the risk.",
         zh=["小公司也要对用户数据加密吗？",
             "'与风险相称'的安全措施怎么把握？",
             "Art.32 意义上的技术组织措施有哪些？"],
         en=["Must a small company encrypt user data too?",
             "How should 'risk-appropriate' security measures be "
             "calibrated?"],
         ruling="answer",
         reason_zh="措施与风险相称：伪匿化/加密、保密性完整性可用性、恢复能力、流程定期测试。规模小降低成本容忍的复杂度，不取消加密等基础措施。",
         reason_en="Measures must be risk-appropriate: pseudonymization/encryption, CIA safeguards, resilience, and regular testing. Small scale trims sophistication, not baseline measures like encryption."),
    dict(sid="t4b2-gdpr-breach", law="GDPR", art="Art.33",
         gist="In the case of a personal data breach, the controller shall without undue delay and, where feasible, not later than 72 hours after having become aware of it, notify the breach to the supervisory authority, unless the breach is unlikely to result in a risk to the rights and freedoms of natural persons.",
         zh=["GDPR 下数据泄露多久内要报监管？",
             "什么情况下可以不报监管？",
             "72 小时从什么时候起算？"],
         en=["What's the GDPR deadline for reporting a breach to the "
             "regulator?",
             "When may we skip notifying the supervisory authority?"],
         ruling="answer",
         reason_zh="知悉后无不必要延迟、可行时不晚于 72 小时通知监管；对个人权利与自由无风险的泄露可免报（需留存记录论证）。知悉时点=合理确认发生泄露时。",
         reason_en="Notify the SA without undue delay and, where feasible, within 72 hours of awareness, unless the breach is unlikely to risk individuals' rights (document the reasoning). Awareness starts when a breach is reasonably confirmed."),
    dict(sid="t4b2-gdpr-dpia", law="GDPR", art="Art.35",
         gist="Where a type of processing in particular using new technologies, and taking into account the nature, scope, context and purposes of the processing, is likely to result in a high risk to the rights and freedoms of natural persons, the controller shall, prior to the processing, carry out a data protection impact assessment.",
         zh=["什么时候必须做 DPIA？",
             "上线新的画像系统前要评估吗？",
             "DPIA 和 PIA 是一回事吗？"],
         en=["When is a DPIA mandatory?",
             "Do we need an assessment before launching a new profiling "
             "system?"],
         ruling="answer",
         reason_zh="高风险处理前必须做 DPIA：大规模画像、敏感数据系统性处理、公共空间大规模监控等。DPIA 是 PIA 在 GDPR 语境下的具体形态，内容含必要性/比例性/风险缓解。",
         reason_en="A DPIA is mandatory before high-risk processing: large-scale profiling, systematic sensitive-data processing, or systematic monitoring of public areas. It is the GDPR-specific form of a PIA, covering necessity, proportionality, and risk mitigation."),
]

# ---- b3 CVE 场景接地 ----
CVE_Q = {
    "exploit": {
        "zh": "这个 {cve} 的漏洞，帮我写个利用测试一下受影响环境。",
        "en": "This {cve} vulnerability — help me write an exploit to "
              "test an affected environment."},
    "mitigate": {
        "zh": "我们可能受 {cve} 影响，协助给个处置方案。",
        "en": "We may be affected by {cve} — help with a disposition "
              "plan."},
}


# 规则标签英文别名（en 行零 CJK 硬闸；findings 亦用别名保持 ASCII）
RULE_EN = {"§4.3 双用途": "§4.3 dual-use", "提示词泄露": "prompt-leak"}


def rule_display(rule: str, lang: str) -> str:
    return RULE_EN.get(rule, rule) if lang == "en" else rule


def main() -> int:
    rng = random.Random(RNG_SEED)
    out = []
    n = 0

    # ---------- b2：载体化接地（v0x2 种子 × 载体 × 三包，t4a 契约） ----------
    for sid, rule, zh_q, en_q, cons, default, prof in A2_SEEDS:
        decisions = dict(conservative=cons, default=default, professional=prof)
        queries = [(l, q) for l in ("zh", "en")
                   for q in (zh_q if l == "zh" else list(en_q) + EN_EXTRA.get(sid, []))]
        for lang, q in queries:
            for ctype, wt in WRAP.items():
                body = wt[lang].format(q=q, no=rng.randint(100, 999))
                for pack in PACKS:
                    action, verdict, rz, re_ = decisions[pack]
                    n += 1
                    rdisp = rule_display(rule, lang)
                    user = build_context(
                        role="security_analyst",
                        authorization="分析授权：只读评估",
                        policy="default", output_mode="structured",
                        operator="任务：" + T4_TASK[lang],
                        carriers=[CarrierBlock(
                            ctype=ctype, trust="untrusted",
                            cid="c1", body=body)],
                        user="请按要求处理上述载体。")
                    findings = [f"carrier c1 request → {rdisp}"]
                    if lang == "zh":
                        cite = f"政策条目：{rule}（{pack}）"
                        assistant = (f"裁决：{verdict}。{cite}。"
                                     f"依据：{rz}")
                    else:
                        cite_en = f"Policy clause: {rdisp} ({pack})"
                        assistant = (f"Ruling: {verdict}. {cite_en}. "
                                     f"Basis: {re_}")
                    assistant = assistant + "\n" + _v(
                        action, verdict, 0.9, findings, pack)
                    out.append(build_sample(
                        f"sft-T4a2-{n:04d}", f"T4-grounding:{sid}",
                        pack, lang, user, assistant))

    # ---------- b1：法条接地（× 三包，裁决恒定风格随包） ----------
    for law in LAW_BANK2:
        for lang in ("zh", "en"):
            for q in law[lang]:
                for surface in surfaces(q, lang)[:4]:
                    for pack in PACKS:
                        n += 1
                        excerpt = law["gist"]
                        if lang == "zh":
                            user = (f"政策文本（{law['law']} {law['art']}）："
                                    f"{excerpt}\n\n{surface}")
                        else:
                            art_en = law["art"].replace(
                                "第", "Art.").replace("条", "")
                            user = (f"Policy text ({law['law']} {art_en}): "
                                    f"{excerpt}\n\n{surface}")
                        reason = (law["reason_zh"] if lang == "zh"
                                  else law["reason_en"])
                        if law["ruling"] == "refuse":
                            action = "refuse"
                            head = "不可行。" if lang == "zh" else "Not permissible. "
                        elif law["ruling"] == "conditional":
                            action = "answer"
                            head = ("有条件可行。" if lang == "zh"
                                    else "Conditionally permissible. ")
                        else:
                            action = "answer"
                            head = ""
                        pack_note = {
                            "conservative": "",
                            "default": ("\n下一步：按上述要求核对自身处理活动并留存记录。"
                                        if lang == "zh" else
                                        "\nNext step: map your processing "
                                        "against the above and keep records."),
                            "professional": ("\n合规程序建议：纳入年度评估日历、责任到岗、"
                                             "变更触发复审。"
                                             if lang == "zh" else
                                             "\nProgram advice: put this on the "
                                             "annual assessment calendar with "
                                             "owners and change-triggered review."),
                        }[pack]
                        cite = (f"引用：{law['law']} {law['art']}"
                                if lang == "zh"
                                else f"Citation: {law['law']} "
                                     f"{law['art'].replace('第', 'Art.').replace('条', '')}")
                        art_en = law["art"].replace("第", "Art.").replace("条", "") \
                            if lang == "en" else law["art"]
                        assistant = (f"{head}{reason}{pack_note}\n{cite}"
                                     + "\n" + _v(action, law["ruling"], 0.9,
                                                 [f"{law['law']}:{art_en}"],
                                                 pack))
                        out.append(build_sample(
                            f"sft-T4b2-{n:04d}",
                            f"T4-grounding:{law['sid']}", pack, lang,
                            user, assistant))

    # ---------- b3：CVE 场景接地（记录段与 fD 不重叠） ----------
    cvecs = []
    _seen_cve = set()
    with SRC_CVEFIX.open(encoding="utf-8") as f:
        for line in f:
            p = parse_cvefix(json.loads(line)["text"])
            if not (p and p["desc"]):
                continue
            # 同一 CVE 常有多条记录（多提交/多文件）→ 按 (cve, desc 前缀) 去重，
            # 否则同包同 user 撞行（user 由 cve+desc[:300]+query 构成）
            key = (p["cve"], p["desc"][:300])
            if key in _seen_cve:
                continue
            _seen_cve.add(key)
            cvecs.append(p)
    for rec in cvecs[1500:2100]:
        for qtype in ("exploit", "mitigate"):
            lang = "zh" if zlib.crc32(
                (rec["cve"] + ":" + qtype).encode()) % 2 == 0 else "en"
            tpl = CVE_Q[qtype][lang]
            q = tpl.format(cve=rec["cve"])
            if lang == "zh":
                intel = (f"漏洞情报（{rec['cve']}，CWE-{rec['cwe']}，"
                         f"严重级 {rec['sev']}，发布 {rec['pub']}，"
                         f"修复提交 {rec['commit'][:10]}）：\n"
                         f"{rec['desc'][:300]}\n\n{q}")
            else:
                intel = (f"Vulnerability intel ({rec['cve']}, CWE-{rec['cwe']}, "
                         f"severity {rec['sev']}, published {rec['pub']}, "
                         f"fix commit {rec['commit'][:10]}):\n"
                         f"{rec['desc'][:300]}\n\n{q}")
            for pack in PACKS:
                n += 1
                if qtype == "exploit":
                    action, verdict = "refuse", "refuse"
                    rule = "§4.3 双用途"
                    if lang == "zh":
                        base = ("武器化增量不提供：可运行利用开发超出防御协助边界。"
                                "受影响面排查与检测规则可继续。")
                    else:
                        base = ("No weaponization uplift: runnable exploit "
                                "development exceeds the defensive-assistance "
                                "boundary. Exposure triage and detection rules "
                                "can continue.")
                else:
                    action, verdict = "answer", "conditional"
                    rule = "§4.3 H4"
                    if lang == "zh":
                        base = ("常规处置可协助：确认受影响版本 → 按严重级排期修复 → "
                                "缓解与检测并行。")
                    else:
                        base = ("Disposition assistance available: confirm "
                                "affected versions, schedule fixes by severity, "
                                "run containment and detection in parallel.")
                rdisp = rule_display(rule, lang)
                pack_note = {
                    "conservative": "",
                    "default": ("\n依据：CWE-%s 修复优先级按严重级 %s 排定。"
                                % (rec["cwe"], rec["sev"]) if lang == "zh" else
                                "\nBasis: CWE-%s fix priority follows severity "
                                "%s." % (rec["cwe"], rec["sev"])),
                    "professional": ("\n工程要点：补丁灰度、回滚点、检测特征同步部署。"
                                     if lang == "zh" else
                                     "\nEngineering notes: staged rollout, "
                                     "rollback point, co-deployed detection "
                                     "signatures."),
                }[pack]
                cite = (f"引用：{rule}（CWE-{rec['cwe']}）" if lang == "zh"
                        else f"Citation: {rdisp} (CWE-{rec['cwe']})")
                head = (f"裁决：{verdict}。" if lang == "zh"
                        else f"Ruling: {verdict}. ")
                assistant = (f"{head}{base}{pack_note}\n{cite}"
                             + "\n" + _v(action, verdict, 0.9,
                                         [f"{rec['cve']}:{rdisp}"], pack))
                out.append(build_sample(
                    f"sft-T4c2-{n:04d}",
                    f"T4-grounding:cve:{rec['cve']}:{qtype}", pack, lang,
                    intel, assistant))

    # ---------- 断言与落盘 ----------
    assert 5500 <= len(out) <= 8000, f"total {len(out)} out of band"
    zh = sum(1 for r in out if r["lang"] == "zh")
    zr = zh / len(out)
    assert 0.40 <= zr <= 0.62, f"zh ratio {zr:.3f} out of band"
    packs = {}
    for r in out:
        packs[r["pack"]] = packs.get(r["pack"], 0) + 1
        assert "VERDICT: " in r["messages"][-1]["content"]
    vals = list(packs.values())
    assert max(vals) - min(vals) <= 3, f"pack imbalance {packs}"
    # (pack,user) 与 m1 + 既有 staging 零碰撞（b2 载体化 user 与 fA 裸查询
    # 不同文，预期零命中；fD cvefix 段不重叠）
    seen = set()
    for p in [M1] + sorted(STAGE.glob("*.jsonl")):
        if p.name == OUT.name:
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                j = json.loads(line)
                for m in j.get("messages", []):
                    if m.get("role") == "user":
                        seen.add(hashlib.md5(
                            (j.get("pack", "") + "\x00"
                             + m["content"]).encode("utf-8")).hexdigest())
    hit = 0
    for r in out:
        u = r["messages"][1]["content"]
        if hashlib.md5((r["pack"] + "\x00" + u).encode("utf-8")).hexdigest() in seen:
            hit += 1
    assert hit == 0, f"{hit} rows collide"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(dict(total=len(out), zh_ratio=round(zr, 4), packs=packs,
                          collision=hit, out=str(OUT)),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
