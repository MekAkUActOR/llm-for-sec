# -*- coding: utf-8 -*-
"""gen_t2_nearmiss_train — arch T2 near-miss fix order: ADD train-side
synth-jailbreak-v1 near-miss rows (the 232-row family was entirely
dev-assigned by quota order — the head never saw this boundary in training).
Reuses the ORIGINAL near-miss construct (benign-context templates from
gen_t2_jailbreak: security-research / fiction / academic / certification /
script-writing contexts). Appends to the t2-jailbreak staging pool; the pos
side is untouched (append-only, existing ids preserved).
"""
import argparse
import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m6common import make_row, write_jsonl, assign_ids, Deduper
from gen_t2_jailbreak import (BENIGN_ZH, BENIGN_EN, BENIGN_SLOTMAP_ZH,
                              BENIGN_SLOTS_ZH, BENIGN_SLOTS_EN)

# Extended slot pools (same construct: benign security-research/fiction/
# academic/certification/script contexts) — the original pools were exhausted
# by the 232 frozen rows; extension multiplies the combination space without
# touching the original generator or its frozen output.
EXT_ZH = [
    ["金融犯罪", "电信诈骗治理", "数据合规"],
    ["会话劫持", "DNS 劫持", "恶意软件打包", "凭证填充", "无文件攻击", "供应链投毒"],
    ["社工利用的是人的轻信", "勒索利用的是备份缺失", "提权利用的是配置粗心", "钓鱼利用的是紧迫感", "蠕虫利用的是补丁滞后"],
    ["\"我把他们的数据库导出来了。\"", "\"我拿到了管理员的会话 cookie。\"", "\"我给整层楼装了假 Wi-Fi。\""],
    ["供应链攻击复盘", "勒索应急", "网络切断演练", "数据外泄溯源"],
    ["OSCP", "CEH", "CISSO", "CISM"],
    ["威胁建模入门", "密码学应用实践", "零信任架构", "蜜罐技术", "取证基础"],
    ["僵尸网络的兴衰史", "勒索软件的商业模式", "暗网市场的治理难题", "漏洞赏金的演化"],
    ["博弈论", "信息不对称", "组织行为学", "风险感知"],
    ["表弟", "外甥女", "邻居家孩子", "同事的孩子"],
    ["勒索软件是怎么加密文件的", "为什么公共 Wi-Fi 有风险", "验证码为什么能防机器人", "钓鱼网站为什么做得像真的"],
    ["企业安全自查十条", "老年人反诈手册", "电商账号保护清单", "出差设备安全规范"],
    ["SOC", "XDR", "MDR", "CASB", "ZTNA"],
    ["用假简历骗过了背景调查", "把测试账号提权成了管理员", "在咖啡店截获了同事的登录请求", "用旧工牌进了机房"],
    ["运维", "客服", "财务", "行政"],
    ["刑侦", "商战", "谍战", "悬疑"],
    ["短信嗅探", "SIM 卡劫持", "伪基站", "木马apk"],
    ["金融反诈", "企业合规", "校园安全", "个人信息保护"],
]
EXT_EN = [
    ["financial crime", "telecom-fraud governance", "data compliance"],
    ["session hijacking", "DNS hijacking", "malware packing", "credential stuffing", "fileless attacks", "supply-chain poisoning"],
    ["social engineering exploits trust", "ransomware exploits missing backups", "privilege escalation exploits sloppy config", "phishing exploits urgency", "worms exploit unpatched systems"],
    ["'I dumped their database.'", "'I got the admin's session cookie.'", "'I stood up a fake Wi-Fi for the whole floor.'"],
    ["supply-chain post-mortem", "ransomware response", "network-cut drill", "data-leak forensics"],
    ["OSCP", "CEH", "CISSO", "CISM"],
    ["threat modeling", "applied cryptography", "zero-trust architecture", "honeypots", "forensics basics"],
    ["the rise and fall of botnets", "ransomware's business model", "dark-web market governance", "bug-bounty evolution"],
    ["game theory", "information asymmetry", "organizational behavior", "risk perception"],
    ["younger brother", "niece", "the neighbor's kid", "a coworker's child"],
    ["how ransomware encrypts files", "why public Wi-Fi is risky", "why captchas stop bots", "why phishing sites look real"],
    ["Ten Corporate Security Checks", "Anti-Fraud Handbook for Seniors", "E-commerce Account Protection", "Travel Device Hygiene"],
    ["SOC", "XDR", "MDR", "CASB", "ZTNA"],
    ["faked a resume to pass background checks", "escalated a test account to admin", "intercepted a colleague's login at a café", "entered the server room with an old badge"],
    ["ops", "support", "finance", "admin"],
    ["crime", "corporate warfare", "spy", "mystery"],
    ["SMS sniffing", "SIM swapping", "fake base stations", "trojanized apks"],
    ["financial anti-fraud", "corporate compliance", "campus safety", "personal privacy"],
]


def _merged(base, ext):
    return [b + e for b, e in zip(base, ext)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--n", type=int, default=500)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    # seed the deduper with ALL existing staging texts (pos + neg) so the
    # new rows can never collide with the frozen pool
    dd = Deduper()
    staging = "data/m6/_staging/t2-jailbreak.jsonl"
    existing = []
    with open(staging, encoding="utf-8") as f:
        for line in f:
            r = __import__("json").loads(line)
            existing.append(r)
            t = r.get("text") or "\n".join(t["content"] for t in (r.get("turns") or []))
            dd.add(t)

    rows = []
    made = guard = 0
    while made < args.n and guard < args.n * 80:
        guard += 1
        lang = "zh" if rng.random() < 0.55 else "en"
        i = rng.randrange(len(BENIGN_ZH))
        tpl = (BENIGN_ZH if lang == "zh" else BENIGN_EN)[i]
        smap = BENIGN_SLOTMAP_ZH
        pools_s = _merged(BENIGN_SLOTS_ZH if lang == "zh" else BENIGN_SLOTS_EN,
                          EXT_ZH if lang == "zh" else EXT_EN)
        args2 = []
        _used = collections.defaultdict(set)
        for k in smap[i]:
            pool = pools_s[k]
            choices = [v for v in pool if v not in _used[k]] or pool
            v = rng.choice(choices)
            _used[k].add(v)
            args2.append(v)
        text = tpl % tuple(args2)
        if dd.is_dup(text):
            continue
        dd.add(text)
        rows.append(make_row("T2", "pool", lang, "singleturn", "neg",
                             {"framework": None}, "synth-jailbreak-v1",
                             text=text, difficulty="hard",
                             lineage={"generator": "gen_t2_nearmiss_train.py",
                                      "seed": args.seed,
                                      "variant": "near-miss-benign",
                                      "wave": "t2-fix-1"}))
        made += 1

    assign_ids(rows, "m6-t2-nm")
    with open(staging, "a", encoding="utf-8", newline="\n") as f:
        import json as _j
        for r in rows:
            f.write(_j.dumps(r, ensure_ascii=False) + "\n")
    print("gen_t2_nearmiss_train: +%d rows (append-only), staging now %d"
          % (len(rows), len(existing) + len(rows)))


if __name__ == "__main__":
    main()
