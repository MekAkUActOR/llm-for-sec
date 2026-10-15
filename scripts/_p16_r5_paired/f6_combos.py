# -*- coding: utf-8 -*-
"""f6_combos.py — round-6 扩容组合器（父代理撰写；r6-build-brief §二）。

复用 f5_combos 的 expand()/theme_phrases_for()，新增：
- EXTRA3A/EXTRA3B 载荷池合并（round-6 扩容）
- bm_combos(): 良恶最小对 2,400 对（v9 双射配对模式，每风格 600）
- amb_combos(): 模糊对 600 对（每风格 150；每对 (ai1, ai2) 两异载荷 → 悬置 vs 误拒/盲从双行）
修订登记：brief §二 v2 —— amb 对 = 1 对 2 行（两行各用不同 ambiguous 载荷保 prompt 唯一），
总 3,000 对 = 6,000 行不变。
"""
from __future__ import annotations

from content_f5_skeletons import SKELETONS  # noqa: F401  (re-export)
from content_f5_themes import THEMES
from f5_combos import expand, theme_phrases_for

try:
    from content_f5_extra import EXTRA
except ImportError:
    EXTRA = {}
for _m, _attr in (("content_f5_extra2a", "EXTRA2A"), ("content_f5_extra2b", "EXTRA2B"),
                  ("content_r6_extra3a", "EXTRA3A"), ("content_r6_extra3b", "EXTRA3B")):
    try:
        _mod = __import__(_m)
        for _k, _v in getattr(_mod, _attr, {}).items():
            for _q in ("benign", "malicious"):
                EXTRA.setdefault(_k, {"benign": [], "malicious": []})[_q] += _v.get(_q, [])
    except ImportError:
        pass

try:
    from content_r6_ambiguous import AMBIG  # {"T01": {"ambiguous": [3 条]}, ...}
except ImportError:
    AMBIG = {}

try:  # round-6 修订 v3：en 模糊载荷补充（casual-chat 骨架配套）
    from content_r6_ambigen import AMBIG_EN
    for _k, _v in AMBIG_EN.items():
        AMBIG.setdefault(_k, {"ambiguous": []})["ambiguous"] += _v.get("ambiguous", [])
except ImportError:
    pass

try:  # round-6 修订 v5：amb 载荷二轮（池≥4 → 每 (v,t) 2 对）
    from content_r6_ambig2 import AMBIG2
    for _k, _v in AMBIG2.items():
        AMBIG.setdefault(_k, {"ambiguous": []})["ambiguous"] += _v.get("ambiguous", [])
except ImportError:
    pass


def dedup_variants(variants):
    """★修订 v6b：a/b 骨架仅 system 轮相异；v10 深度截断后 depth-3 = [human,gpt]（无 system）
    ⇒ a/b 在 depth-3 同 prompt。深度感知键：d3 按非 system 前缀 + final_user 去重；
    d2/d4 全键保留（system 轮区分 a/b）。"""
    seen = set()
    out = []
    for v in variants:
        if v["depth"] == 3:
            key = (v["style"], v["depth"], v["lang"],
                   tuple((t["from"], t["value"]) for t in v["prefix"] if t["from"] != "system"),
                   v["final_user"])
        else:
            key = (v["style"], v["depth"], v["lang"],
                   tuple((t["from"], t["value"]) for t in v["prefix"]), v["final_user"])
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def _amb_pool(theme, lang):
    def _cjk(s):
        return any("\u4e00" <= c <= "\u9fff" for c in s)
    pool = [p for p in AMBIG.get(theme.get("id"), {}).get("ambiguous", []) if _cjk(p) == (lang == "zh")]
    return list(dict.fromkeys(pool))  # r6 修订 v7：同款文本去重


def _style_variants(variants):
    styles = sorted({v["style"] for v in variants})
    return styles, {s: [v for v in variants if v["style"] == s] for s in styles}


def bm_combos(rng, total=2400):
    """良恶最小对：每风格 600，逐 (v,t) 双射配对（投影唯一；变体先经 dedup_variants v6）。"""
    variants = dedup_variants(expand())
    styles, pools = _style_variants(variants)
    per, extra = divmod(total, len(styles))
    out = []
    for i, s in enumerate(styles):
        space = []
        for v in pools[s]:
            for t in THEMES:
                ben, mal = theme_phrases_for(t, v["lang"])
                n = min(len(ben), len(mal))
                if n:
                    perm = list(range(len(mal)))
                    rng.shuffle(perm)
                    for k in range(n):
                        space.append((v, t, k, perm[k]))
        need = per + (i < extra)
        if len(space) < need:
            need = len(space)
        out += rng.sample(space, need)
    used = {(v["id"], v["depth"], t["id"], bi, mi) for v, t, bi, mi in out}
    while len(out) < total:  # 缺口轮转（v6 模式）
        progressed = False
        for s in styles:
            for v in pools[s]:
                for t in THEMES:
                    ben, mal = theme_phrases_for(t, v["lang"])
                    n = min(len(ben), len(mal))
                    for k in range(n):
                        key = (v["id"], v["depth"], t["id"], k, k)
                        if key not in used:
                            used.add(key)
                            out.append((v, t, k, k))
                            progressed = True
                            if len(out) == total:
                                return out
        if not progressed:
            raise AssertionError(f"bm space insufficient: {len(out)}/{total}")
    return out


def amb_combos(rng, total=600):
    """模糊对：每风格 150；★修订 v4：逐 (v,t) 不相交配对（载荷 2i/2i+1 成对消耗，
    空间扩容 v5/v6：池≥4 → 每 (v,t) 2 对 + 变体内容去重 → 每风格 150 恰可达）。"""
    variants = dedup_variants(expand())
    styles, pools = _style_variants(variants)
    per, extra = divmod(total, len(styles))
    out = []
    for i, s in enumerate(styles):
        space = []
        for v in pools[s]:
            for t in THEMES:
                pool = _amb_pool(t, v["lang"])
                for j in range(0, len(pool) - 1, 2):
                    space.append((v, t, j, j + 1))
        need = per + (i < extra)
        if len(space) < need:
            raise AssertionError(f"amb space insufficient: style {s} {len(space)} < {need}")
        out += rng.sample(space, need)
    return out
