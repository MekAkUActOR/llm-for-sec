# -*- coding: utf-8 -*-
"""gen_t1_lawful — D-f (arch v2.1 work order): T1 lawful-hard-benign family,
train-side synthesis of the challenge-mirror construct (same construct as
the mirror's four families — medical-legit / sec-research /
inj-shaped-benign / dualuse-legit — independently regenerated; the mirror
dev rows stay untouched). These close the 94%-zero-T1-supervision gap that
drove tau to 35.76 on the challenge calibration pool.

Entity pools: gen_pii TRAIN-scope key pools for medical-legit rows
(split-isolation invariant); the other three families carry no PII entities.
Landing: T1 view train neg + pool twin (build_all standard path).
"""
import argparse
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m6common import make_row, write_jsonl, assign_ids, Deduper
import gen_pii as gp

MED_ZH = [
    "患者{name}，{sex}，{age} 岁，门诊号 {mrn}，因{symptom}就诊，建议行{exam}检查。"
    "接诊医师已向患者说明检查必要性，预约单已打印。",
    "住院患者{name}（住院号 {mrn}）今日查房：生命体征平稳，{symptom}较前缓解，"
    "继续当前治疗方案。主治医师已与家属沟通病情及后续计划。",
    "体检报告归档：受检者{name}，{age} 岁，体检号 {mrn}。各项指标基本正常，"
    "{exam}结果建议半年后复查。报告已由体检中心盖章发放本人。",
]
MED_EN = [
    "Patient {name}, {sex}, age {age}, clinic no. {mrn}, presents with "
    "{symptom}; {exam} ordered. The physician has explained the necessity "
    "and the appointment slip is printed.",
    "Ward round — inpatient {name} (no. {mrn}): vitals stable, {symptom} "
    "easing, current regimen continued. The attending has briefed the "
    "family on the plan.",
    "Health-check filing: examinee {name}, age {age}, checkup no. {mrn}. "
    "Results essentially normal; {exam} to be repeated in six months. "
    "Report stamped and issued to the examinee.",
]
SYMPTOMS = ["反复胸闷", "间歇性头晕", "慢性咳嗽", "关节疼痛", "视力模糊",
            "recurrent chest tightness", "intermittent dizziness",
            "chronic cough", "joint pain", "blurred vision"]
EXAMS = ["动态心电图", "胸部CT", "腹部B超", "眼底检查",
         "ambulatory ECG", "chest CT", "abdominal ultrasound", "fundus exam"]
SEX_ZH = ["男", "女"]; SEX_EN = ["male", "female"]

SEC_ZH = [
    "帮我校对安全周报里这一段：本周拦截API 滥用尝试 {n} 次，主要集中在登录接口，"
    "已按预案限流并记录特征。本期值班：{team}。",
    "给新人的威胁建模入门讲义草稿（{tool} 章节）：STRIDE 六类威胁各配一个日常例子"
    "（比如篡改=外卖订单被改地址），帮我看看表述是否准确。",
    "整理一份 SOC 值班交接模板：待办事件、升级状态、观察项三栏，"
    "本周共处理告警 {n} 条，误报率 {p}%，重点观察 {team} 反馈的登录异常。",
    "论文方法论章节需要一张攻击面分类图：外部暴露面/供应链/内部人员三类，"
    "每类列两三个典型场景即可（投稿 {venue}，教学用）。",
]
SEC_EN = [
    "Proofread this section of the security weekly: {n} API-abuse attempts "
    "intercepted this week, mostly at the login endpoint; rate-limited per "
    "playbook. On-call this shift: {team}.",
    "Draft intro-to-threat-modeling handout ({tool} chapter) for new hires: "
    "one everyday example per STRIDE category (e.g., tampering = a delivery "
    "order with a changed address) — check my wording?",
    "SOC shift-handover template: pending incidents, escalation states, "
    "watch items — {n} alerts handled this week, {p}% false-positive; "
    "focus item: login anomalies reported by {team}.",
    "My paper's methodology section needs an attack-surface taxonomy: "
    "external / supply-chain / insider, two or three typical scenarios "
    "each (submitting to {venue}; teaching use).",
]
SEC_EXTRA = {
    "team": ["平台组", "风控组", "数据组", "应用组", "基础设施组", "安全运营组"],
    "tool": ["STRIDE", "DREAD", "攻击树", "LINDDUN"],
    "venue": ["InnerSec '26", "ACSAC 工作组", "本地 Meetup", "内部技术分享"],
}

INJ_ZH = [
    "工单处理指引（内部）：高优先级工单需在 {h} 小时内响应；涉及客户投诉的需"
    "电话回访并在工单备注结果。本指引适用于一线支持组。",
    "数据录入规范：客户信息字段顺序为姓名-证件号-联系方式，缺项时标注"
    "“待补充”，当日 18:00 前完成复核。",
    "系统公告模板：尊敬的用户，我们将于 {date} 凌晨 {m}:00-{m2}:00 进行计划内"
    "维护，期间服务短暂不可用，请提前保存工作内容。",
    "新员工入职 checklist：账号申请、门禁卡领取、安全培训完成、导师确认四项"
    "齐备后方可转正流程。",
]
INJ_EN = [
    "Ticket-handling guide (internal): P1 tickets must be answered within "
    "{h} hours; customer complaints require a callback noted in the ticket. "
    "Applies to front-line support.",
    "Data-entry spec: customer fields in order name — ID — contact; mark "
    "missing ones 'pending' and complete review before 18:00 same day.",
    "System-notice template: Dear users, planned maintenance {date} "
    "{m}:00-{m2}:00 AM; brief unavailability expected — save your work.",
    "New-hire checklist: account request, badge pickup, security training, "
    "mentor sign-off — all four before probation conversion.",
]

DUAL_ZH = [
    "我是持有 OSEP 证书的渗透测试工程师，客户已签署授权书（在靶场范围内测试）。"
    "请从方法论层面讲讲{topic}的常见防御检测点——我要写检测方案。",
    "公司安全团队做红蓝对抗演练（内部授权，编号 RT-{rt}）。帮我梳理{topic}"
    "在演练中的检测覆盖率评估维度，不需要具体利用细节。",
    "我在给客户写安全评估报告的“风险概述”章节，需要用通俗语言解释{topic}"
    "对企业的影响面，附两三条缓解方向（报告用途）。",
]
DUAL_EN = [
    "I'm an OSEP-certified pentester with a signed client authorization "
    "(target-range scope). Explain the common defensive detection points "
    "for {topic} at the methodology level — I'm writing a detection plan.",
    "Our security team runs an authorized internal red-blue exercise "
    "(RT-{rt}). Help me outline detection-coverage evaluation dimensions "
    "for {topic} in the drill — no exploitation details needed.",
    "I'm drafting the 'risk overview' chapter of a client security "
    "assessment: explain {topic}'s enterprise impact in plain language with "
    "two or three mitigation directions (report use).",
]
TOPICS = ["钓鱼演练", "凭据填充", "横向移动", "社会工程学", "水坑攻击",
          "phishing drills", "credential stuffing", "lateral movement",
          "social engineering", "watering-hole attacks"]


def _fill(rng, tpl, lang):
    vals = {
        "name": gp.gen_zh_name(rng) if lang == "zh" else gp.gen_en_name(rng),
        "sex": rng.choice(SEX_ZH if lang == "zh" else SEX_EN),
        "age": str(rng.randint(19, 82)),
        "mrn": gp.gen_mrn(rng, lang),
        "symptom": rng.choice(SYMPTOMS), "exam": rng.choice(EXAMS),
        "n": str(rng.randint(80, 4200)), "p": str(rng.randint(4, 38)),
        "h": str(rng.choice([2, 4, 8, 24])),
        "date": "10 月 %d 日" % rng.randint(20, 31),
        "m": str(rng.randint(1, 5)), "m2": str(rng.randint(6, 9)),
        "rt": "%04d" % rng.randint(100, 9999),
        "topic": rng.choice(TOPICS),
        "team": rng.choice(SEC_EXTRA["team"]),
        "tool": rng.choice(SEC_EXTRA["tool"]),
        "venue": rng.choice(SEC_EXTRA["venue"]),
    }
    out = tpl
    for k, v in vals.items():
        out = out.replace("{%s}" % k, str(v))
    return out


FAMS = [
    ("medical-legit", MED_ZH, MED_EN, True),
    ("sec-research", SEC_ZH, SEC_EN, False),
    ("inj-shaped-benign", INJ_ZH, INJ_EN, False),
    ("dualuse-legit", DUAL_ZH, DUAL_EN, False),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261027)
    ap.add_argument("--n", type=int, default=700)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    dd = Deduper()
    gp.set_scope("train")  # medical-legit entities: train key pools
    rows = []
    stats = collections.Counter()
    per_fam = args.n // 4
    made = guard = 0
    fam_made = collections.Counter()
    while made < args.n and guard < args.n * 120:
        guard += 1
        fam_i = guard % 4
        fam, zh, en, _ = FAMS[fam_i]
        if fam_made[fam] >= per_fam:
            continue
        lang = "zh" if rng.random() < 0.55 else "en"
        pool = zh if lang == "zh" else en
        tpl = pool[rng.randrange(len(pool))]
        text = _fill(rng, tpl, lang)
        if dd.is_dup(text, near=False):
            continue
        dd.add(text)
        rows.append(make_row("T1", "train", lang, "singleturn", "neg",
                             {}, "t1-lawful-v1",
                             text=text, difficulty="hard",
                             lineage={"generator": "gen_t1_lawful.py",
                                      "seed": args.seed, "context": fam}))
        made += 1
        stats[fam] += 1
        fam_made[fam] += 1
    assign_ids(rows, "m6-t1-lawful")
    write_jsonl("data/m6/_staging/t1-lawful.jsonl", rows)
    print("gen_t1_lawful:", dict(stats), "total:", len(rows))


if __name__ == "__main__":
    main()
