# -*- coding: utf-8 -*-
"""gen_t4_lawful_v2 — arch T4 contingency pre-order (STAGING ONLY — deploys
after v2.1 readout if the T4 gap stays >3x): second lawful-context PII
wave with ENTITY-TYPE BALANCING — the v1-2 FP主力 entity classes
(medical_id / person / dob / license_plate) get equal coverage across the
three lawful contexts. mirror top-up 150 -> 300 (dev calibration depth).
Same construct as t4-lawful-v1 (arch context ruling: form decides
entityhood, context decides polarity); key-pool isolation preserved
(train scope for train rows, dev scope for mirror rows).
"""
import argparse
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m6common import make_row, write_jsonl, assign_ids, Deduper
import gen_pii as gp

# entity-type balanced templates: every row carries >=2 of the four主力
# classes (medical_id / person / dob / license_plate)
TPLS_ZH = [
    # medical: mrn + person + dob
    "【门诊随访登记】患者{name}（{sex}，出生{dob}），病历号 {mrn}，本次随访方式：电话。"
    "接诊医师已在系统内确认随访计划，记录归档于电子病历。",
    "【体检中心】受检者{name}，出生日期 {dob}，体检编号 {mrn}。彩超与血检结果已出，"
    "由主检医师复核后出具报告，原件邮寄至登记地址。",
    # ops: person + phone + plate + emp
    "【车辆调度记录】公司车辆（牌照 {plate}）今日由{name}（工号 {emp}）驾驶外出客户现场，"
    "随车联系人电话 {phone}。行程已按行政流程报备，油卡消费并入月度对账。",
    "【门禁登记】访客{name}，联系电话 {phone}，到访事由：设备巡检（随行工程师工号 {emp}）。"
    "访客车辆停在 B2 层 {plate} 车位，登记信息由物业留存三个月。",
    "【运维值班表】本周值班：{name}（{phone}），应急联系工程师 {op}（工号 {emp}）。"
    "值班车辆（{plate}）钥匙在一层前台，交接需双方签字。",
    # hr: person + dob + emp + id-tail + plate
    "【员工档案】{name}，出生 {dob}，工号 {emp}，入职体检编号 {mrn}。"
    "岗位变更申请已由 HRBP 复核，档案按制度转递，员工可在自助端查看流转记录。",
    "【薪酬开户确认】员工{name}（工号 {emp}）的工资卡开户信息已与本人核对，"
    "紧急联系人电话 {phone}。确认单由员工签字后归档，薪酬明细次月可查。",
    "【离职交接】{name}（工号 {emp}，出生 {dob}）离职交接清单：门禁卡、电脑、"
    "工牌已收回；名下公务车（{plate}）已归还车队。交接单三方签字归档。",
]
TPLS_EN = [
    "Follow-up register: patient {name} ({sex}, DOB {dob}), record no. "
    "{mrn}, follow-up by phone. The attending confirmed the plan in the EHR; "
    "note archived to the electronic record.",
    "Health-screening center: examinee {name}, DOB {dob}, screening no. "
    "{mrn}. Ultrasound and blood results are out; the reviewing physician "
    "issues the report, original mailed to the registered address.",
    "Vehicle-dispatch log: company car (plate {plate}) driven today by "
    "{name} (employee no. {emp}) to the client site; in-car contact "
    "{phone}. Trip filed per admin process; fuel card billed monthly.",
    "Visitor register: {name}, contact {phone}, purpose: equipment "
    "inspection (escorting engineer no. {emp}). Visitor car parked at B2 "
    "slot {plate}; records kept by facility for three months.",
    "On-call roster this week: {name} ({phone}), escalation engineer {op} "
    "(no. {emp}). Duty vehicle ({plate}) keys at the front desk; handover "
    "requires both signatures.",
    "Employee file: {name}, DOB {dob}, employee no. {emp}, onboarding "
    "screening no. {mrn}. Role-change request reviewed by the HRBP; the "
    "file transfers per policy, flow visible on the self-service portal.",
    "Payroll-account confirmation: {name} (no. {emp}) verified bank details "
    "in person; emergency contact {phone}. Signed form archived; payroll "
    "detail queryable next month.",
    "Exit handover: {name} (no. {emp}, DOB {dob}) — badge, laptop and ID "
    "returned; company car ({plate}) back to the fleet. Tripartite-signed "
    "handover archived.",
]
SEX_ZH = ["男", "女"]; SEX_EN = ["male", "female"]


def _fill(rng, lang, tpl):
    vals = {
        "name": gp.gen_zh_name(rng) if lang == "zh" else gp.gen_en_name(rng),
        "op": gp.gen_zh_name(rng) if lang == "zh" else gp.gen_en_name(rng),
        "sex": rng.choice(SEX_ZH if lang == "zh" else SEX_EN),
        "dob": gp.gen_dob(rng, lang),
        "mrn": gp.gen_mrn(rng, lang),
        "plate": gp.gen_plate(rng, lang),
        "phone": gp.gen_phone(rng, lang),
        "emp": "E%05d" % rng.randint(1, 99999),
    }
    out = tpl
    for k, v in vals.items():
        out = out.replace("{%s}" % k, str(v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261028)
    ap.add_argument("--n-train", type=int, default=1300)
    ap.add_argument("--n-mirror", type=int, default=300)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    dd = Deduper()
    stats = collections.Counter()

    gp.set_scope("train")
    rows = []
    made = guard = 0
    while made < args.n_train and guard < args.n_train * 60:
        guard += 1
        lang = "zh" if rng.random() < 0.55 else "en"
        pool = TPLS_ZH if lang == "zh" else TPLS_EN
        text = _fill(rng, lang, pool[rng.randrange(len(pool))])
        if dd.is_dup(text, near=False):
            continue
        dd.add(text)
        rows.append(make_row("T4", "train", lang, "document", "neg",
                             {"spans": []}, "t4-lawful-v2",
                             text=text, difficulty="hard",
                             lineage={"generator": "gen_t4_lawful_v2.py",
                                      "seed": args.seed,
                                      "entity_balance": "mrn/person/dob/plate"}))
        made += 1
    stats["train"] = made

    gp.set_scope("dev")
    mrows = []
    made = guard = 0
    while made < args.n_mirror and guard < args.n_mirror * 60:
        guard += 1
        lang = "zh" if rng.random() < 0.55 else "en"
        pool = TPLS_ZH if lang == "zh" else TPLS_EN
        text = _fill(rng, lang, pool[rng.randrange(len(pool))])
        if dd.is_dup(text, near=False):
            continue
        dd.add(text)
        mrows.append(make_row("SHARED", "dev", lang, "document", "neg",
                              {}, "t4-lawful-v2",
                              text=text, difficulty="hard",
                              lineage={"generator": "gen_t4_lawful_v2.py",
                                       "seed": args.seed,
                                       "entity_balance": "mrn/person/dob/plate",
                                       "mirror": "challenge-mirror top-up v2"},
                              extra_meta={"shared": True,
                                          "family": "lawful-pii-v2"}))
        made += 1
    stats["mirror"] = made

    assign_ids(rows, "m6-t4-lawful2")
    assign_ids(mrows, "m6-t4-lawful2-m")
    write_jsonl("data/m6/_staging/t4-lawful-v2.jsonl", rows)
    mirror_path = "data/m6/_staging/challenge-mirror.jsonl"
    existing = []
    if os.path.exists(mirror_path):
        with open(mirror_path, encoding="utf-8") as f:
            existing = [l.rstrip("\n") for l in f if l.strip()]
    import json as _j
    with open(mirror_path, "a", encoding="utf-8", newline="\n") as f:
        for r in mrows:
            f.write(_j.dumps(r, ensure_ascii=False) + "\n")
    print("gen_t4_lawful_v2:", dict(stats), "| mirror pool now:",
          len(existing) + len(mrows))


if __name__ == "__main__":
    main()
