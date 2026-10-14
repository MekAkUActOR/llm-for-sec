#!/usr/bin/env python
"""fC_cvpku_release：cvalues/pku 剩余池释放（m2.5-staging 政策行族）。

背景：m1 组装（assemble_sft_m2.py）对 cv/pku 攻击侧设 SUBCAPS 行上限
（policy_pairs: cvalues 4800 / pku-saferlhf 3600 = 1600/1200 池行×三包），
池内大量攻击行未释放。本生成器按**相同转换逻辑**放开配额，采 ~7,600 行：
- cv/pku 池行 → is_attack（与 m1 同一 classifier-v1）→ 三包拒绝行；
  判定分布照抄 m1 T5-attack:cvalues / T5-attack:pku 现有行：
  100% refuse/refuse 0.95、cv=zh+表面改述、pku=en+裸 prompt；
- cv:pku 配比照抄 m1 SUBCAPS 4:3（4800:3600）。

排除纪律（m1 已采样行绝不重复）：
- 剔除哈希 reports/sft-exclusion-hashes.json 与 m1 逐字节同判
  （_dt_cv/_dt_pku + sha256，覆盖 eval split 防污染）；
- m1 全量 user md5 集合查重：cv 池行查**所有表面形式**（裸 query +
  SURFACE_WRAPPERS zh，覆盖 m1 cv 攻击包装行与 cv/pku 良性裸行），
  pku 池行查裸 prompt md5；命中即整基弃（含跨文件同文副本）；
- 本族内基 prompt 归一去重（harmless/helpful 同 prompt、pku 跨目录同文）；
- m2.5-staging 既有各族 user 一并查重（零同文）。

输出：data/sft/m2.5-staging/fC_cvpku_release.jsonl（5 键行：id/task/
pack/lang/messages——与 m1/train.jsonl 及 staging 各族同构）。
seed=20260928 确定性；全程 CPU。
"""
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import assemble_sft_m2 as m2  # noqa: E402  复用 m1 转换契约（不复制实现）
from gen_sft_v0 import verdict_line  # noqa: E402

SEED = 20260928
TARGET_ROWS = 7600                    # ±5% 断言
CV_PKU_RATIO = (4800, 3600)           # 照抄 m1 SUBCAPS 配比
PACKS = ("conservative", "default", "professional")
M1_TRAIN = ROOT / "data" / "sft" / "m1" / "train.jsonl"
STAGE_DIR = ROOT / "data" / "sft" / "m2.5-staging"
OUT = STAGE_DIR / "fC_cvpku_release.jsonl"

# zh 行中文下限保证：cvalues 池内短基底（如「如何偷车？」）经 surface 包装后
# 仍可能 CJK<10，不满足结构闸（zh 行 user 需 ≥10 CJK，用以捕获 lang 错标）。
# 统一在包装后补齐语气前缀（只改语气，不改请求抽象层级与攻击意图）。
CJK_PAD_PRE = "想请教一下，"
CJK_PAD_SUF = "，方便说说吗？"
_CJK = re.compile(r"[\u4e00-\u9fff]")


def zh_pad(text: str) -> str:
    """保证 zh 行 user 的 CJK ≥10（结构闸），只补语气不改语义。"""
    if len(_CJK.findall(text)) >= 10:
        return text
    text = CJK_PAD_PRE + text
    if len(_CJK.findall(text)) < 10:
        text = text.rstrip("。？！") + CJK_PAD_SUF
    return text


def md5(t: str) -> str:
    return hashlib.md5(t.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 现有语料指纹
def existing_user_md5s() -> set:
    """m1 全量 + staging 既有各族的所有 user turn md5（查重基准）。"""
    out = set()
    with open(M1_TRAIN, encoding="utf-8") as f:
        for line in f:
            for m in json.loads(line)["messages"]:
                if m["role"] == "user":
                    out.add(md5(m["content"]))
    for p in sorted(STAGE_DIR.glob("*.jsonl")):
        if p.name == OUT.name:
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                for m in json.loads(line)["messages"]:
                    if m["role"] == "user":
                        out.add(md5(m["content"]))
    return out


# ---------------------------------------------------------------- 池枚举
def cv_pool(excl: set) -> list:
    """cvalues 池（harmless_train + helpful_train，同 m1 枚举序）。"""
    rows = []
    for fname in ("harmless_train.json", "helpful_train.json"):
        data = json.loads(
            (m2.RAW / "cvalues" / fname).read_text(encoding="utf-8"))
        for i, r in enumerate(data):
            p = (r.get("prompt") or "").strip()
            if not p or m2._sha(m2._dt_cv(r)) in excl.get("cvalues", set()):
                continue
            rows.append((p, f"{fname[:4]}-{i:05d}"))
    return rows


def pku_pool(excl: set) -> list:
    """pku-saferlhf 池（data/*/train.jsonl，同 m1 枚举序）。"""
    rows = []
    for p_ in sorted((m2.RAW / "pku-saferlhf" / "data").rglob("train.jsonl")):
        for i, j in enumerate(m2._jsonl_rows(p_)):
            prompt = (j.get("prompt") or "").strip()
            if not prompt or m2._sha(m2._dt_pku(j)) in \
                    excl.get("pku-saferlhf", set()):
                continue
            rows.append((prompt, f"{p_.parent.name}-{i:05d}"))
    return rows


def classify(texts: list) -> list:
    """批量 is_attack（与 m2.is_attack 同一 classifier-v1；等价性抽检）。"""
    b = m2._load_clf()
    if b is None:
        return [m2.is_attack(t)[0] for t in texts]
    out = []
    for k in range(0, len(texts), 2000):
        X = b["vectorizer"].transform(texts[k:k + 2000])
        out.extend(bool(int(p)) for p in b["clf"].predict(X))
    return out


# ---------------------------------------------------------------- 主流程
def main() -> None:
    rng = random.Random(SEED)
    excl = m2.load_exclusions()
    existing = existing_user_md5s()
    n_existing = len(existing)

    # ---- 池 → 剔除哈希 → 基去重 + m1/staging 查重 → 攻击分类 ----
    stats = {}
    pools = {}
    for name, pool_fn, hit_fn in (
            ("cvalues", cv_pool,
             lambda p: [md5(w) for w in m2._surface_forms(p, "zh")]),
            ("pku-saferlhf", pku_pool, lambda p: [md5(p)])):
        rows = pool_fn(excl)
        seen_base, kept, m1_hit, base_dup = set(), [], 0, 0
        for p, tag in rows:
            base = m2._norm(p)
            if base in seen_base:
                base_dup += 1
                continue
            if any(h in existing for h in hit_fn(p)):
                seen_base.add(base)     # 同文副本一并封禁
                m1_hit += 1
                continue
            seen_base.add(base)
            kept.append((p, tag))
        atk = [r for r, a in zip(kept, classify([r[0] for r in kept])) if a]
        stats[name] = {"pool": len(rows), "m1_or_staging_hit": m1_hit,
                       "base_dup": base_dup, "unique_kept": len(kept),
                       "attack_available": len(atk)}
        pools[name] = atk
    # 批量分类与逐行 is_attack 等价性抽检（classifier 路径）
    for name in pools:
        sample = [p for p, _ in pools[name][:100:7]] or \
            [p for p, _ in pools[name][:5]]
        for t in sample:
            batched = classify([t])[0]
            assert batched == m2.is_attack(t)[0], f"分类器等价性失败: {t[:50]}"

    # ---- 配额：cv:pku = 4:3（照抄 m1 SUBCAPS），每池行出三包行 ----
    frac_cv = CV_PKU_RATIO[0] / sum(CV_PKU_RATIO)
    n_cv = round(TARGET_ROWS * frac_cv / 3)
    n_pku = round(TARGET_ROWS * (1 - frac_cv) / 3)
    take = {"cvalues": min(n_cv, len(pools["cvalues"])),
            "pku-saferlhf": min(n_pku, len(pools["pku-saferlhf"]))}
    stats["quota_pool_rows"] = {"cvalues": take["cvalues"],
                                "pku-saferlhf": take["pku-saferlhf"],
                                "deficit": {"cvalues": max(0, n_cv - take["cvalues"]),
                                            "pku-saferlhf": max(0, n_pku - take["pku-saferlhf"])}}

    # ---- 转换（逐行照抄 conv_cvalues/conv_pku 攻击分支）----
    items = []
    for p, tag in rng.sample(pools["cvalues"], take["cvalues"]):
        wrapped = zh_pad(rng.choice(m2._surface_forms(p, "zh")))
        for pack in PACKS:
            v = verdict_line("refuse", "refuse", 0.95, [], pack)
            items.append(m2._item(
                f"cv-rel-{pack[:3]}-{tag}", "T5-attack:cvalues", pack, "zh",
                [("user", wrapped),
                 ("assistant", m2.REFUSAL_REPLY[pack]["zh"] + "\n" + v)],
                row="policy_pairs", pool="attack", source="cvalues",
                surface_key=f"cvrel:{tag}", attack=True))
    for p, tag in rng.sample(pools["pku-saferlhf"], take["pku-saferlhf"]):
        for pack in PACKS:
            v = verdict_line("refuse", "refuse", 0.95, [], pack)
            items.append(m2._item(
                f"pku-rel-{pack[:3]}-{tag}", "T5-attack:pku", pack, "en",
                [("user", p),
                 ("assistant", m2.REFUSAL_REPLY[pack]["en"] + "\n" + v)],
                row="policy_pairs", pool="attack", source="pku-saferlhf",
                surface_key=f"pkurel:{tag}", attack=True))
    rng.shuffle(items)

    # ---- 写出（5 键行，同 m1/train.jsonl 构型）----
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps({"id": it["id"], "task": it["task"],
                                "pack": it["pack"], "lang": it["lang"],
                                "messages": it["messages"]},
                               ensure_ascii=False) + "\n")

    # ================================================================ 断言 ===
    rows = [json.loads(l) for l in open(OUT, encoding="utf-8")]
    n = len(rows)
    # ① 总量 ±5%
    assert 7220 <= n <= 7980, f"总量 {n} 超出 7600±5%"
    # ② 零重复：基（池行）唯一——三包行有意共享 user（同池行 × 三包
    #    条件化），故每个 user md5 恰出现 3 次（同 task、异 pack）；
    #    vs m1/staging 全量零同文；id 唯一
    users = [r["messages"][1]["content"] for r in rows]
    u_cnt = Counter(md5(u) for u in users)
    assert set(u_cnt.values()) == {3}, \
        f"user 非三包成组: {dict(Counter(u_cnt.values()))}"
    assert len(u_cnt) == n // 3, f"唯一基 {len(u_cnt)} ≠ n/3"
    grp = {}
    for r in rows:
        grp.setdefault(md5(r["messages"][1]["content"]), []).append(r)
    for g in grp.values():
        assert len({x["pack"] for x in g}) == 3 \
            and len({x["task"] for x in g}) == 1, "三包组内 task/pack 异常"
    uhash = set(u_cnt)
    assert not (uhash & existing), \
        f"与 m1/staging 同文 {len(uhash & existing)} 条"
    assert len({r["id"] for r in rows}) == n, "id 重复"
    # ③ 三包分布（每池行出三包 → 各包精确 1/3，分源相等）
    by_pack = Counter(r["pack"] for r in rows)
    for pk in PACKS:
        assert by_pack[pk] == n // 3, f"包 {pk}={by_pack[pk]} ≠ {n // 3}"
    for name, pre in (("cvalues", "cv-rel-"), ("pku-saferlhf", "pku-rel-")):
        c = Counter(r["pack"] for r in rows if r["id"].startswith(pre))
        assert len(c) == 3 and len(set(c.values())) == 1, f"{name} 三包不齐"
    # ④ VERDICT 结尾 100% + refuse 判定 + policy==pack + 回复重构一致
    actions = Counter()
    for r in rows:
        a = r["messages"][-1]
        assert a["role"] == "assistant" and "VERDICT: " in a["content"]
        v = json.loads(a["content"].rsplit("VERDICT: ", 1)[1])
        assert v["action"] == "refuse" and v["verdict"] == "refuse" \
            and v["confidence"] == 0.95 and v["policy"] == r["pack"], r["id"]
        assert a["content"] == m2.REFUSAL_REPLY[r["pack"]][r["lang"]] \
            + "\n" + verdict_line("refuse", "refuse", 0.95, [], r["pack"]), \
            r["id"]
        actions[v["action"]] += 1
    assert actions["refuse"] == n, "存在非 refuse 行"
    # ⑤ zh 为主（cv=zh / pku=en，照抄 m1；4:3 配比 → zh 多数）
    langs = Counter(r["lang"] for r in rows)
    assert langs["zh"] > langs["en"], f"zh {langs['zh']} 未过半于 en {langs['en']}"
    # ⑥ 结构闭环（system=POLICY_SYSTEM、user 首发、交替、末轮 assistant）
    for r in rows:
        ms = r["messages"]
        assert ms[0]["role"] == "system" \
            and ms[0]["content"] == m2.POLICY_SYSTEM[r["pack"]][
                "zh" if r["lang"] == "zh" else "en"], r["id"]
        for k, m in enumerate(ms[1:], 1):
            assert m["role"] == ("user" if k % 2 else "assistant"), r["id"]

    # ---- 报告 ----
    report = {"seed": SEED, "n_rows": n, "unique_bases": len(u_cnt),
              "by_task": dict(Counter(r["task"] for r in rows)),
              "by_pack": dict(by_pack), "by_lang": dict(langs),
              "actions": dict(actions),
              "existing_user_md5_pool": n_existing,
              "cv_pku_ratio": f"{CV_PKU_RATIO[0]}:{CV_PKU_RATIO[1]}",
              **stats}
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"OK -> {OUT}")


if __name__ == "__main__":
    main()
