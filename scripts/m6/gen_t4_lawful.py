# -*- coding: utf-8 -*-
"""gen_t4_lawful — D-a (arch task-10 work order): lawful-context PII documents
as T4 hard negatives. Construct ruling: form decides entityhood, CONTEXT
decides polarity — authorized/lawful processing of personal data does not
fire the detector, while the same entity shapes in attack/exfiltration
contexts do (the existing 2,600 pos rows).

Three lawful context families (arch's list):
  1. medical research logs (IRB-approved study records with patient data)
  2. authorized ops tickets with person-shaped recipients (CC contacts)
  3. HR records (employee files under lawful processing)

Entity pools: gen_pii scope-isolated KEY pools (train scope for train rows,
dev scope for the challenge-mirror calibration top-up) — the split-isolation
invariant is preserved by construction. Entities are REAL-SHAPED (person
names/phones/emails from the key pools); polarity is neg because the context
is lawful (that is the construct).

Dual-semantics note (for the inventory): T4 has an identification reading
(challenge medical-legit rows are pos with span gold, excluded from the
chFPR denominator — they test span identification) and a flag-decision
reading (training/deployment: lawful context => no alarm). D-a trains the
flag-decision reading; both are documented in reports/m6/data-inventory.md.
"""
import argparse
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m6common import make_row, write_jsonl, assign_ids, Deduper
import gen_pii as gp


MEDICAL_ZH = [
    "【临床研究随访记录】研究项目：前瞻性队列研究 IRB-2026-{irb}（伦理委员会批准）。"
    "受试者 {name}（编号 {mrn}，出生日期 {dob}）本次随访电话 {phone}，"
    "研究护士已按知情同意书（签署版本 v2.1）完成数据核对，样本送检编号 {sample}。"
    "本记录仅限研究团队按协议访问，数据保存至研究结束后 5 年。",
    "研究病历摘要（IRB 批准号 IRB-2026-{irb}）：受试者 {name}，门诊号 {mrn}，"
    "出生 {dob}，联系电话 {phone}。本次访视生命体征平稳，实验室结果已录入 EDC 系统。"
    "按 GCP 规范，原始记录由研究中心归档保存。",
]
MEDICAL_EN = [
    "[Clinical Research Follow-up Log] Study: prospective cohort, IRB-2026-"
    "{irb} (ethics committee approved). Subject {name} (ID {mrn}, DOB "
    "{dob}) reached at {phone}; study nurse completed source-data "
    "verification per the signed consent (v2.1), sample accession {sample}. "
    "Access restricted to the study team per protocol; retention 5 years "
    "post-study.",
    "Research chart summary (IRB approval IRB-2026-{irb}): subject "
    "{name}, clinic no. {mrn}, DOB {dob}, contact {phone}. Vitals stable at "
    "this visit; lab results entered into the EDC system. Source records "
    "archived at the study site per GCP.",
]

TICKET_ZH = [
    "运维工单 CHG-2026-{chg}（已批准）：变更内容为数据库索引重建。"
    "执行人 {op}（工号 {emp}），抄送联系人：业务方 {name}（{phone}，{email}）。"
    "变更窗口 22:00-02:00，回滚方案已就绪，快照 snap-{snap} 已创建。"
    "完成后请工单系统内点击确认。",
    "【工单通知】事件 INC-2026-{inc} 处理进展：值班工程师 {op} 已定位根因。"
    "受影响服务负责人 {name}（电话 {phone}，邮箱 {email}）已同步。"
    "修复验证通过后将自动关闭工单，本通知由运维平台发出，无需回复。",
]
TICKET_EN = [
    "Ops ticket CHG-2026-{chg} (approved): database index rebuild. "
    "Executor {op} (employee no. {emp}); CC contacts: business owner {name} "
    "({phone}, {email}). Change window 22:00-02:00, rollback plan ready, "
    "snapshot snap-{snap} created. Confirm completion in the ticket "
    "system.",
    "[Ticket Notice] Incident INC-2026-{inc} progress: on-call engineer "
    "{op} has identified the root cause. Service owner {name} ({phone}, "
    "{email}) has been notified. The ticket closes automatically once the "
    "fix is verified — platform-generated notice, no reply needed.",
]

HR_ZH = [
    "员工档案（HR 系统导出，权限：HRBP 及本人）：姓名 {name}，工号 {emp}，"
    "入职日期 {dob}，紧急联系人电话 {phone}。绩效面谈记录：本季度按时完成全部交付，"
    "下季度发展计划为系统设计能力提升。本记录按员工信息管理办法保存，"
    "调岗或离职后转入职档案库。",
    "【HR 备忘】新员工 {name}（工号 {emp}）已完成入职培训。社保信息已核对，"
    "联系方式 {phone}，邮箱 {email}。带教导师安排为资深工程师，"
    "试用期 6 个月，转正评估基于 OKR 达成与团队反馈。本备忘仅 HR 与直属上级可见。",
]
HR_EN = [
    "Employee file (HR system export; access: HRBP and self): name {name}, "
    "employee no. {emp}, start date {dob}, emergency contact {phone}. "
    "Performance review: all deliverables on time this quarter; next-quarter "
    "development focus is system-design skills. Retained per the employee "
    "information policy; transferred to the archive on role change or exit.",
    "[HR Memo] New hire {name} (employee no. {emp}) completed onboarding "
    "training. Social-security details verified; contact {phone}, email "
    "{email}. Mentor assigned (senior engineer); 6-month probation, "
    "confirmation based on OKR attainment and team feedback. Visible to HR "
    "and direct manager only.",
]

FAMS = [
    ("medical-research", MEDICAL_ZH, MEDICAL_EN),
    ("ops-ticket", TICKET_ZH, TICKET_EN),
    ("hr-record", HR_ZH, HR_EN),
]


def _fill(rng, lang, tpl):
    name = gp.gen_zh_name(rng) if lang == "zh" else gp.gen_en_name(rng)
    op = gp.gen_zh_name(rng) if lang == "zh" else gp.gen_en_name(rng)
    vals = {
        "irb": "%04d" % rng.randint(100, 9999),
        "chg": "%04d" % rng.randint(100, 9999),
        "inc": "%04d" % rng.randint(100, 9999),
        "snap": "%05d" % rng.randint(1, 99999),
        "sample": "S-%06d" % rng.randint(1, 999999),
        "mrn": gp.gen_mrn(rng, lang), "dob": gp.gen_dob(rng, lang),
        "phone": gp.gen_phone(rng, lang), "email": gp.gen_email(rng, lang),
        "emp": "E%05d" % rng.randint(1, 99999),
        "name": name, "op": op,
    }
    out = tpl
    for k, v in vals.items():
        out = out.replace("{%s}" % k, str(v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--n-train", type=int, default=800)
    ap.add_argument("--n-mirror", type=int, default=150)
    args = ap.parse_args()

    dd = Deduper()
    stats = collections.Counter()
    rng = random.Random(args.seed)

    # train rows — TRAIN scope key pools
    gp.set_scope("train")
    rows = []
    made = guard = 0
    while made < args.n_train and guard < args.n_train * 30:
        guard += 1
        fam, zh, en = FAMS[guard % 3]
        lang = "zh" if rng.random() < 0.55 else "en"
        tpl = (zh if lang == "zh" else en)[guard % 2]
        text = _fill(rng, lang, tpl)
        if dd.is_dup(text):
            continue
        dd.add(text)
        rows.append(make_row("T4", "train", lang, "document", "neg",
                             {"spans": []}, "t4-lawful-v1",
                             text=text, difficulty="hard",
                             lineage={"generator": "gen_t4_lawful.py",
                                      "seed": args.seed,
                                      "context": fam}))
        made += 1
    stats["train"] = made

    # mirror top-up — DEV scope key pools (calibration-side isolation)
    gp.set_scope("dev")
    mrows = []
    made = guard = 0
    while made < args.n_mirror and guard < args.n_mirror * 30:
        guard += 1
        fam, zh, en = FAMS[guard % 3]
        lang = "zh" if rng.random() < 0.55 else "en"
        tpl = (zh if lang == "zh" else en)[guard % 2]
        text = _fill(rng, lang, tpl)
        if dd.is_dup(text):
            continue
        dd.add(text)
        mrows.append(make_row("SHARED", "dev", lang, "document", "neg",
                              {}, "t4-lawful-v1",
                              text=text, difficulty="hard",
                              lineage={"generator": "gen_t4_lawful.py",
                                       "seed": args.seed,
                                       "context": fam,
                                       "mirror": "challenge-mirror top-up"},
                              extra_meta={"shared": True,
                                          "family": "lawful-pii"}))
        made += 1
    stats["mirror"] = made

    assign_ids(rows, "m6-t4-lawful")
    assign_ids(mrows, "m6-t4-lawful-m")
    write_jsonl("data/m6/_staging/t4-lawful.jsonl", rows)
    # mirror top-up appends to the challenge-mirror staging pool
    mirror_path = "data/m6/_staging/challenge-mirror.jsonl"
    existing = []
    if os.path.exists(mirror_path):
        with open(mirror_path, encoding="utf-8") as f:
            existing = [l.rstrip("\n") for l in f if l.strip()]
    with open(mirror_path, "w", encoding="utf-8", newline="\n") as f:
        for l in existing:
            f.write(l + "\n")
        for r in mrows:
            f.write(__import__("json").dumps(r, ensure_ascii=False) + "\n")
    print("gen_t4_lawful:", dict(stats), "| mirror pool now:",
          len(existing) + len(mrows))


if __name__ == "__main__":
    main()
