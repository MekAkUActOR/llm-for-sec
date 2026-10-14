r"""M2 全量 SFT 数据组装管线（docs/research/m2-data-assembly-plan.md §9 规格实现）。

管线顺序（§5 固定）：load raw(15 公共源 + 自建 v0) → 污染/红线剔除
（reports/sft-exclusion-hashes.json 内容哈希清单——消 doc_index 枚举序
耦合）→ 转换（§1 逐源规格）→ 跨源去重（§4：8-gram containment，攻击池
0.6 / 良性池 0.5，attack_surface_id 组内豁免）→ 条件化（A 三包 / B 二包
误拒纪律 / C 固定 default 检测 / D 随机包拒绝——转换器内嵌）→ 配比采样
（§6 行总数定标 96K，zh:en 40:60 目标）→ shuffle（seed 固定）。

关键纪律：
- 原始公共源响应永不直接作 assistant 模板——[R] 复用必须追加 VERDICT 尾行；
  武器化侧（cvalues neg / pku unsafe / beavertails unsafe / hh rejected）
  永不 assistant，整对进 data/sft/dpo-reserve/（M3 偏好阶段）；
- trustllm privacy_leakage 反向设计（§1.5）：检测/分级响应，gt-* 永不入
  训练文本；
- 公共 eval split 永不入 SFT（hh test / pku test / beavertails 30k-test
  + 330k-test / wj eval.tsv / wgm test.parquet / cvalues test 文件——
  §1.12"任何自带 test split"原则）；
- 工具输出载体族永不生成（docs/06 §7 留出族）；红名单参考集与安全
  评测基准集零引用（reference-only / 评估侧，见 plan §0 原则）；评估与
  探针路径零引用（隔离红线）；
- 攻击意图池切分 = 规则版分类器（§1.14 降级方案，M2 首跑不训分类器；
  wgm 人标实测准确率 + 100 条抽检清单见 --audit-pool-split 输出）。

输出：data/sft/m1/{train.jsonl, meta.json, README.md} +
data/sft/dpo-reserve/*.jsonl + reports/m2-pool-split-audit.json。
LF 注册接口：--register-lf（复用 convert_sft_v0 注册逻辑，登记
sec_sft_m1——**默认关**，等校准跑后再定）。

用法：python scripts/assemble_sft_m2.py [--audit-pool-split 100]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gen_sft_v0 import (  # noqa: E402  自建管线契约（政策系统区/改述/VERDICT）
    POLICY_SYSTEM, SURFACE_WRAPPERS, verdict_line)
from secfm.carriers.base import CarrierBlock  # noqa: E402
from secfm.protocol.context import build_context  # noqa: E402

RAW = ROOT / "data" / "corpora" / "raw" / "m2"
V0_DIR = ROOT / "data" / "sft" / "v0"
V0X_DIR = ROOT / "data" / "sft" / "v0x"
EXCL_JSON = ROOT / "reports" / "sft-exclusion-hashes.json"
OUT_DIR = ROOT / "data" / "sft" / "m1"
DPO_DIR = ROOT / "data" / "sft" / "dpo-reserve"
AUDIT_JSON = ROOT / "reports" / "m2-pool-split-audit.json"
SEED = 20260927

# §6 行总数定标（回填批 M2：总盘 96K±10% 由子项上限自然收敛；OR:attack
# ≥1.25 与 zh:en ≥35:65 通过上限配置实现——见 meta.row_deficit 如实报告）
ROW_QUOTA = {"policy_pairs": 43200, "task_single": 24000,
             "injection_jailbreak": 11500, "multiturn": 7700,
             "general_recovery": 52000}

# ================================================================ 模板库 ===
# [S] 政策化拒绝（D 层随机单包；理由随包微调——§2 D）
REFUSAL_REPLY = {
    "conservative": {
        "en": ("I can't help with this request. Under the conservative "
               "policy pack, this falls outside what I may assist with. "
               "If there's a legitimate professional need, please route it "
               "through an authorized channel."),
        "zh": "这个请求我无法协助。保守包语境下它不在可协助范围内；如有正当专业需求，请走授权通道。"},
    "default": {
        "en": ("I can't help with that. This request is against the "
               "default policy pack's safety rules. I'm happy to help with "
               "a safe alternative if you'd like."),
        "zh": "这个我帮不了。该请求违反默认包的安全规则；如果需要，我可以帮你找一个安全的替代方案。"},
    "professional": {
        "en": ("This request can't be fulfilled. Even under the "
               "professional pack, it lacks the authorization context "
               "required for this class of action. Provide attested "
               "identity and written scope, or use an approved channel."),
        "zh": "该请求无法执行。即使在专业包下，此类操作也缺少授权语境；请提供认证身份与书面范围，或走已批准通道。"},
}
# [S] 误拒纪律简短应答（xstest/or-bench——良性争议话题必须应答；诚实简答
# 不编造细节，教"应答而非回避"的行为信号）
OR_ANSWER = {
    "en": ["Sure — this is a reasonable question. In short: the direct, "
           "everyday interpretation here is benign, and the usual approach "
           "works fine. Tell me more and I'll go deeper.",
           "Happy to help. The short version: nothing about this request "
           "is problematic on its face; the standard practice applies. "
           "Ask away if you want specifics.",
           "Good question — it's a safe one to discuss. Briefly: the "
           "common-sense answer holds here. I can expand if useful."],
    "zh": ["可以聊聊，这个问题本身没什么问题。简单说：按常规理解处理即可，需要细节可以继续问我。",
           "没问题，这是可以正常讨论的话题。简短回答就是通常的做法在这里适用；想深入我再说。",
           "这个可以答。简要来说，常识性的处理方式在这里是成立的，有需要我可以展开。"],
}
# [S] 多轮渐进梯度（safemtdata Attack_600：正常→提醒→拒绝升级——ais-r10）
SMT_BRIDGE = {
    "en": ["Sure — briefly: {q0} is a fair background question; the "
           "general picture is well documented and I can sketch it.",
           "Okay. On that background point: the broad outline is standard "
           "knowledge and worth understanding from a professional angle."],
    "zh": ["好的，这个问题作为背景了解是合理的；大方向上是公开常识，我可以简述。"],
}
SMT_REMIND = {
    "en": "I can keep going on the background, but let's stay on the safe, documented side of this topic.",
    "zh": "背景部分我可以继续，但这个话题我们保持在有据可查的安全范围内。",
}
# [S] 检测/分级响应（trustllm privacy_leakage 反向设计——检测不揭示）
LEAK_DETECT = {
    "en": ("I checked the text you provided: it contains personal "
           "information (names and email addresses). I won't extract or "
           "repeat those values. Recommended handling: mask the direct "
           "identifiers before any further processing, and access such "
           "records only through your authorized data channel."),
    "zh": ("我检查了你提供的文本：其中包含个人信息（姓名与邮箱地址）。我不会提取或复述这些值。"
           "建议处理方式：先对直接标识符做脱敏，再进行后续处理；此类记录只应通过授权数据通道访问。"),
}
# [S] 隐私意识问答三包（trustllm privacy_awareness——POL-PRIV-001/002 对齐）
AWARENESS_REPLY = {
    "conservative": {
        "en": ("Under the conservative pack, treat this as sensitive by "
               "default: collect the minimum, share nothing without "
               "explicit consent, and prefer refusing the processing step "
               "to risking exposure."),
        "zh": "保守包语境下默认按敏感处理：最小化收集、未经明确同意不共享；宁可拒绝该处理步骤，也不冒暴露风险。"},
    "default": {
        "en": ("This can be handled with care: keep only what's needed, "
               "anonymize where possible, and confirm the purpose is "
               "legitimate before processing. If any doubt remains, ask "
               "the data subject or decline."),
        "zh": "可以谨慎处理：只保留必要数据、尽量匿名化、处理前确认目的正当；仍有疑虑时，询问数据主体或拒绝。"},
    "professional": {
        "en": ("As a professional handling this: apply purpose limitation "
               "and data minimization, log the access, and process within "
               "the documented authorization scope. Where the request "
               "exceeds scope, escalate rather than improvise."),
        "zh": "专业人员处理时：遵循目的限制与数据最小化、记录访问、在书面授权范围内处理；超出范围时上报而非自行变通。"},
}
AWARENESS_VERDICT = {"conservative": ("refuse", "refuse"),
                     "default": ("answer", "conditional"),
                     "professional": ("answer", "allow")}
# [S] 回复审查（wgm 任务③——审查其他模型输出，docs/04.4 T8 职能）
REVIEW_SAFE = {
    "en": "I reviewed the assistant reply in the carrier: it stays within safe bounds — no harmful content or policy violations detected.",
    "zh": "我审查了载体中的助手回复：内容在安全范围内，未检出有害内容或政策违规。"}
REVIEW_UNSAFE = {
    "en": "I reviewed the assistant reply in the carrier: it contains harmful content that should not have been produced. Flagging it as a finding; recommend suppression and a refusal-style rewrite.",
    "zh": "我审查了载体中的助手回复：其中包含不应产出的有害内容。已作为发现上报；建议拦截并改写为拒绝式回复。"}

# ================================================== 攻击意图分类器（池切分） ===
# v1 = CPU 轻量（TF-IDF char_wb(2-4)+word(1-2) → LogReg，zh+en）；
# 训练/评测见 scripts/train_pool_classifier.py（wgm 独立切分 heldout：
# P=0.941 / R=0.940，规则版 0.705/0.20 —— §1.14 降级解除）。
_CLF_STATE = {"bundle": None, "loaded": False}


def _load_clf():
    if not _CLF_STATE["loaded"]:
        _CLF_STATE["loaded"] = True
        _p = ROOT / "data" / "models" / "classifier-v1" / "model.pkl"
        if _p.exists() and os.environ.get("ASSEMBLE_RULE_ONLY") != "1":
            try:
                import joblib
                _CLF_STATE["bundle"] = joblib.load(_p)
            except Exception:
                _CLF_STATE["bundle"] = None
    return _CLF_STATE["bundle"]


_ATTACK_EN = re.compile(
    r"\b(bomb|explosive|malware|ransomware|keylogger|phishing|hack(?:ing)? "
    r"(?:into|someone|account)|break into|steal|shoplift|meth|cocaine|heroin"
    r"|poison|kill (?:someone|him|her|them|myself)|suicide|self[- ]harm"
    r"|counterfeit|forge|fraud|scam|launder|blackmail|extort|stalk(?:ing)?"
    r"|pedophil|child (?:porn|sexual|abuse)|ransom|dDoS|botnet|exploit (?:kit|vuln)"
    r"|weapon|silencer|ghost gun|hitman|murder|strangling|strangle|date rape"
    r"|drug (?:dealer|trafficking)|human trafficking|slave|torture"
    r"|counterfeit (?:money|bills)|fake (?:id|passport|license)"
    r"|laundering|smuggle|arson|loot|riot|vandalis"
    r"|rape|raping|molest|molesting|assault|assaulting|stab|stabbing"
    r"|shoot(?:ing)? (?:someone|him|her|them|up|people|up a|at)"
    r"|mass shooting|school shooting|bomb threat"
    r"|embezzl|kidnap(?:ping)?|traffick"
    r"|nerve agent|ricin|methamphetamine|fentanyl"
    r"|identity theft|credit card (?:fraud|dump|number)"
    r"|(?:find|get|give) (?:me )?(?:his|her|their|the)? ?home address"
    r"|home address for|dox(?:ing)?|swat(?:ting)?"
    r"|pornograph|bestiality|necrophilia|incest"
    r"|whore|slut|retard|fag{2,}|n[i1]gg)"
    r"\w*", re.I)
_ATTACK_ZH = re.compile(
    r"(炸弹|爆炸|爆炸物|病毒|木马|勒索|黑客|入侵|破解.{0,4}(账号|密码|系统)|"
    r"盗窃|偷窃|偷渡|走私|诈骗|洗钱|假币|伪造|假证|假护照|赌场|赌博|毒品|"
    r"冰毒|海洛因|大麻|下药|毒死|杀人|自杀|自残|绑架|拐卖|人口贩卖|虐待|"
    r"色情|裸照|偷拍|跟踪|骚扰|恐吓|威胁|敲诈|行贿|受贿|逃税|造假|袭击|"
    r"强奸|轮奸|迷奸|猥亵|性侵|性骚扰|嫖娼|卖淫|淫秽|"
    r"操纵他人|精神控制|洗脑|伤害.{0,3}(他人|别人)|攻击.{0,4}(别人|他人|某人)|"
    r"灭口|虐杀|殴打|暴打|捅刀|持刀|枪击|伏击|"
    r"住址|家庭住址|身份证号|手机号.{0,2}多少|"
    r"开房)")


def is_attack(text: str) -> tuple[bool, list[str]]:
    """攻击意图判定 → (是否攻击, 证据)。

    分类器优先（data/models/classifier-v1，wgm heldout P=0.941/R=0.940，
    超规则版一倍召回）；模型缺失或 ASSEMBLE_RULE_ONLY=1 时回退词面规则
    （§1.14 原降级路径保留）。"""
    b = _load_clf()
    if b is not None:
        x = b["vectorizer"].transform([text])
        p = int(b["clf"].predict(x)[0])
        return bool(p), [f"clf:{p}"]
    hits = []
    m = _ATTACK_EN.search(text)
    if m:
        hits.append(m.group(0))
    m = _ATTACK_ZH.search(text)
    if m:
        hits.append(m.group(0))
    return bool(hits), hits


# ============================================================ 剔除哈希 ===
def load_exclusions(path: Path = EXCL_JSON) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    return {k: set(v["sha256"]) for k, v in d.items() if k != "_meta"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- 排除文本镜像（与 check_sft_contamination.docs_for 逐字节一致；
# ---- 单测桥接校验防漂移；此处只描述"记录 → 检查器文档串"的构造）----
def _dt_hh(j): return f"{j.get('chosen','')}\n{j.get('rejected','')}"
def _dt_sp(it): return f"{it.get('prompt','')}\n{it.get('response','')}"
def _dt_smt(it):
    parts = [it.get("plain_query", ""), it.get("relationship", "")]
    parts += [str(q) for q in (it.get("multi_turn_queries") or [])]
    for c in it.get("conversations") or []:
        parts.append(c.get("value", ""))
    return "\n".join(parts)
def _dt_adv(row): return "\n".join(str(row.get(c, "")) for c in ["goal"])
def _dt_hb(row): return "\n".join(str(row.get(c, "")) for c in
                                  ["Behavior", "ContextString"])
def _dt_sr(row): return "\n".join(str(row.get(c, "")) for c in
                                  ["forbidden_prompt"])
def _dt_mi(text): return text
def _dt_xst(row): return "\n".join(str(row.get(c, "")) for c in ["prompt"])
def _dt_ob(row): return "\n".join(str(row.get(c, "")) for c in ["prompt"])
def _dt_tl(it): return "\n".join(str(v) for v in it.values()
                                 if isinstance(v, str))
def _dt_cv(r): return "\n".join(str(v) for v in r.values()
                                if isinstance(v, str))
def _dt_pku(j): return "\n".join(str(j.get(k, "")) for k in
                                 ("prompt", "response_0", "response_1"))
def _dt_bt(j): return f"{j.get('prompt','')}\n{j.get('response','')}"
def _dt_wj(row): return "\n".join(row)
def _dt_wgm(row): return "\n".join(str(row[c]) for c in
                                   ("prompt", "adversarial", "response")
                                   if c in row)


# ============================================================ 基础构件 ===
# 转换期池上限（去重前预采样；行配比 SUBCAPS 之前的体量护栏——
# 保原始行序，paraphrase 对/多轮结构不受影响）
POOL_CAPS = {"wj_rows": 30000, "wj_benign_rows": 20000,
             "cv_attack": 9000, "cv_benign": 8000,
             "pku_attack": 6000, "pku_benign": 8000,
             "hh_benign": 20000,
             "sp_attack": 15000, "sp_typical": 15000}


def _select_idx(idx_list: list, cap: int, rng: random.Random) -> set:
    """从索引列表确定性采样 cap 个（返回原索引子集；保序消费方枚举）。"""
    if len(idx_list) <= cap:
        return set(idx_list)
    return set(rng.sample(idx_list, cap))


def _messages(pack: str, lang: str, turns: list) -> dict:
    """多轮消息流（LLaMA-Factory 兼容；system 固定 POLICY_SYSTEM）。
    生成期硬校验：首轮 user、严格交替、末轮 assistant——违规当场失败。"""
    assert turns and turns[0][0] == "user", f"首轮非 user: {turns[:1]}"
    for k, (role, _) in enumerate(turns):
        want = "user" if k % 2 == 0 else "assistant"
        assert role == want, f"第 {k} 轮角色 {role}≠{want}"
    assert turns[-1][0] == "assistant", "末轮非 assistant"
    msgs = [{"role": "system",
             "content": POLICY_SYSTEM[pack]["zh" if lang == "zh" else "en"]}]
    msgs += [{"role": r, "content": c} for r, c in turns]
    return msgs


def _item(sid, task, pack, lang, turns, *, row, pool, source,
          surface_key=None, or_flag=False, attack=False):
    """条目构造：turns = [(role, text)]；末轮 assistant 已含 VERDICT。"""
    return {"id": sid, "task": task, "pack": pack, "lang": lang,
            "messages": _messages(pack, lang, turns), "row": row,
            "pool": pool, "source": source,
            "surface_key": surface_key or f"{source}:{sid}",
            "or_flag": or_flag, "attack": attack}


def _refusal_turns(user_text: str, pack: str, lang: str, task_note: str):
    reply = REFUSAL_REPLY[pack][lang]
    v = verdict_line("refuse", "refuse", 0.95, [task_note] if task_note
                     else [], pack)
    return [("user", user_text), ("assistant", reply + "\n" + v)]


def _answer_turns(user_text: str, reply: str, pack: str, verdict=None,
                  findings=None, conf=0.9):
    v = verdict_line("answer", verdict, conf, findings or [], pack)
    return [("user", user_text), ("assistant", reply.rstrip() + "\n" + v)]


def _collapse_turns(turns: list) -> list:
    """连续同角色轮合并（LF sharegpt 契约：严格 user/assistant 交替；
    hh 原文偶见连续 Human 块）。"""
    out = []
    for role, text in turns:
        if out and out[-1][0] == role:
            out[-1] = (role, out[-1][1] + "\n\n" + text)
        else:
            out.append((role, text))
    return out


_HH_SPLIT = re.compile(r"(?:^|\n\n|\n)\s*(Human|Assistant):\s*")


def _hh_turns(conv: str) -> list:
    """'Human: X\n\nAssistant: Y' 串 → [(role, text)]（LF 契约角色归一）。"""
    parts = _HH_SPLIT.split(conv)
    turns = []
    for i in range(1, len(parts) - 1, 2):
        role = "user" if parts[i].lower() == "human" else "assistant"
        text = parts[i + 1].strip()
        if text:
            turns.append((role, text))
    return _collapse_turns(turns)


# ================================================================ 读取器 ===
def _jsonl_rows(path: Path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _csv_rows(path: Path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            yield row


def _gz_jsonl_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _parquet_rows(path: Path):
    import pyarrow.parquet as pq
    t = pq.read_table(path)
    for row in t.to_pylist():
        yield row


# ================================================================ 转换器 ===
def conv_hh(raw: Path, excl: set, rng: random.Random, dpo: list) -> list:
    """§1.1 双池切分：攻击池 [S] 拒绝重写 / 良性池 [R] 复用 + VERDICT；
    >6 轮截断（§7）；rejected 侧 → DPO 储备（良性对话）。"""
    out = []
    rows = list(_gz_jsonl_rows(raw / "hh-rlhf" / "harmless-base"
                               / "train.jsonl.gz"))
    atk_rows, ben_rows = [], []
    for i, j in enumerate(rows):
        if _sha(_dt_hh(j)) in excl:
            continue
        turns = _hh_turns(j["chosen"])
        if not turns:
            continue
        human_all = " ".join(t for r, t in turns if r == "user")
        (atk_rows if is_attack(human_all)[0] else ben_rows).append((i, j))
    keep_ben = _select_idx([i for i, _ in ben_rows], POOL_CAPS["hh_benign"],
                           rng)
    for i, j in ben_rows:
        if i not in keep_ben:
            continue
        pairs = [p for p in _hh_turns(j["chosen"]) if p[1].strip()]
        while pairs and pairs[0][0] != "user":   # LF 契约：首轮 user
            pairs.pop(0)
        pairs = pairs[:13]
        if not pairs:
            continue
        while pairs and pairs[-1][0] != "assistant":   # 末轮 assistant
            pairs.pop()
        if len(pairs) < 2:
            continue
        last = pairs[-1][1] + "\n" + verdict_line(
            "answer", None, 0.9, [], "default")
        pairs[-1] = ("assistant", last)
        out.append(_item(f"hh-ben-{i:05d}", "general:hh", "default",
                         "en", pairs, row="general_recovery",
                         pool="benign",
                         source="hh-rlhf-harmlessness",
                         surface_key=f"hh:{i}"))
        # DPO 储备（良性对话整对；攻击对话双侧皆不宜作 chosen，不入）
        rej = _hh_turns(j["rejected"])
        if rej and len(rej) >= 2:
            human_all = " ".join(t for r, t in _hh_turns(j["chosen"])
                                 if r == "user")
            dpo.append({"source": "hh-rlhf", "id": f"hh-{i:05d}",
                        "prompt": human_all,
                        "chosen": pairs[-1][1].rsplit("\nVERDICT:", 1)[0],
                        "rejected": rej[-1][1]})
    for i, j in atk_rows:
        pairs = [p for p in _hh_turns(j["chosen"]) if p[1].strip()]
        while pairs and pairs[0][0] != "user":   # LF 契约：首轮 user
            pairs.pop(0)
        if not pairs:
            continue
        # 截到首个攻击 user 轮（无命中则截到末 user 轮），[S] 拒绝收尾
        cut = next((idx for idx, (r, t) in enumerate(pairs)
                    if r == "user" and is_attack(t)[0]),
                   max(0, len(pairs) - 1))
        kept = pairs[:cut + 1][:13]   # >6 轮截断（system 外 ≤13 消息）
        if cut >= 13:
            # 攻击轮被截断丢弃：退化为对攻击查询的单轮拒绝（不拿良性
            # 前缀配拒绝尾——语义错配）
            kept = [("user", pairs[cut][1])]
        else:
            # 截断边界防御：kept 必须以 user 收尾（拼拒绝 assistant 才
            # 满足交替契约）
            while kept and kept[-1][0] != "user":
                kept.pop()
        if not kept:
            continue
        pack = rng.choice(("conservative", "default", "professional"))
        reply = (REFUSAL_REPLY[pack]["en"]
                 + "\n" + verdict_line("refuse", "refuse", 0.95, [],
                                       pack))
        out.append(_item(f"hh-atk-{i:05d}", "T5-attack:hh", pack, "en",
                         kept + [("assistant", reply)],
                         row="multiturn", pool="attack",
                         source="hh-rlhf-harmlessness",
                         surface_key=f"hh:{i}", attack=True))
    return out


def conv_sp(raw: Path, excl: set, rng: random.Random) -> list:
    """§1.2 zh 攻击面主力：instruction_attack [S] 拒绝（Role_Play/Goa
l_
    Hijacking → T8）；typical [R] 复用 + VERDICT。"""
    out = []
    atk_idx, ben_idx = [], []   # 池采样（体量护栏）
    entries = []
    for fname, is_atk in (("instruction_attack_scenarios.json", True),
                          ("typical_safety_scenarios.json", False)):
        j = json.loads((raw / "safety-prompts" / fname).read_text(
            encoding="utf-8"))
        for cat, items in j.items():
            for it in items:
                doc = _dt_sp(it)
                prompt = (it.get("prompt") or "").strip()
                if not prompt or _sha(doc) in excl:
                    continue
                entries.append((is_atk, cat, it, doc))
                (atk_idx if is_atk else ben_idx).append(len(entries) - 1)
    keep_atk = _select_idx(atk_idx, POOL_CAPS["sp_attack"], rng)
    keep_ben = _select_idx(ben_idx, POOL_CAPS["sp_typical"], rng)
    for k, (is_atk, cat, it, doc) in enumerate(entries):
        if k not in keep_atk and k not in keep_ben:
            continue
        prompt = (it.get("prompt") or "").strip()
        resp = (it.get("response") or "").strip()
        if is_atk and k in keep_atk:
            task = ("T8-jailbreak:sp" if cat in
                    ("Role_Play_Instruction", "Goal_Hijacking")
                    else "T5-attack:sp")
            verdict = ("jailbreak-pattern" if task.startswith("T8")
                       else "refuse")
            v = verdict_line("refuse", verdict, 0.95, [], "default")
            reply = (REFUSAL_REPLY["default"]["zh"] + "\n" + v)
            out.append(_item(f"sp-atk-{cat}-{len(out):05d}", task,
                             "default", "zh",
                             [("user", prompt),
                              ("assistant", reply)],
                             row="injection_jailbreak",
                             pool="attack", source="safety-prompts",
                             surface_key=f"sp:{hashlib.md5(doc.encode()).hexdigest()[:10]}",
                             attack=True))
        elif not is_atk and k in keep_ben:
            if not resp:
                continue
            task = ("T7-input:sp-privacy"
                    if cat == "Privacy_And_Property"
                    else f"general:sp-{cat}")
            v = verdict_line("answer", None, 0.9, [], "default")
            out.append(_item(f"sp-typ-{cat}-{len(out):05d}", task,
                             "default", "zh",
                             [("user", prompt),
                              ("assistant", resp + "\n" + v)],
                             row="general_recovery", pool="benign",
                             source="safety-prompts",
                             surface_key=f"sp:{hashlib.md5(doc.encode()).hexdigest()[:10]}"))
    return out


def conv_smt(raw: Path, excl: set, rng: random.Random) -> list:
    """§1.3 多轮关键料：Attack_600 渐进梯度（正常→提醒→拒绝+VERDICT）；
    1K [R] 复用 + 末轮 VERDICT；relationship 并入首轮 user 前缀。"""
    out = []
    a600 = json.loads((raw / "safemtdata" / "Attack_600.json").read_text(
        encoding="utf-8"))
    for it in a600:
        if _sha(_dt_smt(it)) in excl:
            continue
        qs = it.get("multi_turn_queries") or []
        if not qs:
            continue
        rel = (it.get("relationship") or "").strip()
        turns, refused = [], False
        for i, q in enumerate(qs):
            q = str(q).strip()
            if not q:
                continue
            if i == 0 and rel:
                q = f"[背景] {rel}\n\n{q}"
            atk, _ = is_attack(q)
            if atk:
                pack = "default"
                reply = (REFUSAL_REPLY[pack]["en"] + "\n"
                         + verdict_line("refuse", "refuse", 0.95,
                                        ["escalation-stopped"], pack))
                turns += [("user", q), ("assistant", reply)]
                refused = True
                break  # 拒绝即止（升级被阻断——ais-r10 信号）
            if i >= 2:
                bridge = SMT_REMIND["en"]
            else:
                bridge = SMT_BRIDGE["en"][i % len(SMT_BRIDGE["en"])].format(
                    q0=q.split()[0] if q.split() else "that")
            turns += [("user", q), ("assistant", bridge)]
        if not refused and turns:
            last = (turns[-1][1] + "\n"
                    + verdict_line("answer", None, 0.9, [], "default"))
            turns[-1] = ("assistant", last)
        if len(turns) >= 2:
            out.append(_item(f"smt-a-{it.get('id', len(out)):05d}",
                             "T10-multiturn:smt-attack", "default", "en",
                             turns, row="multiturn", pool="multiturn",
                             source="safemtdata",
                             surface_key=f"smt:{it.get('id', len(out))}",
                             attack=refused))
    s1k = json.loads((raw / "safemtdata" / "SafeMTData_1K.json").read_text(
        encoding="utf-8"))
    for it in s1k:
        if _sha(_dt_smt(it)) in excl:
            continue
        convs = it.get("conversations") or []
        rel = (it.get("relationship") or "").strip()
        turns = []
        for c in convs:
            role = {"human": "user", "gpt": "assistant",
                    "user": "user", "assistant": "assistant"}.get(
                        c.get("role"), "user")
            turns.append((role, c.get("content",
                                      c.get("value", "")) or ""))
        turns = _collapse_turns([t for t in turns if t[1].strip()])
        while turns and turns[0][0] != "user":   # LF 契约：首轮 user
            turns.pop(0)
        if not turns:
            continue
        if turns[-1][0] != "assistant":          # 原对话终于 user → 补尾
            turns.append(("assistant",
                          "I can help with that — see above for the "
                          "key points."))
        if rel:
            turns[0] = ("user", f"[背景] {rel}\n\n{turns[0][1]}")
        turns = turns[:13]
        if turns[-1][0] != "assistant":   # 截断落在 user 轮 → 弃尾
            turns = turns[:-1]
        last = turns[-1][1] + "\n" + verdict_line("answer", None, 0.9, [],
                                                  "default")
        turns[-1] = ("assistant", last)
        out.append(_item(f"smt-1k-{it.get('id', len(out)):05d}",
                         "T10-multiturn:smt-1k", "default", "en", turns,
                         row="multiturn", pool="multiturn",
                         source="safemtdata",
                         surface_key=f"smt1k:{it.get('id', len(out))}"))
    return out


def _bench_refusal(sid, task, user_text, source, row="injection_jailbreak"):
    """裸 query 攻击基准（adv/sr/mi）：固定 default 包拒绝（§1.4）。"""
    v = verdict_line("refuse", "refuse", 0.95, [], "default")
    return _item(sid, task, "default", "en",
                 [("user", user_text),
                  ("assistant", REFUSAL_REPLY["default"]["en"] + "\n" + v)],
                 row=row, pool="attack", source=source,
                 surface_key=f"{source}:{hashlib.sha256(user_text.encode()).hexdigest()[:10]}",
                 attack=True)


def conv_benchmarks(raw: Path, excl: set, rng: random.Random) -> list:
    """§1.4 基准六件：adv/sr/mi 裸拒绝；hb 裸+ContextString 载体化；
    xstest 误拒纪律 B 二包；or-bench hard/80k 应答 + toxic 拒绝。"""
    out = []
    # advbench（harmful_strings 不入——字符串载荷无对话语义）
    for row in _csv_rows(raw / "advbench" / "harmful_behaviors.csv"):
        if _sha(_dt_adv(row)) in excl:
            continue
        g = (row.get("goal") or "").strip()
        if g:
            out.append(_bench_refusal(f"adv-{len(out):05d}",
                                      "T5-attack:advbench", g, "advbench"))
    for row in _csv_rows(raw / "strongreject" / "strongreject_dataset.csv"):
        if _sha(_dt_sr(row)) in excl:
            continue
        p = (row.get("forbidden_prompt") or "").strip()
        if p:
            out.append(_bench_refusal(f"sr-{len(out):05d}",
                                      "T5-attack:strongreject", p,
                                      "strongreject"))
    for text in _parquet_col(raw / "maliciousinstruct"
                             / "train-00000-of-00001.parquet", "prompt"):
        if _sha(_dt_mi(text)) in excl:
            continue
        if text.strip():
            out.append(_bench_refusal(f"mi-{len(out):05d}",
                                      "T5-attack:maliciousinstruct",
                                      text.strip(), "maliciousinstruct"))
    # harmbench：裸 + ContextString 载体化（81 条）
    for row in _csv_rows(raw / "harmbench" / "harmbench_behaviors_text_test.csv"):
        if _sha(_dt_hb(row)) in excl:
            continue
        b = (row.get("Behavior") or "").strip()
        ctx = (row.get("ContextString") or "").strip()
        if not b:
            continue
        sem = row.get("SemanticCategory") or "misc"
        if ctx:
            carrier = CarrierBlock(ctype="text", trust="untrusted",
                                   cid="c1", body=ctx)
            user = build_context(role="security_analyst",
                                 authorization="分析授权：只读评估",
                                 policy="default", output_mode="structured",
                                 operator="任务：评估语境化请求",
                                 carriers=[carrier],
                                 user=f"请求：{b}\n\n请评估上述语境中的"
                                      "请求并说明处置。")
            task = f"T5-attack:hb-ctx-{sem}"
            v = verdict_line("refuse", "refuse", 0.95,
                             ["contextualized-attack"], "default")
            reply = ("This context doesn't change the assessment: the "
                     "request is harmful and I can't help.\n" + v)
            out.append(_item(f"hb-ctx-{len(out):05d}", task, "default",
                             "en", [("user", user),
                                    ("assistant", reply)],
                             row="injection_jailbreak", pool="attack",
                             source="harmbench",
                             surface_key=f"harmbench:{row.get('BehaviorID', len(out))}",
                             attack=True))
        else:
            out.append(_bench_refusal(f"hb-{len(out):05d}",
                                      f"T5-attack:hb-{sem}", b, "harmbench"))
    # xstest：safe → B 二包应答（误拒纪律）；unsafe → 拒绝
    for row in _csv_rows(raw / "xstest" / "xstest_prompts.csv"):
        if _sha(_dt_xst(row)) in excl:
            continue
        p = (row.get("prompt") or "").strip()
        if not p:
            continue
        if row.get("label") == "safe":
            for pack in ("default", "professional"):
                reply = OR_ANSWER["en"][len(out) % len(OR_ANSWER["en"])]
                v = verdict_line("answer", None, 0.9, [], pack)
                out.append(_item(f"xst-safe-{pack[:3]}-{len(out):05d}",
                                 "general:xstest-safe", pack, "en",
                                 [("user", p),
                                  ("assistant", reply + "\n" + v)],
                                 row="general_recovery", pool="benign",
                                 source="xstest", or_flag=True,
                                 surface_key=f"xstest:{row.get('id')}"))
        else:
            v = verdict_line("refuse", "refuse", 0.95, [], "default")
            out.append(_item(f"xst-uns-{len(out):05d}",
                             "T5-attack:xstest-unsafe", "default", "en",
                             [("user", p),
                              ("assistant", REFUSAL_REPLY["default"]["en"]
                               + "\n" + v)],
                             row="injection_jailbreak", pool="attack",
                             source="xstest",
                             surface_key=f"xstest:{row.get('id')}",
                             attack=True))
    # or-bench：hard-1k 全量 + 80k 采样 2.5K → [S] 应答 B 二包；toxic → 拒绝
    hard_pool, pool80 = [], []
    for fn, sink in (("or-bench-hard-1k.csv", hard_pool),
                     ("or-bench-80k.csv", pool80)):
        for row in _csv_rows(raw / "or-bench" / fn):
            if _sha(_dt_ob(row)) in excl:
                continue
            p = (row.get("prompt") or "").strip()
            if p:
                sink.append(p)
    rng.shuffle(pool80)
    # hard 全量保底 + 80K 采样 6K（回填批：OR:attack ≥1.25 的 or 盘面）
    ob_pool = hard_pool + pool80[:6000]
    for p in ob_pool:
        for pack in ("default", "professional"):
            reply = OR_ANSWER["en"][len(out) % len(OR_ANSWER["en"])]
            v = verdict_line("answer", None, 0.9, [], pack)
            out.append(_item(f"or-{pack[:3]}-{len(out):05d}",
                             "general:or-bench", pack, "en",
                             [("user", p), ("assistant", reply + "\n" + v)],
                             row="general_recovery", pool="benign",
                             source="or-bench", or_flag=True,
                             surface_key="orb:" + hashlib.sha256(
                                 p.encode()).hexdigest()[:10]))
    for row in _csv_rows(raw / "or-bench" / "or-bench-toxic.csv"):
        if _sha(_dt_ob(row)) in excl:
            continue
        p = (row.get("prompt") or "").strip()
        if p:
            out.append(_bench_refusal(f"or-tox-{len(out):05d}",
                                      "T5-attack:or-toxic", p, "or-bench"))
    return out


def _parquet_col(path: Path, col: str):
    import pyarrow.parquet as pq
    t = pq.read_table(path)
    yield from t.column(col).to_pylist()


def conv_trustllm(raw: Path, excl: set, rng: random.Random) -> list:
    """§1.5：jailbreak T8 / exaggerated 误拒 B 二包 / misuse T5 /
    privacy_leakage 反向设计（检测不揭示，gt 永不入文本）/
    awareness 三包（POL-PRIV-001/002）。"""
    out = []
    base = raw / "trustllm" / "dataset"

    def load(rel):
        return json.loads((base / rel).read_text(encoding="utf-8"))

    for i, it in enumerate(load("safety/jailbreak.json")):
        if _sha(_dt_tl(it)) in excl:
            continue
        p = (it.get("prompt") or "").strip()
        if p:
            v = verdict_line("refuse", "jailbreak-pattern", 0.95, [],
                             "default")
            out.append(_item(f"tl-jb-{i:05d}", "T8-jailbreak:trustllm",
                             "default", "en",
                             [("user", p),
                              ("assistant", REFUSAL_REPLY["default"]["en"]
                               + "\n" + v)],
                             row="injection_jailbreak", pool="attack",
                             source="trustllm-safety",
                             surface_key=f"tljb:{i}", attack=True))
    for i, it in enumerate(load("safety/exaggerated_safety.json")):
        if _sha(_dt_tl(it)) in excl:
            continue
        p = (it.get("prompt") or "").strip()
        if not p:
            continue
        for pack in ("default", "professional"):
            reply = OR_ANSWER["en"][i % len(OR_ANSWER["en"])]
            v = verdict_line("answer", None, 0.9, [], pack)
            out.append(_item(f"tl-ex-{pack[:3]}-{i:05d}",
                             "general:trustllm-exag", pack, "en",
                             [("user", p), ("assistant", reply + "\n" + v)],
                             row="general_recovery", pool="benign",
                             source="trustllm-safety", or_flag=True,
                             surface_key=f"tlex:{i}"))
    for i, it in enumerate(load("safety/misuse.json")):
        if _sha(_dt_tl(it)) in excl:
            continue
        p = (it.get("prompt") or "").strip()
        if p:
            v = verdict_line("refuse", "refuse", 0.95, [], "default")
            out.append(_item(f"tl-mi-{i:05d}", "T5-attack:trustllm-misuse",
                             "default", "en",
                             [("user", p),
                              ("assistant", REFUSAL_REPLY["default"]["en"]
                               + "\n" + v)],
                             row="injection_jailbreak", pool="attack",
                             source="trustllm-safety",
                             surface_key=f"tlmi:{i}", attack=True))
    # privacy_leakage 反向设计：载体化 + 检测/分级响应（gt-* 不入文本）
    for i, it in enumerate(load("privacy/privacy_leakage.json")):
        if _sha(_dt_tl(it)) in excl:
            continue
        p = (it.get("prompt") or "").strip()
        if not p:
            continue
        carrier = CarrierBlock(ctype="text", trust="untrusted", cid="c1",
                               body=p)
        user = build_context(role="security_analyst",
                             authorization="分析授权：只读评估",
                             policy="default", output_mode="structured",
                             operator="任务：个人信息暴露检测",
                             carriers=[carrier],
                             user="请分析上述文本中的个人信息暴露情况并给出处理建议。")
        reply = LEAK_DETECT["en"]
        v = verdict_line("report", "contains-pii", 0.9,
                         ["pii-in-untrusted-carrier"], "default")
        out.append(_item(f"tl-lk-{i:05d}", "T7-pii:trustllm-leakage",
                         "default", "en",
                         [("user", user), ("assistant", reply + "\n" + v)],
                         row="task_single", pool="detection",
                         source="trustllm-safety",
                         surface_key=f"tllk:{i}", attack=False))
    # privacy_awareness（query+confAIde）三包条件化
    for tag, rel in (("aq", "privacy/privacy_awareness_query.json"),
                     ("ca", "privacy/privacy_awareness_confAIde.json")):
        for i, it in enumerate(load(rel)):
            if _sha(_dt_tl(it)) in excl:
                continue
            p = (it.get("prompt") or it.get("question") or "").strip()
            if not p:
                continue
            for pack in ("conservative", "default", "professional"):
                act, verdict = AWARENESS_VERDICT[pack]
                reply = AWARENESS_REPLY[pack]["en"]
                v = verdict_line(act, verdict, 0.9, [], pack)
                out.append(_item(f"tl-{tag}-{pack[:3]}-{i:05d}",
                                 "T7-privacy:trustllm-awareness", pack,
                                 "en",
                                 [("user", p),
                                  ("assistant", reply + "\n" + v)],
                                 row="policy_pairs", pool="policy",
                                 source="trustllm-safety",
                                 surface_key=f"tl{tag}:{i}"))
    return out


def conv_cvalues(raw: Path, excl: set, rng: random.Random, dpo: list) -> list:
    """§1.6 zh 偏好对：pos_resp [R] 复用（良性）；攻击 prompt [S] 三包拒绝
    + 表面改述（短模板过拟合防护）；neg/pos 对整条进 DPO。"""
    out = []
    atk_idx, ben_idx = [], []   # 池采样后再转换（体量护栏）
    rows = []
    for fname in ("harmless_train.json", "helpful_train.json"):
        for i, r in enumerate(json.loads(
                (raw / "cvalues" / fname).read_text(encoding="utf-8"))):
            p = (r.get("prompt") or "").strip()
            if not p or _sha(_dt_cv(r)) in excl:
                continue
            rows.append((fname, i, r))
            (atk_idx if is_attack(p)[0] else ben_idx).append(len(rows) - 1)
    keep_atk = _select_idx(atk_idx, POOL_CAPS["cv_attack"], rng)
    keep_ben = _select_idx(ben_idx, POOL_CAPS["cv_benign"], rng)
    for k, (fname, i, r) in enumerate(rows):
        if k not in keep_atk and k not in keep_ben:
            continue
        p = (r.get("prompt") or "").strip()
        pos = (r.get("pos_resp") or "").strip()
        neg = (r.get("neg_resp") or "").strip()
        dpo.append({"source": "cvalues", "id": f"cv-{fname[:4]}-{i:05d}",
                    "prompt": p, "chosen": pos, "rejected": neg})
        if k in keep_atk and is_attack(p)[0]:
            wrapped = rng.choice(_surface_forms(p, "zh"))
            for pack in ("conservative", "default", "professional"):
                v = verdict_line("refuse", "refuse", 0.95, [], pack)
                out.append(_item(
                    f"cv-atk-{pack[:3]}-{i:05d}", "T5-attack:cvalues",
                    pack, "zh",
                    [("user", wrapped),
                     ("assistant", REFUSAL_REPLY[pack]["zh"] + "\n" + v)],
                    row="policy_pairs", pool="attack",
                    source="cvalues", surface_key=f"cv:{i}",
                    attack=True))
        elif k in keep_ben and pos:
            v = verdict_line("answer", None, 0.9, [], "default")
            out.append(_item(f"cv-ben-{i:05d}", "general:cvalues",
                             "default", "zh",
                             [("user", p), ("assistant", pos + "\n" + v)],
                             row="general_recovery", pool="benign",
                             source="cvalues",
                             surface_key=f"cv:{i}"))
    return out


def conv_pku(raw: Path, excl: set, rng: random.Random, dpo: list) -> list:
    """§1.7：攻击 prompt [S] 三包拒绝；良性 [R] safer 侧 + VERDICT；
    is_safe=false 响应永不 assistant；better/safer 对进 DPO（train split）。"""
    out = []
    atk_idx, ben_idx = [], []   # 池采样后再转换（体量护栏）
    rows = []
    for p_ in sorted((raw / "pku-saferlhf" / "data").rglob("train.jsonl")):
        for i, j in enumerate(_jsonl_rows(p_)):
            prompt = (j.get("prompt") or "").strip()
            if not prompt or _sha(_dt_pku(j)) in excl:
                continue
            rows.append((p_, i, j))
            (atk_idx if is_attack(prompt)[0] else ben_idx).append(
                len(rows) - 1)
    keep_atk = _select_idx(atk_idx, POOL_CAPS["pku_attack"], rng)
    keep_ben = _select_idx(ben_idx, POOL_CAPS["pku_benign"], rng)
    for k, (p_, i, j) in enumerate(rows):
        if k not in keep_atk and k not in keep_ben:
            continue
        prompt = (j.get("prompt") or "").strip()
        r0, r1 = (j.get("response_0") or "").strip(), (
            j.get("response_1") or "").strip()
        safer = str(j.get("safer_response_id", "0"))
        safer_resp = r1 if safer == "1" else r0
        other_resp = r0 if safer == "1" else r1
        dpo.append({"source": "pku-saferlhf",
                    "id": f"pku-{p_.parent.name}-{i:05d}",
                    "prompt": prompt, "chosen": safer_resp,
                    "rejected": other_resp})
        if k in keep_atk and is_attack(prompt)[0]:
            for pack in ("conservative", "default", "professional"):
                v = verdict_line("refuse", "refuse", 0.95, [], pack)
                out.append(_item(
                    f"pku-atk-{pack[:3]}-{i:05d}", "T5-attack:pku", pack,
                    "en", [("user", prompt),
                           ("assistant", REFUSAL_REPLY[pack]["en"]
                            + "\n" + v)],
                    row="policy_pairs", pool="attack",
                    source="pku-saferlhf", surface_key=f"pku:{i}",
                    attack=True))
        elif k in keep_ben:
            if not safer_resp:
                continue
            safer_is_safe = str(j.get(
                f"is_response_{safer}_safe", "True"))
            if safer_is_safe == "False":
                continue  # 双响应均不安全 → 放弃（不入 assistant）
            v = verdict_line("answer", None, 0.9, [], "default")
            out.append(_item(f"pku-ben-{i:05d}", "general:pku",
                             "default", "en",
                             [("user", prompt),
                              ("assistant", safer_resp + "\n" + v)],
                             row="general_recovery", pool="benign",
                             source="pku-saferlhf",
                             surface_key=f"pku:{i}"))
    return out


def conv_beavertails(raw: Path, excl: set, rng: random.Random,
                     dpo: list) -> list:
    """§1.8：30K train 为 SFT 池界（unsafe prompt [S] 拒绝 / safe 响应
    [R]）；330K train 采样作 DPO 对；is_safe=false 响应永不 assistant。"""
    out = []
    rows30 = [j for j in _gz_jsonl_rows(
        raw / "beavertails" / "round0" / "30k" / "train.jsonl.gz")]
    by_prompt = defaultdict(lambda: {"safe": [], "unsafe": []})
    for j in rows30:
        if _sha(_dt_bt(j)) in excl:
            continue
        p = (j.get("prompt") or "").strip()
        r = (j.get("response") or "").strip()
        if not p:
            continue
        key = ("safe" if str(j.get("is_safe")) == "True" else "unsafe")
        by_prompt[p][key].append(r)
    n_atk = n_ben = 0
    for p, pools in by_prompt.items():
        atk, _ = is_attack(p)
        if (atk or pools["unsafe"]) and n_atk < 1000:
            v = verdict_line("refuse", "refuse", 0.95, [], "default")
            out.append(_item(f"bt-atk-{n_atk:05d}", "T5-attack:beavertails",
                             "default", "en",
                             [("user", p),
                              ("assistant", REFUSAL_REPLY["default"]["en"]
                               + "\n" + v)],
                             row="injection_jailbreak", pool="attack",
                             source="beavertails",
                             surface_key="bt:" + hashlib.sha256(
                                 p.encode()).hexdigest()[:10], attack=True))
            n_atk += 1
        elif pools["safe"] and n_ben < 1000:
            resp = pools["safe"][0]
            v = verdict_line("answer", None, 0.9, [], "default")
            out.append(_item(f"bt-ben-{n_ben:05d}", "general:beavertails",
                             "default", "en",
                             [("user", p), ("assistant", resp + "\n" + v)],
                             row="general_recovery", pool="benign",
                             source="beavertails",
                             surface_key="bt:" + hashlib.sha256(
                                 p.encode()).hexdigest()[:10]))
            n_ben += 1
        # DPO 对（30K）：safe × unsafe 同 prompt 配对
        if pools["safe"] and pools["unsafe"]:
            dpo.append({"source": "beavertails",
                        "id": "bt-" + hashlib.sha256(
                            p.encode()).hexdigest()[:10],
                        "prompt": p, "chosen": pools["safe"][0],
                        "rejected": pools["unsafe"][0]})
    # 330K train 采样 20K 作 DPO 补充（池界外不进 SFT）
    import lzma
    n330 = 0
    with lzma.open(raw / "beavertails" / "round0" / "330k" /
                   "train.jsonl.xz", "rt", encoding="utf-8",
                   errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            j = json.loads(line)
            p = (j.get("prompt") or "").strip()
            if not p:
                continue
            n330 += 1
            if n330 % 15 != 0:  # ~20K/300K 确定性采样
                continue
            r = (j.get("response") or "").strip()
            if not r:
                continue
            if str(j.get("is_safe")) == "False":
                dpo.append({"source": "beavertails-330k",
                            "id": f"bt330-{n330:06d}", "prompt": p,
                            "chosen": None, "rejected": r})
    return out


def conv_wj(raw: Path, excl: set, rng: random.Random) -> list:
    """§1.9：vanilla/adversarial 对保序同 attack_surface_id（paraphrase
    阶梯）；harmful [S] 拒绝（D 随机包）；benign completion [R] + VERDICT；
    eval.tsv 永不入。"""
    out = []
    with open(raw / "wildjailbreak" / "train" / "train.tsv",
              encoding="utf-8", newline="") as f:
        rd = csv.reader(f, delimiter="\t")
        header = next(rd, None)
        if not header:
            return out
        rows = [(i, row) for i, row in enumerate(rd)
                if len(row) == len(header)
                and _sha(_dt_wj(row)) not in excl]
    atk = [k for k, (i, r) in enumerate(rows)
           if r[3].endswith("_harmful")]
    ben = [k for k in range(len(rows)) if k not in set(atk)]
    keep_atk = _select_idx(atk, POOL_CAPS["wj_rows"], rng)
    keep_ben = _select_idx(ben, POOL_CAPS["wj_benign_rows"], rng)
    for k, (i, row) in enumerate(rows):
        vanilla, adversarial, completion, dtype = row
        if dtype.endswith("_harmful"):
            if k not in keep_atk:
                continue
            sid = f"wj:{i}"
            for tag, text in (("v", vanilla), ("a", adversarial)):
                if not text.strip():
                    continue
                pack = rng.choice(("conservative", "default",
                                   "professional"))
                v = verdict_line("refuse", "refuse", 0.95, [], pack)
                out.append(_item(
                    f"wj-{tag}-{i:06d}", "T5-attack:wildjailbreak", pack,
                    "en", [("user", text.strip()),
                           ("assistant", REFUSAL_REPLY[pack]["en"]
                            + "\n" + v)],
                    row="injection_jailbreak", pool="attack",
                    source="wildjailbreak", surface_key=sid,
                    attack=True))
        else:
            if k not in keep_ben:
                continue
            c = (completion or "").strip()
            if not c:
                continue
            v = verdict_line("answer", None, 0.9, [], "default")
            out.append(_item(f"wj-ben-{i:06d}", "general:wj-benign",
                             "default", "en",
                             [("user", (vanilla or adversarial).strip()),
                              ("assistant", c + "\n" + v)],
                             row="general_recovery", pool="benign",
                             source="wildjailbreak", or_flag=True,
                             surface_key=f"wjben:{i}"))
    return out


def conv_wgm(raw: Path, excl: set, rng: random.Random) -> list:
    """§1.10：harmful×refusal [R] 拒绝对；harmful×compliance → 回复审查
    样本（载体化，task ③）；unharmful [R] 应答（B 二包采样作误拒纪律）；
    test.parquet 永不入；任务④自我修正 M2 低优先跳过。"""
    out = []
    n_ref = n_rev = n_ben = n_benB = 0
    for row in _parquet_rows(raw / "wildguardmix" / "train"
                             / "wildguard_train.parquet"):
        if _sha(_dt_wgm(row)) in excl:
            continue
        p = (row.get("prompt") or "").strip()
        if not p:
            continue
        harm = str(row.get("prompt_harm_label")) == "harmful"
        refusal = str(row.get("response_refusal_label"))
        resp = (row.get("response") or "").strip()
        if harm and refusal == "refusal" and resp and n_ref < 8000:
            v = verdict_line("refuse", "refuse", 0.95, [], "default")
            out.append(_item(f"wgm-ref-{n_ref:06d}",
                             "T5-attack:wgm-refusal", "default", "en",
                             [("user", p),
                              ("assistant", resp + "\n" + v)],
                             row="injection_jailbreak", pool="attack",
                             source="wildguardmix",
                             surface_key="wgm:" + hashlib.sha256(
                                 p.encode()).hexdigest()[:10], attack=True))
            n_ref += 1
        elif harm and resp and n_rev < 8000:
            # 回复审查（审查其他模型输出——docs/04.4 T8 职能）
            body = (f"User asked: {p}\n\nAssistant replied: {resp}")
            carrier = CarrierBlock(ctype="text", trust="untrusted",
                                   cid="c1", body=body)
            user = build_context(role="security_analyst",
                                 authorization="分析授权：只读评估",
                                 policy="default",
                                 output_mode="structured",
                                 operator="任务：回复安全审查",
                                 carriers=[carrier],
                                 user="请审查上述助手回复的安全性并给出结论。")
            resp_harm = str(row.get("response_harm_label")) == "harmful"
            reply = (REVIEW_UNSAFE if resp_harm else REVIEW_SAFE)["en"]
            verdict = ("harmful-response" if resp_harm else "normal")
            v = verdict_line("report", verdict, 0.9,
                             ["response-review"], "default")
            out.append(_item(f"wgm-rev-{n_rev:06d}",
                             "T8-review:wgm", "default", "en",
                             [("user", user),
                              ("assistant", reply + "\n" + v)],
                             row="task_single", pool="detection",
                             source="wildguardmix",
                             surface_key="wgmrev:" + hashlib.sha256(
                                 body.encode()).hexdigest()[:10]))
            n_rev += 1
        elif not harm and resp:
            if n_benB < 4000 and rng.random() < 0.25:
                for pack in ("default", "professional"):
                    v = verdict_line("answer", None, 0.9, [], pack)
                    out.append(_item(
                        f"wgm-benB-{pack[:3]}-{n_benB:06d}",
                        "general:wgm-unharmful", pack, "en",
                        [("user", p), ("assistant", resp + "\n" + v)],
                        row="general_recovery", pool="benign",
                        source="wildguardmix", or_flag=True,
                        surface_key="wgmben:" + hashlib.sha256(
                            p.encode()).hexdigest()[:10]))
                n_benB += 1
            elif n_ben < 8000:
                v = verdict_line("answer", None, 0.9, [], "default")
                out.append(_item(
                    f"wgm-ben-{n_ben:06d}", "general:wgm-unharmful",
                    "default", "en",
                    [("user", p), ("assistant", resp + "\n" + v)],
                    row="general_recovery", pool="benign",
                    source="wildguardmix", or_flag=True,
                    surface_key="wgmben:" + hashlib.sha256(
                        p.encode()).hexdigest()[:10]))
                n_ben += 1
    return out


def conv_selfbuilt(v0_dir: Path, v0x_dir: Path = None) -> list:
    """§1.13 自建 v0+v0x 全量纳入（A/Ax/T4→政策配对行 / B/攻击词典→
    注入行 / 检测类→任务行 / 走私多轮→多轮行）；样本已含
    pack/lang/messages，直通。"""
    out = []

    def _emit(corpus: str, j: dict) -> None:
        if corpus in ("v0:policy_pairs", "v0x:policy_expansion",
                      "v0x:t4_grounding"):
            row, attack = "policy_pairs", False
        elif corpus == "v0:injection_pairs":
            clean = "clean-control" in j["task"]
            row = "injection_jailbreak" if not clean else "task_single"
            attack = not clean
        elif corpus == "v0x:attack_dict":
            row, attack = "injection_jailbreak", True
        elif corpus == "v0x:smuggle_multiturn":
            row = "multiturn"
            attack = ":attack:" in j["task"]
        else:
            row, attack = "task_single", False
        out.append({"id": j["id"], "task": j["task"], "pack": j["pack"],
                    "lang": j["lang"], "messages": j["messages"],
                    "row": row, "pool": "selfbuilt", "source": corpus,
                    "surface_key": f"{corpus}:{j['id']}",
                    "or_flag": False, "attack": attack})

    for f in sorted(v0_dir.glob("*.jsonl")):
        corpus = f.stem
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                _emit(f"v0:{corpus}", json.loads(ln))
    if v0x_dir is not None:
        for f in sorted(Path(v0x_dir).glob("*.jsonl")):
            corpus = f.stem
            for ln in f.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    _emit(f"v0x:{corpus}", json.loads(ln))
    return out


def _surface_forms(q: str, lang: str) -> list:
    return [q] + [w.format(q=q) for w in SURFACE_WRAPPERS[lang]]


# ================================================================= 去重 ===
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def _ngrams(text: str, n: int = 8) -> set:
    t = _norm(text)
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


DEDUP_PRIORITY = {"v0": 0, "harmbench": 1, "wildjailbreak": 2,
                  "wildguardmix": 3, "advbench": 4, "strongreject": 4,
                  "maliciousinstruct": 4, "xstest": 4, "or-bench": 4,
                  "safety-prompts": 5, "trustllm-safety": 5, "cvalues": 6,
                  "pku-saferlhf": 6, "beavertails": 7,
                  "hh-rlhf-harmlessness": 7, "safemtdata": 8}


def dedup(items: list) -> tuple[list, dict]:
    """§4 跨源 8-gram containment 去重：攻击池 ≥0.6 / 良性池 ≥0.5；
    attack_surface_id 组内豁免（组=去重单元，组内变体全保留）；
    保序 = DEDUP_PRIORITY（信息量优先 hb>wj>wgm>bench>sp）。
    同源不去重（表面改述/多轮是有意的近重复）。
    高频 gram（>500 组共用）跳过候选收集——公共短语，containment 命中
    不会只靠它达到阈值（性能护栏，语义影响可忽略）。"""
    groups = defaultdict(list)   # (source, surface_key) -> items
    for it in items:
        groups[(it["source"], it["surface_key"])].append(it)
    ordered = sorted(groups.items(),
                     key=lambda kv: (DEDUP_PRIORITY.get(kv[0][0], 9),
                                     kv[0][0], kv[0][1]))
    kept, gram_index, group_grams = [], defaultdict(set), {}
    dropped = Counter()
    for (source, skey), members in ordered:
        pool = members[0]["pool"]
        if pool not in ("attack", "benign"):
            kept.extend(members)   # policy/detection/multiturn/selfbuilt 不去重
            continue
        threshold = 0.6 if pool == "attack" else 0.5
        query_text = " ".join(m["messages"][1]["content"]
                              for m in members if len(m["messages"]) > 1)
        grams = _ngrams(query_text)
        if not grams:
            kept.extend(members)
            continue
        cand = set()
        for g in grams:
            posting = gram_index.get(g)
            if posting and len(posting) <= 500:
                cand.update(posting)
        clash = False
        for other_key in cand:
            other_grams = group_grams[other_key]
            inter = len(grams & other_grams)
            if inter and inter / min(len(grams), len(other_grams)) \
                    >= threshold:
                clash = True
                dropped[source] += len(members)
                break
        if not clash:
            kept.extend(members)
            gk = (source, skey)
            group_grams[gk] = grams
            for g in grams:
                gram_index[g].add(gk)
    return kept, {"dropped_items": dict(dropped),
                  "n_groups": len(group_grams)}


# ============================================================== 配比采样 ===
SUBCAPS = {   # §6 子项（回填批定标：OR:attack≥1.25 / zh:en≥35:65 / 96K±10%
    # —— 攻击预算：注入行 ≤11K、政策行 cv/pku 攻击侧收窄（OR 盘面换空间）
    ("policy_pairs", "cvalues"): 4800,
    ("policy_pairs", "pku-saferlhf"): 3600,
    ("policy_pairs", "trustllm-safety"): 100000,
    ("policy_pairs", "v0:policy_pairs"): 100000,
    ("policy_pairs", "v0x:policy_expansion"): 100000,
    ("policy_pairs", "v0x:t4_grounding"): 100000,
    ("task_single", "wildguardmix"): 12000,
    ("task_single", "trustllm-safety"): 100000,
    ("task_single", "v0:injection_pairs"): 100000,
    ("task_single", "v0:pii_synthetic"): 100000,
    ("task_single", "v0:calibration"): 100000,
    ("task_single", "v0x:t1_injection"): 100000,
    ("task_single", "v0x:t3_risk"): 100000,
    ("task_single", "v0x:t9_phish"): 100000,
    ("task_single", "v0x:t12_policyqa"): 100000,
    ("task_single", "v0x:t6_code"): 100000,
    ("task_single", "v0x:pii_expansion"): 100000,
    ("injection_jailbreak", "harmbench"): 320,
    ("injection_jailbreak", "advbench"): 520,
    ("injection_jailbreak", "maliciousinstruct"): 100,
    ("injection_jailbreak", "strongreject"): 313,
    ("injection_jailbreak", "wildjailbreak"): 1500,
    ("injection_jailbreak", "wildguardmix"): 1400,
    ("injection_jailbreak", "safety-prompts"): 1400,
    ("injection_jailbreak", "trustllm-safety"): 1400,
    ("injection_jailbreak", "xstest"): 200,
    ("injection_jailbreak", "or-bench"): 655,
    ("injection_jailbreak", "beavertails"): 500,
    ("injection_jailbreak", "hh-rlhf-harmlessness"): 1000,
    ("injection_jailbreak", "v0:injection_pairs"): 500,
    ("injection_jailbreak", "v0x:attack_dict"): 1860,
    ("multiturn", "safemtdata"): 2280,
    ("multiturn", "hh-rlhf-harmlessness"): 2500,
    ("multiturn", "v0x:smuggle_multiturn"): 100000,
    # —— OR 盘面（or_flag 优先）+ zh 良性盘面（拉回 zh:en ≥35:65）
    ("general_recovery", "xstest"): 450,
    ("general_recovery", "or-bench"): 15000,
    ("general_recovery", "trustllm-safety"): 400,
    ("general_recovery", "wildguardmix"): 12000,
    ("general_recovery", "hh-rlhf-harmlessness"): 2000,
    ("general_recovery", "safety-prompts"): 13270,
    ("general_recovery", "cvalues"): 7000,
    ("general_recovery", "wildjailbreak"): 3000,
    ("general_recovery", "pku-saferlhf"): 6000,
    ("general_recovery", "beavertails"): 1000,
}


def ratio_sample(items: list, rng: random.Random) -> tuple[list, dict]:
    """行配比采样（可用量纪律）：行内按 §6 子项上限采样（or_flag 误拒
    纪律优先），上限即边界——**不突破**；行缺口如实上报（自建扩容未
    到位时行短于定标是预期状态，校准跑后按缺口回填）。"""
    by_row = defaultdict(list)
    for it in items:
        by_row[it["row"]].append(it)
    picked = []
    stats = {}
    for row, quota in ROW_QUOTA.items():
        pool = by_row.get(row, [])
        rng.shuffle(pool)
        selected, used = [], Counter()
        # 子项上限内采样（or_flag 优先，稳定排序保持随机序）
        for it in sorted(pool, key=lambda x: not x["or_flag"]):
            cap = SUBCAPS.get((row, it["source"]))
            if cap is not None and used[it["source"]] >= cap:
                continue
            if len(selected) < quota:
                selected.append(it)
                used[it["source"]] += 1
        picked += selected
        stats[row] = {"quota": quota, "picked": len(selected),
                      "deficit": quota - len(selected),
                      "by_source": dict(used)}
    return picked, stats


# ================================================================== 主流程 ===
def assemble(raw: Path = RAW, v0_dir: Path = V0_DIR, v0x_dir: Path = V0X_DIR,
             excl_path: Path = EXCL_JSON, out_dir: Path = OUT_DIR,
             dpo_dir: Path = DPO_DIR, audit_n: int = 0,
             small: bool = False) -> dict:
    rng = random.Random(SEED)
    excl = load_exclusions(excl_path)
    dpo = []
    items = []
    items += conv_hh(raw, excl.get("hh-rlhf-harmlessness", set()), rng, dpo)
    items += conv_sp(raw, excl.get("safety-prompts", set()), rng)
    items += conv_smt(raw, excl.get("safemtdata", set()), rng)
    items += conv_benchmarks(raw, excl.get("advbench", set())
                             | excl.get("harmbench", set())
                             | excl.get("strongreject", set())
                             | excl.get("maliciousinstruct", set())
                             | excl.get("xstest", set())
                             | excl.get("or-bench", set()), rng)
    items += conv_trustllm(raw, excl.get("trustllm-safety", set()), rng)
    items += conv_cvalues(raw, excl.get("cvalues", set()), rng, dpo)
    items += conv_pku(raw, excl.get("pku-saferlhf", set()), rng, dpo)
    items += conv_beavertails(raw, excl.get("beavertails", set()), rng, dpo)
    items += conv_wj(raw, excl.get("wildjailbreak", set()), rng)
    items += conv_wgm(raw, excl.get("wildguardmix", set()), rng)
    items += conv_selfbuilt(v0_dir, v0x_dir)
    n_converted = len(items)

    if small:   # 测试模式：跳过全量去重采样（小 fixture 直接返回）
        return {"items": items, "dpo": dpo, "n_converted": n_converted}

    items, dedup_stats = dedup(items)
    picked, row_stats = ratio_sample(items, rng)
    rng.shuffle(picked)

    # DPO 出库净化：rejected（武器化/劣侧）文本不得以主集 assistant 形态
    # 存在——hh 源内重复对话会让同文异位（A 行 rejected = B 行 chosen），
    # 此处按内容哈希硬隔离（≥60 字符实质内容；短泛用短语不计）
    main_assistant_h = {_sha(m["content"]) for it in picked
                        for m in it["messages"]
                        if m["role"] == "assistant"}
    n_dpo_raw = len(dpo)
    dpo = [d for d in dpo
           if not (d.get("rejected") and len(d["rejected"]) >= 60
                   and _sha(d["rejected"]) in main_assistant_h)]
    n_dpo_purged = n_dpo_raw - len(dpo)

    # ---- 输出 ----
    out_dir.mkdir(parents=True, exist_ok=True)
    dpo_dir.mkdir(parents=True, exist_ok=True)
    train = out_dir / "train.jsonl"
    with open(train, "w", encoding="utf-8", newline="\n") as f:
        for it in picked:
            f.write(json.dumps({"id": it["id"], "task": it["task"],
                                "pack": it["pack"], "lang": it["lang"],
                                "messages": it["messages"]},
                               ensure_ascii=False) + "\n")
    dpo_by_src = defaultdict(list)
    for d in dpo:
        dpo_by_src[d["source"].split("-330k")[0].replace(
            "hh-rlhf", "hh")].append(d)
    for src, rows in sorted(dpo_by_src.items()):
        p = dpo_dir / f"{src}.jsonl"
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            for d in rows:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # ---- 统计 ----
    packs = Counter(it["pack"] for it in picked)
    langs = Counter(it["lang"] for it in picked)
    tasks = Counter(it["task"].split(":")[0] for it in picked)
    or_n = sum(1 for it in picked if it["or_flag"])
    atk_n = sum(1 for it in picked if it["attack"])
    actions = Counter()
    for it in picked:
        last = [m for m in it["messages"] if m["role"] == "assistant"][-1]
        if "VERDICT: " in last["content"]:
            actions[json.loads(last["content"].rsplit("VERDICT: ", 1)[1])
                    ["action"]] += 1
    meta = {"n_converted": n_converted, "n_after_dedup": len(items),
            "n_train": len(picked), "rows": row_stats,
            "dedup": dedup_stats, "packs": dict(packs),
            "langs": dict(langs), "task_families": dict(tasks),
            "actions": dict(actions),
            "or_discipline_n": or_n, "attack_n": atk_n,
            "or_to_attack_ratio": round(or_n / atk_n, 3) if atk_n else None,
            "dpo_reserve": {s: len(r) for s, r in dpo_by_src.items()},
            "dpo_purged_rejected_in_main": n_dpo_purged,
            "quota_targets": ROW_QUOTA,
            "row_deficit": {r: st["deficit"] for r, st in row_stats.items()},
            "deficit_note": ("自建扩容缺口（§6 列明、生成器尚未扩容）："
                             "政策配对 ~28K（A 扩容 10K+T4 场景 7K）、"
                             "任务族 ~19K（T1/T3/T9 8K+T12 4K+B/C 扩容）、"
                             "注入 ~3K（攻击词典 2.3K）、多轮 ~3.8K（走私"
                             "构造 5K）——校准跑错误分析后按缺口回填"),
            "seed": SEED}
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    _write_readme(out_dir, meta)
    return meta


def _write_readme(out_dir: Path, meta: dict) -> None:
    zh = meta["langs"].get("zh", 0)
    en = meta["langs"].get("en", 0)
    tot = max(1, zh + en)
    lines = [
        "# SFT M1（M2 全量组装首版）",
        "",
        "由 `scripts/assemble_sft_m2.py` 生成（seed 固定，可复现）；",
        "规格：docs/research/m2-data-assembly-plan.md（§9 实现摘要；",
        "行配比以 §6 定稿为准）。**本目录不含 LF 注册**——`--register-lf`",
        "显式触发后才写 data/lf/sft_m1.jsonl 并登记 `sec_sft_m1`。",
        "",
        "## 组成",
        "",
        f"- 共 {meta['n_train']} 条（转换 {meta['n_converted']} → 去重后 "
        f"{meta['n_after_dedup']} → 采样）",
        f"- zh:en = {zh}:{en}（{zh / tot:.0%}:{en / tot:.0%}；目标 40:60）",
        f"- OR(误拒纪律):攻击 = {meta['or_to_attack_ratio']}（目标≈1.25:1）",
        "",
        "| 行 | 采得 | 缺口 | 定标 |",
        "|---|---|---|---|",
    ]
    for row, st in meta["rows"].items():
        lines.append(f"| {row} | {st['picked']} | {st['deficit']} | "
                     f"{st['quota']} |")
    lines += [
        "",
        "## 行定义（§6）",
        "- policy_pairs：三包条件化政策行为（v0 政策对 + cvalues/pku",
        "  攻击面三包拒绝 + trustllm 隐私意识三包）",
        "- task_single：检测/审查任务（v0 注入/PII/校准 + trustllm 泄漏",
        "  检测 + wgm 回复审查）",
        "- injection_jailbreak：攻击识别与拒绝（adv/sr/mi/hb/wj/wgm/",
        "  sp/trustllm/xstest-unsafe/or-toxic/beavertails/v0 注入）",
        "- multiturn：多轮渐进（safemtdata 梯度 + hh 截断对话）",
        "- general_recovery：良性恢复与误拒纪律（xstest/or-bench/exag/",
        "  wgm-unharmful B 二包 + hh/sp/cvalues/pku 良性复用）",
        "",
        "## 纪律",
        "- 全部 assistant 以 VERDICT 行结尾（多轮仅末轮——§7）；",
        "- 武器化响应永不入 assistant（neg/unsafe 侧整对进",
        " data/sft/dpo-reserve/，M3 偏好阶段用）；",
        "- trustllm privacy_leakage 为反向设计：检测/分级不揭示，",
        " gt-* 不入任何训练文本；",
        "- 工具输出载体族零生成（docs/06 §7 留出族）；",
        "- 排除：reports/sft-exclusion-hashes.json（污染∪红线，内容",
        " 哈希——生成器不接触评估路径）；",
        "- 攻击意图池切分为规则版分类器（§1.14 降级方案）；实测与",
        " 抽检见 reports/m2-pool-split-audit.json。",
        "",
        "## VERDICT 词表扩展（v0.1 草案，校准跑定稿）",
        "- 新增 verdict 值 `harmful-response`（wgm 回复审查任务：被审",
        "  回复含应拦截的有害内容）与 `normal`（审查通过）。",
        "",
        "## 自建扩容缺口（校准跑后回填）",
        meta["deficit_note"],
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def audit_pool_split(raw: Path = RAW, n: int = 100,
                     out: Path = AUDIT_JSON) -> dict:
    """规则版分类器抽检支持件：①wgm 人标实测（prompt_harm_label 为
    prompt 级真值——准确率/查全）；②n 条池切分决策清单供人工抽检。"""
    rows = list(_parquet_rows(raw / "wildguardmix" / "train"
                              / "wildguard_train.parquet"))
    import random as _r
    rng = _r.Random(SEED)
    sample = rng.sample(rows, min(3000, len(rows)))
    tp = fp = tn = fn = 0
    for row in sample:
        p = row.get("prompt") or ""
        pred, _ = is_attack(p)
        truth = str(row.get("prompt_harm_label")) == "harmful"
        if pred and truth:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif not pred and truth:
            fn += 1
        else:
            tn += 1
    acc = (tp + tn) / max(1, tp + fp + tn + fn)
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    # 抽检清单：跨 hh/pku/cvalues/sp 各抽（人工核）
    audit = []
    hh_rows = list(_gz_jsonl_rows(RAW / "hh-rlhf" / "harmless-base"
                                  / "train.jsonl.gz"))[:2000]
    cv = json.loads((RAW / "cvalues" / "harmless_train.json").read_text(
        encoding="utf-8"))[:2000]
    spj = json.loads((RAW / "safety-prompts"
                      / "instruction_attack_scenarios.json").read_text(
        encoding="utf-8"))
    sp_flat = [it for items in spj.values() for it in items][:2000]
    pools = ([("hh", r.get("chosen", "")[:300]) for r in hh_rows[:40]]
             + [("cvalues", r.get("prompt", "")[:300]) for r in cv[:40]]
             + [("sp-attack", it.get("prompt", "")[:300])
                for it in sp_flat[:40]])
    for src, text in pools[:n]:
        pred, hits = is_attack(text)
        audit.append({"source": src, "excerpt": text[:160],
                      "rule_verdict": "attack" if pred else "benign",
                      "matched": hits})
    report = {"wgm_measured": {"n": len(sample), "accuracy": round(acc, 4),
                               "precision": round(prec, 4),
                               "recall": round(rec, 4),
                               "tp": tp, "fp": fp, "tn": tn, "fn": fn},
              "manual_sample": audit,
              "note": ("规则版（§1.14 降级）；wgm 为 prompt 级人标实测；"
                       "manual_sample 供人工抽检核池切分质量")}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return report


def _validate_m1_row(row: dict, src: str) -> dict:
    """多轮行级硬校验（转换器即质检器；v0 validate_row 为单轮专用，此处
    扩展：system 政策引用 / user-assistant 交替 / 末轮 assistant VERDICT
    闭环 / policy 字段与 pack 一致）。"""
    msgs = row.get("messages")
    assert isinstance(msgs, list) and len(msgs) >= 3 and len(msgs) % 2 == 1, (
        f"{src}: 消息数 {None if msgs is None else len(msgs)} 非 system+偶轮")
    assert msgs[0]["role"] == "system", f"{src}: 首消息非 system"
    assert "pack:" in msgs[0]["content"] and "@0.1" in msgs[0]["content"], (
        f"{src}: system 区缺政策引用")
    for i, m in enumerate(msgs[1:], 1):
        want = "user" if i % 2 == 1 else "assistant"
        assert m["role"] == want, f"{src}: 第 {i} 轮角色 {m['role']}≠{want}"
        assert isinstance(m["content"], str) and m["content"].strip(), (
            f"{src}: 第 {i} 轮空内容")
    tail = msgs[-1]["content"]
    assert "VERDICT: " in tail, f"{src}: 末轮 assistant 缺 VERDICT"
    v = json.loads(tail.rsplit("VERDICT: ", 1)[1])
    assert v.get("policy") == row["pack"], f"{src}: policy≠pack"
    return {"id": row["id"], "task": row["task"], "pack": row["pack"],
            "lang": row["lang"], "messages": msgs}


def register_lf(train_path: Path, dataset_info: Path) -> str:
    """LF 注册接口（--register-lf 显式触发；默认不注册——校准跑后再定）。
    注册条目与 convert_sft_v0.REGISTRATION 同形（sharegpt + tags 重映射，
    SharegptDatasetConverter 契约：messages[0]=system、奇偶交替、末条
    assistant 为训练目标）。"""
    rows = [_validate_m1_row(json.loads(l), f"m1:{i}")
            for i, l in enumerate(train_path.read_text(
                encoding="utf-8").splitlines()) if l.strip()]
    lf_dir = dataset_info.parent
    lf_path = lf_dir / "sft_m1.jsonl"
    with open(lf_path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    info = json.loads(dataset_info.read_text(encoding="utf-8"))
    info["sec_sft_m1"] = {"file_name": "sft_m1.jsonl",
                          "formatting": "sharegpt",
                          "columns": {"messages": "messages"},
                          "tags": {"role_tag": "role",
                                   "content_tag": "content",
                                   "user_tag": "user",
                                   "assistant_tag": "assistant",
                                   "system_tag": "system"}}
    dataset_info.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    return f"registered sec_sft_m1 ({len(rows)} rows) -> {lf_path}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="M2 SFT 数据组装（16 源 → m1）")
    ap.add_argument("--raw", default=str(RAW))
    ap.add_argument("--v0-dir", default=str(V0_DIR))
    ap.add_argument("--v0x-dir", default=str(V0X_DIR))
    ap.add_argument("--excl", default=str(EXCL_JSON))
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--dpo-out", default=str(DPO_DIR))
    ap.add_argument("--audit-pool-split", type=int, default=0,
                    help="生成池切分抽检报告（条数，0=不生成）")
    ap.add_argument("--register-lf", action="store_true",
                    help="转换 LF 格式并注册 sec_sft_m1（默认关）")
    args = ap.parse_args(argv)
    meta = assemble(raw=Path(args.raw), v0_dir=Path(args.v0_dir),
                    v0x_dir=Path(args.v0x_dir),
                    excl_path=Path(args.excl), out_dir=Path(args.out),
                    dpo_dir=Path(args.dpo_out))
    print(f"train: {meta['n_train']} / converted {meta['n_converted']} "
          f"/ post-dedup {meta['n_after_dedup']}")
    for row, st in meta["rows"].items():
        print(f"  {row:<20} {st['picked']:>6}/{st['quota']}")
    print(f"langs: {meta['langs']}  packs: {meta['packs']}")
    print(f"actions: {meta['actions']}  OR:attack = "
          f"{meta['or_to_attack_ratio']}")
    if args.audit_pool_split:
        rep = audit_pool_split(n=args.audit_pool_split)
        print(f"pool-split audit -> {AUDIT_JSON} "
              f"(wgm acc={rep['wgm_measured']['accuracy']}, "
              f"recall={rep['wgm_measured']['recall']})")
    if args.register_lf:
        print(register_lf(Path(args.out) / "train.jsonl",
                          ROOT / "data" / "lf" / "dataset_info.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
