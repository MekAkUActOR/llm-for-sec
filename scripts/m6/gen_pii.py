# -*- coding: utf-8 -*-
"""M6 T4 (PII identification) synthetic corpus generator (dataeng-m6).

Entity type table (aligned with arch ADR 10-class vocabulary):
  person / phone / email / gov_id(resident_id|passport) / address /
  bank_card / credential / dob / license_plate / medical_id

Design notes
------------
- All values are synthetic: real-world formats (18-digit resident ID with
  ISO 7064 MOD 11-2 check digit, Luhn-shaped unionpay cards, 1[3-9] phone
  prefixes, sk-/ghp- credential shapes) but generated from seeded RNG; no
  real person correspondence (manifest documents this).
- Scene slots are semantically typed (recipient=person, address=address...),
  so entities never land in the wrong slot.
- Spans are exact character offsets computed by segment concatenation (Seg).
- Negatives: same scenes with non-PII fillers + near-miss hard negatives
  (fictional/historical names, ISBNs, waybills, hotlines, versions, IPs).
Output: data/m6/_staging/t4-pii.jsonl (unsplit pool with split_hint).
"""
import random
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m6common import Seg, make_row, write_jsonl, assign_ids, Deduper

ENT_TYPES = ["person", "phone", "email", "gov_id", "address", "bank_card",
             "credential", "dob", "license_plate", "medical_id", "other_id"]

# risk tier per type (frozen for SYS-1 vocabulary, 11 classes)
RISK_TIER = {
    "credential": "high", "gov_id": "high", "bank_card": "high",
    "medical_id": "medium", "address": "medium", "phone": "medium",
    "license_plate": "medium", "dob": "medium", "other_id": "medium",
    "person": "low", "email": "low",
}

# ---------------------------------------------------------------- pools
ZH_SURNAMES = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任卢姚沈钟姜崔谭陆范汪石金贾韦夏付方邹熊孟秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤温康施文柯柴倪凌米谷代桂")
ZH_GIVEN_1 = list("伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛明超秀兰霞平刚桂英文辉力健俊峰红玉梅琳素云莲真环雪荣爱妹霞香月莺媛艳瑞凡佳嘉琼勤珍贞莉桂凤洁琪楠")
ZH_GIVEN_2 = ["志强", "建国", "秀英", "淑华", "海燕", "春梅", "雨欣", "子轩", "浩然", "欣怡", "梓涵", "志明", "家豪", "静婷", "俊杰", "雅雯", "思远", "梦琪", "文博", "晓东", "佳怡", "天佑", "美玲", "世杰"]
EN_FIRST = ["James", "Mary", "Robert", "Patricia", "Michael", "Linda", "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Daniel", "Nancy", "Matthew", "Lisa", "Anthony", "Betty", "Mark", "Sandra", "Steven", "Ashley", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle", "Kevin", "Grace", "Brian", "Amanda", "George", "Melissa"]
EN_LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"]

ZH_PINYIN = ["wei", "fang", "na", "lei", "jun", "min", "tao", "jie", "hao", "xin", "yu", "chen", "li", "qiang", "zhang", "wang", "liu", "yang", "huang", "zhao", "wu", "zhou", "xu", "sun", "ma", "zhu", "hu", "guo", "he", "lin", "luo", "zheng"]

PROV_CITY = [
    ("广东省", "深圳市"), ("广东省", "广州市"), ("浙江省", "杭州市"), ("浙江省", "宁波市"),
    ("江苏省", "苏州市"), ("江苏省", "南京市"), ("四川省", "成都市"), ("山东省", "青岛市"),
    ("湖北省", "武汉市"), ("湖南省", "长沙市"), ("河南省", "郑州市"), ("福建省", "厦门市"),
    ("陕西省", "西安市"), ("安徽省", "合肥市"), ("河北省", "石家庄市"), ("辽宁省", "大连市"),
    ("云南省", "昆明市"), ("贵州省", "贵阳市"), ("江西省", "南昌市"), ("重庆市", ""),
    ("北京市", ""), ("上海市", ""), ("天津市", ""),
]
DISTRICTS = ["西湖区", "高新区", "经开区", "朝阳区", "海淀区", "浦东新区", "福田区", "天河区", "锦江区", "雁塔区", "滨湖区", "姑苏区", "玄武区", "雨花区"]
ROADS_ZH = ["人民路", "中山路", "解放大道", "建设路", "幸福里", "望江路", "科技园路", "光明街", "和平大道", "长安街", "文化路", "金融街", "创新大道", "长江路", "珠江路"]
EN_STREETS = ["Maple", "Oak", "Cedar", "Pine", "Elm", "Washington", "Lake", "Hill", "Park", "River", "Sunset", "Highland", "Meadow", "Spring", "Church", "Main", "Willow", "Birch", "Chestnut", "Juniper", "Magnolia", "Aspen", "Cypress", "Dogwood", "Fernwood", "Glenview", "Hawthorn", "Laurel", "Poplar", "Sycamore", "Walnut"]
EN_STREET_TYPES = ["St", "Ave", "Blvd", "Rd", "Ln", "Dr", "Way"]
EN_CITIES = ["Springfield", "Riverside", "Franklin", "Greenville", "Bristol", "Clinton", "Fairview", "Salem", "Madison", "Georgetown", "Arlington", "Ashland"]
EN_STATES = ["CA", "NY", "TX", "FL", "IL", "PA", "OH", "GA", "NC", "WA", "MA", "AZ"]

HOSPITALS_ZH = ["市第一人民医院", "市中心医院", "市中医院", "仁济医院", "市儿童医院", "肿瘤专科医院", "市妇幼保健院"]
HOSPITALS_EN = ["Mercy General Hospital", "St. Mary's Medical Center", "City Hospital", "Riverside Clinic", "Lakeview Medical Center"]
DEPARTMENTS_ZH = ["心内科", "呼吸科", "消化内科", "骨科", "神经外科", "皮肤科", "眼科", "内分泌科", "儿科", "急诊科"]
DEPARTMENTS_EN = ["Cardiology", "Pulmonology", "Orthopedics", "Neurology", "Dermatology", "Endocrinology", "Pediatrics", "Emergency"]

EMAIL_DOMAINS = ["gmail.com", "outlook.com", "qq.com", "163.com", "126.com", "hotmail.com", "foxmail.com", "sina.com", "corp.example.com", "mail.example.org"]
COMPANIES_ZH = ["宏远科技", "蓝海物流", "恒信贸易", "智联教育", "中天建设", "锐捷网络", "华丰制造", "启明咨询"]
COMPANIES_EN = ["Acme Corp", "Bluewave Logistics", "Northgate Trading", "Vertex Systems", "Ironclad Manufacturing", "Lumen Analytics"]
PRODUCTS_ZH = ["智能手表", "空气净化器", "无线耳机", "扫地机器人", "电饭煲", "投影仪", "按摩椅", "咖啡机"]
PRODUCTS_EN = ["smart watch", "air purifier", "wireless earbuds", "robot vacuum", "rice cooker", "projector", "massage chair"]

FICTIONAL_ZH = ["郭靖", "黄蓉", "张三丰", "令狐冲", "赵敏", "林黛玉", "贾宝玉", "孙悟空", "白素贞", "聂小倩"]
FICTIONAL_EN = ["Harry Potter", "Sherlock Holmes", "Elizabeth Bennet", "Katniss Everdeen", "Tony Stark", "Bruce Wayne", "Hermione Granger", "Frodo Baggins"]
HISTORICAL_ZH = ["李白", "杜甫", "苏轼", "李清照", "辛弃疾", "王安石", "白居易", "欧阳修"]
HISTORICAL_EN = ["Napoleon Bonaparte", "Jane Austen", "Abraham Lincoln", "Cleopatra", "Leonardo da Vinci", "Charles Dickens"]


# ---------------------------------------------------------------- generators
import hashlib as _hl


def _bucket(v):
    return int(_hl.sha256(str(v).encode("utf-8")).hexdigest()[:8], 16) % 10


# bucket-KEY pools: exactly one discriminating pool per composed entity is
# bucket-isolated; all other component pools stay shared so in-split diversity
# is preserved while cross-split composition is provably disjoint.
#   person zh: ZH_SURNAMES | person en: EN_LAST
#   address zh: ROADS_ZH  | address en: EN_STREETS
#   dob: year % 10 bucket (inside gen_dob)
# high-entropy randoms (phone/id/card/credential/mrn/plate/zip/room) need no
# isolation — collision probability across splits is negligible.
_BUCKET_KEY_POOLS = ["ZH_SURNAMES", "EN_LAST", "ROADS_ZH", "EN_STREETS"]
_ORIG_POOLS = {n: list(globals()[n]) for n in _BUCKET_KEY_POOLS}
_SCOPE_BUCKETS = set(range(10))


def set_scope(scope):
    """Restrict bucket-key pools to this split's hash buckets (70/20/10)."""
    global _SCOPE_BUCKETS
    _SCOPE_BUCKETS = {"train": set(range(0, 7)), "dev": {7, 8}, "heldout": {9}}[scope]
    for n in _BUCKET_KEY_POOLS:
        pool = _ORIG_POOLS[n]
        globals()[n] = [v for v in pool if _bucket(v) in _SCOPE_BUCKETS]


set_scope("train")  # default: 70% bucket space


def gen_zh_name(rng):
    if rng.random() < 0.5:
        return rng.choice(ZH_SURNAMES) + rng.choice(ZH_GIVEN_1)
    return rng.choice(ZH_SURNAMES) + rng.choice(ZH_GIVEN_2)


def gen_en_name(rng):
    return "%s %s" % (rng.choice(EN_FIRST), rng.choice(EN_LAST))


def gen_phone(rng, lang):
    if lang == "zh":
        if rng.random() < 0.8:
            return "1" + "".join(str(rng.randint(0, 9)) for _ in range(10))
        return "0%d%d-%d%d%d%d%d%d%d%d" % (rng.randint(1, 9), rng.randint(0, 9),
                                           *[rng.randint(0, 9) for _ in range(8)])
    return "+1 (%d%d%d) %d%d%d-%d%d%d%d" % tuple(rng.randint(0, 9) for _ in range(10))


def gen_email(rng, lang):
    dom = rng.choice(EMAIL_DOMAINS)
    if lang == "zh":
        local = rng.choice(ZH_PINYIN) + rng.choice(ZH_PINYIN) + str(rng.randint(1, 999))
    else:
        local = (rng.choice(EN_FIRST) + "." + rng.choice(EN_LAST)).lower().replace(" ", "") + str(rng.randint(1, 99))
    return "%s@%s" % (local, dom)


ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
ID_CHECK = "10X98765432"


def gen_id_card(rng):
    area = rng.choice(["110101", "310104", "440305", "330106", "510107", "320102",
                       "420111", "500103", "610113", "120101"])
    year = rng.randint(1960, 2005)
    body = "%s%04d%02d%02d%03d" % (area, year, rng.randint(1, 12), rng.randint(1, 28),
                                    rng.randint(1, 999))
    s = sum(int(body[i]) * ID_WEIGHTS[i] for i in range(17))
    return body + ID_CHECK[s % 11]


def gen_passport(rng):
    return rng.choice("EG") + "".join(str(rng.randint(0, 9)) for _ in range(8))


def gen_gov_id(rng):
    if rng.random() < 0.7:
        return gen_id_card(rng), "resident_id"
    return gen_passport(rng), "passport"


def gen_bank_card(rng):
    prefix = rng.choice(["621700", "622202", "622260", "621485", "620302", "436742", "402658"])
    length = rng.choice([16, 19])
    body = prefix + "".join(str(rng.randint(0, 9)) for _ in range(length - len(prefix) - 1))
    return body + str(rng.randint(0, 9))


def gen_credential(rng):
    alpha = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    shape = rng.random()
    if shape < 0.25:
        return "Pa$$w0rd%d!" % rng.randint(10000, 99999)
    if shape < 0.5:
        return "sk-" + "".join(rng.choice(alpha) for _ in range(32))
    if shape < 0.7:
        return "ghp_" + "".join(rng.choice(alpha) for _ in range(36))
    if shape < 0.85:
        return "Bearer eyJ" + "".join(rng.choice(alpha) for _ in range(28))
    return "pwd:" + "".join(rng.choice("abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789")
                            for _ in range(12))


def gen_dob(rng, lang):
    while True:
        y = rng.randint(1955, 2008)
        if y % 10 in _SCOPE_BUCKETS:
            break
    m, d = rng.randint(1, 12), rng.randint(1, 28)
    if lang == "zh":
        return "%d年%d月%d日" % (y, m, d)
    if rng.random() < 0.5:
        return "%d-%02d-%02d" % (y, m, d)
    return "%s %d, %d" % (["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1], d, y)


def gen_address(rng, lang):
    if lang == "zh":
        prov, city = rng.choice(PROV_CITY)
        return "%s%s%s%s%d号%d幢%d单元%d室" % (
            prov, city, rng.choice(DISTRICTS),
            rng.choice(ROADS_ZH), rng.randint(1, 999), rng.randint(1, 30),
            rng.randint(1, 6), rng.randint(101, 2404))
    return "%d %s %s, %s, %s %05d" % (
        rng.randint(1, 9999), rng.choice(EN_STREETS), rng.choice(EN_STREET_TYPES),
        rng.choice(EN_CITIES), rng.choice(EN_STATES), rng.randint(10000, 99999))


def gen_mrn(rng, lang):
    if lang == "zh":
        return "%s-2026-%05d" % (rng.choice(["MR", "MZ", "ZY"]), rng.randint(1, 99999))
    return "MRN-%d-%06d" % (rng.randint(2019, 2026), rng.randint(1, 999999))


def gen_other_id(rng, lang):
    shape = rng.random()
    if shape < 0.3:  # social security style number
        return "".join(str(rng.randint(0, 9)) for _ in range(12))
    if shape < 0.55:  # student id
        return "%d%06d" % (rng.randint(2018, 2026), rng.randint(1, 999999))
    if shape < 0.8:  # employee id
        return rng.choice(["EMP-", "GH-"]) + "%05d" % rng.randint(1, 99999)
    return "VIP%08d" % rng.randint(1, 99999999)


def gen_plate(rng, lang):
    if lang == "zh":
        prov = rng.choice("京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新渝")
        return "%s%s·%s%s%s%s%s" % (prov, rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ"),
                                    *[rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ")
                                      for _ in range(5)])
    return "%s%s%s-%d%d%d%d" % (rng.choice("ABCDEFGH"), rng.choice("ABCDEFGH"),
                                rng.choice("ABCDEFGH"), *[rng.randint(0, 9) for _ in range(4)])


def gen_order_no(rng):
    return "SN2026" + "".join(str(rng.randint(0, 9)) for _ in range(10))


def gen_waybill(rng):
    return rng.choice(["SF", "YT", "ZTO", "JD"]) + "".join(str(rng.randint(0, 9)) for _ in range(13))


def gen_isbn(rng):
    return "978-%d-%04d-%04d-%d" % (rng.randint(100, 799), rng.randint(1, 9999),
                                     rng.randint(1, 9999), rng.randint(0, 9))


def _ent_person(rng, lang):
    return (gen_zh_name(rng) if lang == "zh" else gen_en_name(rng)), None


def _ent_gov_id(rng, lang):
    return gen_gov_id(rng)


ENT_FUNCS = {
    "person": _ent_person,
    "phone": lambda r, l: (gen_phone(r, l), None),
    "email": lambda r, l: (gen_email(r, l), None),
    "gov_id": _ent_gov_id,
    "address": lambda r, l: (gen_address(r, l), None),
    "bank_card": lambda r, l: (gen_bank_card(r), None),
    "credential": lambda r, l: (gen_credential(r), None),
    "dob": lambda r, l: (gen_dob(r, l), None),
    "license_plate": lambda r, l: (gen_plate(r, l), None),
    "medical_id": lambda r, l: (gen_mrn(r, l), None),
    "other_id": lambda r, l: (gen_other_id(r, l), None),
}

NONPII_FILLERS = {
    "order": lambda r, l: gen_order_no(r),
    "waybill": lambda r, l: gen_waybill(r),
    "company": lambda r, l: r.choice(COMPANIES_ZH) if l == "zh" else r.choice(COMPANIES_EN),
    "product": lambda r, l: r.choice(PRODUCTS_ZH) if l == "zh" else r.choice(PRODUCTS_EN),
    "isbn": lambda r, l: gen_isbn(r),
    "ticket": lambda r, l: "IT-2026-%04d" % r.randint(1, 9999),
    "version": lambda r, l: "v%d.%d.%d" % (r.randint(1, 9), r.randint(0, 20), r.randint(0, 30)),
    "hotline": lambda r, l: "12345" if l == "zh" else "1-800-555-%04d" % r.randint(0, 9999),
    "fictional": lambda r, l: r.choice(FICTIONAL_ZH) if l == "zh" else r.choice(FICTIONAL_EN),
    "historical": lambda r, l: r.choice(HISTORICAL_ZH) if l == "zh" else r.choice(HISTORICAL_EN),
    "room": lambda r, l: "会议室%d" % r.randint(1, 12) if l == "zh" else "Room %d" % r.randint(1, 30),
    "ip": lambda r, l: "192.168.%d.%d" % (r.randint(0, 255), r.randint(1, 254)),
    # placeholder-shaped credentials (arch-m6 directive: example forms that must
    # NOT trigger the BIO head — key to the T4 challenge gate <0.1%)
    "placeholder": lambda r, l: r.choice([
        "YOUR_API_KEY", "sk-xxxxxxxxxxxxxxxx", "user@example.com", "test@test.com",
        "000-000-0000", "+86 000 0000 0000", "password: ********",
        '"api_key": "<你的密钥>"' if l == "zh" else '"api_key": "<your-key-here>"',
        "AKIAIOSFODNN7EXAMPLE", "noreply@example.org",
    ]),
    # masked/authorized-redaction forms (qa-m6 directive: T4 challenge mirror)
    "masked": lambda r, l: r.choice([
        "张*", "李*明", "138****5678", "110101********1234", "6217 **** **** 1234",
        "w***i@example.com" if l == "en" else "王**",
    ]),
}


# ---------------------------------------------------------------- scenes
def maybe_ent(sb, rng, lang, plan, etype, fallback="product", p=0.85):
    """Emit entity of `etype` if still budgeted in plan (list-multiset)."""
    if etype in plan and rng.random() < p:
        plan.remove(etype)
        value, sub = ENT_FUNCS[etype](rng, lang)
        sb.ent(value, etype, sub)
    else:
        sb.txt(NONPII_FILLERS[fallback](rng, lang))
    return


def scene_ticket(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("工单 #%d：客户 " % rng.randint(1000, 9999))
        maybe_ent(sb, rng, lang, plan, "person", "ticket")
        sb.txt(" 来电反馈%s未收到，" % rng.choice(PRODUCTS_ZH))
        sb.txt("订单号 ")
        sb.txt(gen_order_no(rng))
        sb.txt("，联系电话 ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("，请优先回访。")
    else:
        sb.txt("Ticket #%d: customer " % rng.randint(1000, 9999))
        maybe_ent(sb, rng, lang, plan, "person", "ticket")
        sb.txt(" reports the %s was not delivered, order " % rng.choice(PRODUCTS_EN))
        sb.txt(gen_order_no(rng))
        sb.txt(", contact ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(". Please follow up.")
    return sb


def scene_delivery(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("快递面单：收件人 ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("，地址 ")
        maybe_ent(sb, rng, lang, plan, "address", "company")
        sb.txt("，手机 ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("，物品：%s，运单号 %s。" % (rng.choice(PRODUCTS_ZH), gen_waybill(rng)))
    else:
        sb.txt("Delivery slip: recipient ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(", address ")
        maybe_ent(sb, rng, lang, plan, "address", "company")
        sb.txt(", phone ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(", contents: %s, waybill %s." % (rng.choice(PRODUCTS_EN), gen_waybill(rng)))
    return sb


def scene_clinic(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("%s%s门诊记录：患者 " % (rng.choice(HOSPITALS_ZH), rng.choice(DEPARTMENTS_ZH)))
        maybe_ent(sb, rng, lang, plan, "person", "ticket")
        sb.txt("，病历号 ")
        maybe_ent(sb, rng, lang, plan, "medical_id", "ticket")
        sb.txt("，出生 ")
        maybe_ent(sb, rng, lang, plan, "dob", "version")
        sb.txt("，%d岁，" % rng.randint(3, 88))
        sb.txt(rng.choice(["主诉咳嗽三天。", "复诊高血压。", "体检咨询。", "术后复查。"]))
    else:
        sb.txt("%s — %s visit note: patient " % (rng.choice(HOSPITALS_EN), rng.choice(DEPARTMENTS_EN)))
        maybe_ent(sb, rng, lang, plan, "person", "ticket")
        sb.txt(", MRN ")
        maybe_ent(sb, rng, lang, plan, "medical_id", "ticket")
        sb.txt(", DOB ")
        maybe_ent(sb, rng, lang, plan, "dob", "version")
        sb.txt(", age %d, " % rng.randint(3, 88))
        sb.txt(rng.choice(["complains of persistent cough.", "hypertension follow-up.",
                           "post-op review.", "annual physical."]))
    return sb


def scene_bank(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("开户回执：户名 ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("，证件号 ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt("，卡号 ")
        maybe_ent(sb, rng, lang, plan, "bank_card", "order")
        sb.txt("，网银初始密码 ")
        maybe_ent(sb, rng, lang, plan, "credential", "version")
        sb.txt("，预留手机 ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("。")
    else:
        sb.txt("Account opening receipt: holder ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(", ID no. ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt(", card no. ")
        maybe_ent(sb, rng, lang, plan, "bank_card", "order")
        sb.txt(", initial online password ")
        maybe_ent(sb, rng, lang, plan, "credential", "version")
        sb.txt(", phone on file ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(".")
    return sb


def scene_insurance(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("理赔申请：被保险人 ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("，证件号 ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt("，联系邮箱 ")
        maybe_ent(sb, rng, lang, plan, "email", "ticket")
        sb.txt("，事故经过：雨天追尾，责任明确，理赔金额待定。")
    else:
        sb.txt("Insurance claim: policyholder ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(", ID ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt(", email ")
        maybe_ent(sb, rng, lang, plan, "email", "ticket")
        sb.txt(", incident: rear-ended in rain, liability admitted.")
    return sb


def scene_resume(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("候选人信息：")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("，")
        maybe_ent(sb, rng, lang, plan, "email", "ticket")
        sb.txt("，电话 ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("，现居 ")
        maybe_ent(sb, rng, lang, plan, "address", "company")
        sb.txt("，意向岗位：数据工程师。")
    else:
        sb.txt("Candidate profile: ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(", ")
        maybe_ent(sb, rng, lang, plan, "email", "ticket")
        sb.txt(", phone ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(", located at ")
        maybe_ent(sb, rng, lang, plan, "address", "company")
        sb.txt(", target role: data engineer.")
    return sb


def scene_chat(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("[聊天记录]\n甲：你好，我是")
        maybe_ent(sb, rng, lang, plan, "person", "fictional")
        sb.txt("，加一下微信吧，我手机是 ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("。\n乙：好的，发我邮箱 ")
        maybe_ent(sb, rng, lang, plan, "email", "ticket")
        sb.txt(" 也行。")
    else:
        sb.txt("[Chat log]\nA: hi, this is ")
        maybe_ent(sb, rng, lang, plan, "person", "fictional")
        sb.txt(", my number is ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(".\nB: sure, or email me at ")
        maybe_ent(sb, rng, lang, plan, "email", "ticket")
        sb.txt(".")
    return sb


def scene_lease(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("租赁合同（节选）：出租方 ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("；承租方 ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("，身份证 ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt("；房屋坐落 ")
        maybe_ent(sb, rng, lang, plan, "address", "room")
        sb.txt("；月租金人民币%d元。" % rng.randint(1500, 9800))
    else:
        sb.txt("Lease (excerpt): lessor ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("; lessee ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(", ID ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt("; premises ")
        maybe_ent(sb, rng, lang, plan, "address", "room")
        sb.txt("; monthly rent $%d." % rng.randint(900, 4800))
    return sb


def scene_signup(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("会员注册：姓名 ")
        maybe_ent(sb, rng, lang, plan, "person", "fictional")
        sb.txt("，邮箱 ")
        maybe_ent(sb, rng, lang, plan, "email", "ticket")
        sb.txt("，手机 ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("，生日 ")
        maybe_ent(sb, rng, lang, plan, "dob", "version")
        sb.txt("，会员号 ")
        maybe_ent(sb, rng, lang, plan, "other_id", "order")
        sb.txt("。")
    else:
        sb.txt("Member signup: name ")
        maybe_ent(sb, rng, lang, plan, "person", "fictional")
        sb.txt(", email ")
        maybe_ent(sb, rng, lang, plan, "email", "ticket")
        sb.txt(", phone ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(", birthday ")
        maybe_ent(sb, rng, lang, plan, "dob", "version")
        sb.txt(".")
    return sb


def scene_hotel(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("酒店预订确认：")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("，护照 ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt("，入住 3 晚，联系电话 ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("。")
    else:
        sb.txt("Hotel booking confirmation: ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(", passport ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt(", 3 nights, contact ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(".")
    return sb


def scene_hr(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("HR 备忘：新员工 ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(" 报到，工号 ")
        maybe_ent(sb, rng, lang, plan, "other_id", "ticket")
        sb.txt("，工卡已制，工资卡 ")
        maybe_ent(sb, rng, lang, plan, "bank_card", "order")
        sb.txt(" 待验证，系统初始密码 ")
        maybe_ent(sb, rng, lang, plan, "credential", "version")
        sb.txt("，紧急联系人 ")
        maybe_ent(sb, rng, lang, plan, "person", "fictional")
        sb.txt(" ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("。")
    else:
        sb.txt("HR memo: new hire ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(" onboarding; badge printed, payroll card ")
        maybe_ent(sb, rng, lang, plan, "bank_card", "order")
        sb.txt(" pending, initial password ")
        maybe_ent(sb, rng, lang, plan, "credential", "version")
        sb.txt(", emergency contact ")
        maybe_ent(sb, rng, lang, plan, "person", "fictional")
        sb.txt(" ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(".")
    return sb


def scene_property(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("物业报修：")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("（")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("）反映家中水管渗漏，车牌 ")
        maybe_ent(sb, rng, lang, plan, "license_plate", "order")
        sb.txt(" 需登记临时通行。")
    else:
        sb.txt("Maintenance request: ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(" (")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(") reports a water leak; plate ")
        maybe_ent(sb, rng, lang, plan, "license_plate", "order")
        sb.txt(" needs temporary parking access.")
    return sb


def scene_vehicle(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("车辆登记：车主 ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt("，身份证 ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt("，车牌 ")
        maybe_ent(sb, rng, lang, plan, "license_plate", "order")
        sb.txt("，登记地址 ")
        maybe_ent(sb, rng, lang, plan, "address", "room")
        sb.txt("。")
    else:
        sb.txt("Vehicle registration: owner ")
        maybe_ent(sb, rng, lang, plan, "person", "company")
        sb.txt(", ID ")
        maybe_ent(sb, rng, lang, plan, "gov_id", "order")
        sb.txt(", plate ")
        maybe_ent(sb, rng, lang, plan, "license_plate", "order")
        sb.txt(", registered address ")
        maybe_ent(sb, rng, lang, plan, "address", "room")
        sb.txt(".")
    return sb


def scene_school(rng, lang, plan):
    sb = Seg()
    if lang == "zh":
        sb.txt("家长联系方式登记：学生学号 ")
        maybe_ent(sb, rng, lang, plan, "other_id", "ticket")
        sb.txt("，家长 ")
        maybe_ent(sb, rng, lang, plan, "person", "fictional")
        sb.txt("，电话 ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt("，住址 ")
        maybe_ent(sb, rng, lang, plan, "address", "room")
        sb.txt("，接送车辆 ")
        maybe_ent(sb, rng, lang, plan, "license_plate", "order")
        sb.txt("。")
    else:
        sb.txt("Parent contact sheet: parent ")
        maybe_ent(sb, rng, lang, plan, "person", "fictional")
        sb.txt(", phone ")
        maybe_ent(sb, rng, lang, plan, "phone", "hotline")
        sb.txt(", home address ")
        maybe_ent(sb, rng, lang, plan, "address", "room")
        sb.txt(", pickup vehicle ")
        maybe_ent(sb, rng, lang, plan, "license_plate", "order")
        sb.txt(".")
    return sb


SCENES = [scene_ticket, scene_delivery, scene_clinic, scene_bank, scene_insurance,
          scene_resume, scene_chat, scene_lease, scene_signup, scene_hotel,
          scene_hr, scene_property, scene_vehicle, scene_school]
SCENE_SLOTS = {
    scene_ticket: ["person", "phone"],
    scene_delivery: ["person", "address", "phone"],
    scene_clinic: ["person", "medical_id", "dob", "other_id"],
    scene_bank: ["person", "gov_id", "bank_card", "credential", "phone"],
    scene_insurance: ["person", "gov_id", "email"],
    scene_resume: ["person", "email", "phone", "address"],
    scene_chat: ["person", "phone", "email"],
    scene_lease: ["person", "person", "gov_id", "address"],
    scene_signup: ["person", "email", "phone", "dob", "other_id"],
    scene_hotel: ["person", "gov_id", "phone"],
    scene_hr: ["person", "other_id", "bank_card", "credential", "person", "phone"],
    scene_property: ["person", "phone", "license_plate"],
    scene_vehicle: ["person", "gov_id", "license_plate", "address"],
    scene_school: ["other_id", "person", "phone", "address", "license_plate"],
}


def build_pos(rng, lang, difficulty):
    scene = rng.choice(SCENES)
    slot_types = SCENE_SLOTS[scene]
    if difficulty == "easy":
        n = rng.choice([1, 2])
    elif difficulty == "medium":
        n = rng.choice([2, 3])
    else:
        n = rng.choice([4, 5])
    n = min(n, len(slot_types))
    pool = list(slot_types)
    rng.shuffle(pool)
    plan = pool[:n]
    sb = scene(rng, lang, plan)
    text, spans = sb.build()
    return text, spans


def _fill_tpl(tpl, rng):
    """Parameterize placeholder/masked hard-negative templates: keeps the
    PII-shaped semantics while randomizing non-semantic slots so identical
    text cannot recur across split scopes (cross-split sig uniqueness)."""
    import re as _re
    def _sub(m):
        kind = m.group(1)
        if kind == "d":
            return str(rng.randint(12, 480))            # ticket counts etc.
        if kind == "t":
            return str(rng.randint(1000, 9999))         # masked phone tail
        if kind == "c":
            return str(rng.randint(1000, 9999))         # masked card tail
        if kind == "i":
            return str(rng.randint(100, 999)) + "****" + "****" + str(rng.randint(100, 999))  # masked id mid
        if kind == "u":
            return "user%04d" % rng.randint(1, 9999)    # fixture username
        if kind == "x":
            return "x" * rng.randint(8, 20)             # sk-xxxx run length
        if kind == "n":
            return rng.choice(["张*", "李*明", "王*", "刘*", "陈*", "赵*", "w**", "j*"])
        return m.group(0)
    return _re.sub(r"%(d|t|c|i|u|x|n)%", _sub, tpl)


PLACEHOLDER_CTX_ZH = [
    "API 配置文档（示例值）：\n{\n  \"api_key\": \"YOUR_API_KEY\",\n  \"endpoint\": \"https://api.example.com/v1\",\n  \"timeout\": 30\n}",
    "使用说明：请在 config.yaml 中填入你的密钥，例如 token: sk-%x%，切勿提交到代码库。",
    "测试用例夹具：user = \"%u@test.com\"; phone = \"000-000-0000\"; expect login to fail.",
    "接入示例：export ACCESS_KEY=AKIAIOSFODNN7EXAMPLE；联系方式填 noreply@example.org 即可。",
]
PLACEHOLDER_CTX_EN = [
    "API config doc (example values):\n{\n  \"api_key\": \"YOUR_API_KEY\",\n  \"endpoint\": \"https://api.example.com/v1\",\n  \"timeout\": 30\n}",
    "Usage note: put your key in config.yaml, e.g. token: sk-%x%; never commit it.",
    "Test fixture: user = \"%u@test.com\"; phone = \"000-000-0000\"; expect login to fail.",
    "Onboarding example: export ACCESS_KEY=AKIAIOSFODNN7EXAMPLE; set contact to noreply@example.org.",
]
MASKED_CTX_ZH = [
    "合规脱敏日报：今日处理客户工单 %d 件，其中客户 %n（手机 138****%t）的退款申请已通过复核。",
    "日志脱敏样例：user=%n 登录成功；身份证 %i 已按规范掩码。",
    "数据出境审查记录：银行卡 6217 **** **** %c 的持卡人信息已脱敏，可放行。",
]
MASKED_CTX_EN = [
    "Compliance redaction digest: %d tickets processed today; customer %n (phone 138****%t) refund approved on review.",
    "Log masking sample: user=%n logged in; ID %i masked per policy.",
    "Cross-border data review: card 6217 **** **** %c holder info redacted; cleared for release.",
]


def build_neg(rng, lang, hard):
    scene = rng.choice(SCENES)
    if hard:
        u = rng.random()
        if u < 0.4:
            # placeholder-shaped credentials in doc/test-fixture contexts
            return _fill_tpl(rng.choice(PLACEHOLDER_CTX_ZH if lang == "zh" else PLACEHOLDER_CTX_EN), rng)
        if u < 0.6:
            # masked/authorized-redaction context (T4 challenge mirror)
            return _fill_tpl(rng.choice(MASKED_CTX_ZH if lang == "zh" else MASKED_CTX_EN), rng)
        # near-miss: scene with PII-shaped non-personal fillers
        sb = scene(rng, lang, [])
        text = sb.build()[0]
        # then sometimes wrap in an explicitly fictional/historical context
        if rng.random() < 0.5:
            if lang == "zh":
                text = rng.choice([
                    "小说设定稿：%s" % text,
                    "教材示例（虚构人物）：%s" % text,
                    "影视剧情梗概：%s" % text,
                ])
            else:
                text = rng.choice([
                    "Fiction draft: %s" % text,
                    "Textbook example (fictional persons): %s" % text,
                    "Movie synopsis: %s" % text,
                ])
        return text
    # plain negative: scene runs with empty entity plan -> all fillers non-PII
    sb = scene(rng, lang, [])
    return sb.build()[0]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261021)
    ap.add_argument("--out", default="data/m6/_staging/t4-pii.jsonl")
    args = ap.parse_args()

    # cross-scope dedup: one shared Deduper so identical text can never be
    # emitted into two split scopes (arch P0-1 global-sig ruling)
    rng = random.Random(args.seed)
    rows = []
    dd = Deduper()

    # three-scope production: entity pools are hash-bucket-isolated per split
    # (qa L5 fix) — heldout/dev rows share NO low-entropy pool value with train
    scopes = [
        ("train", "data/m6/_staging/t4-pii-train.jsonl", 2600, 3700),
        ("dev", "data/m6/_staging/t4-pii-dev.jsonl", 250, 600),
        ("heldout", "data/m6/_staging/t4-pii-heldout.jsonl", 300, 1100),
    ]
    for scope, out_path, n_pos, n_neg in scopes:
        rng = random.Random(args.seed + {"train": 0, "dev": 1, "heldout": 2}[scope])
        set_scope(scope)
        rows = []

        plan = (["easy"] * int(n_pos * 0.25) + ["medium"] * int(n_pos * 0.42)
                + ["hard"] * (n_pos - int(n_pos * 0.25) - int(n_pos * 0.42)))
        rng.shuffle(plan)
        made = 0
        guard = 0
        while made < n_pos and guard < n_pos * 40:
            guard += 1
            diff = plan[made % len(plan)]
            lang = "zh" if rng.random() < 0.55 else "en"
            text, spans = build_pos(rng, lang, diff)
            if not spans or dd.is_dup(text):
                continue
            dd.add(text)
            rows.append(make_row("T4", scope, lang, "singleturn", "pos",
                                 {"spans": spans}, "synth-pii-v1", text=text,
                                 difficulty=diff,
                                 lineage={"generator": "gen_pii.py", "seed": args.seed,
                                          "scope": scope}))
            made += 1

        n_hard = int(n_neg * 0.34)
        made = 0
        guard = 0
        while made < n_neg and guard < n_neg * 40:
            guard += 1
            lang = "zh" if rng.random() < 0.55 else "en"
            hard = made < n_hard
            text = build_neg(rng, lang, hard)
            if dd.is_dup(text):
                continue
            dd.add(text)
            rows.append(make_row("T4", scope, lang, "singleturn", "neg",
                                 {"spans": []}, "synth-pii-v1", text=text,
                                 difficulty="hard" if hard else "easy",
                                 lineage={"generator": "gen_pii.py", "seed": args.seed,
                                          "scope": scope,
                                          "variant": "near-miss" if hard else "clean"}))
            made += 1

        assign_ids(rows, "m6-t4-" + scope)
        write_jsonl(out_path, rows)
        bad = 0
        for r in rows:
            t = r.get("text", "")
            for sp in r["label_detail"]["spans"]:
                if sp["end"] > len(t) or sp["start"] >= sp["end"]:
                    bad += 1
        print("[%s] %d rows, %d bad spans" % (scope, len(rows), bad))
        assert bad == 0, "bad spans in " + scope


if __name__ == "__main__":
    main()
