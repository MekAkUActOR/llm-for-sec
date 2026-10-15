# f5_combos.py — F5：expand() 把 8 个骨架扩展成 24 个深度变体，combos(rng) 生成 1000 个风格均衡、语言匹配的 (骨架变体, 主题) 元组。
import copy

from content_f5_skeletons import SKELETONS
from content_f5_themes import THEMES
try:
    from content_f5_extra import EXTRA  # v7 载荷扩容补丁
except ImportError:
    EXTRA = {}
for _m in ("content_f5_extra2a", "content_f5_extra2b"):  # v8 第二轮扩容
    try:
        _mod = __import__(_m)
        for _k, _v in getattr(_mod, "EXTRA2A" if _m.endswith("a") else "EXTRA2B", {}).items():
            for _q in ("benign", "malicious"):
                EXTRA.setdefault(_k, {"benign": [], "malicious": []})[_q] += _v.get(_q, [])
    except ImportError:
        pass


def theme_phrases_for(theme, lang):
    """★父代理修订 v7：主题短语（含 EXTRA 扩容）按骨架 lang 过滤可用载荷（zh=含 CJK / en=不含）。"""
    def _cjk(s):
        return any("\u4e00" <= c <= "\u9fff" for c in s)
    ex = EXTRA.get(theme.get("id"), {})
    ben_all = list(theme["benign"]) + list(ex.get("benign", []))
    mal_all = list(theme["malicious"]) + list(ex.get("malicious", []))
    ben = [p for p in ben_all if _cjk(p) == (lang == "zh")]
    mal = [p for p in mal_all if _cjk(p) == (lang == "zh")]
    # ★r6 修订 v7：跨扩容层文本去重（EXTRA2/EXTRA3 层间偶有同句 → 索引唯一但 prompt 撞）；
    # 保序去重（枚举与渲染共用本函数 ⇒ 索引一致）。r5 冻结产物不受影响（已落盘 sha 锚定）。
    ben = list(dict.fromkeys(ben))
    mal = list(dict.fromkeys(mal))
    return ben, mal


def expand():
    """8 骨架 → 24 变体：depth=对话总轮数（含末 human）；★父代理修订 v10：截断保持角色交替合法
    —— depth2=[system,human] / depth3=[human,gpt,human] / depth4=[system,human,gpt,human]
    （v9 前的 prefix[:depth-1] 会产 [system,human,human] 连续双 human → LF 转换器弃 700 行）。"""
    variants = []
    for skel in SKELETONS:
        for depth in (2, 3, 4):
            var = copy.deepcopy(skel)
            var["depth"] = depth
            full = var["prefix"]
            if depth == 2:
                prefix = [t for t in full if t["from"] == "system"]  # [system]+末human=合法2轮
            elif depth == 3:
                prefix = [t for t in full if t["from"] in ("human", "gpt")]  # [human,gpt]+human=合法3轮
            else:
                prefix = list(full)  # [system,human,gpt]+human=4轮
            assert any("{theme}" in t["value"] for t in prefix), skel["id"]
            var["prefix"] = prefix
            variants.append(var)
    return variants


def _pair_space(pool, rng):
    """★父代理修订 v9：逐 (变体,主题) 双射配对（bi↔mi 置换），保证 (v,t,bi) 与 (v,t,mi) 两投影均唯一。"""
    space = []
    for v in pool:
        for t in THEMES:
            ben, mal = theme_phrases_for(t, v["lang"])
            n = min(len(ben), len(mal))
            if n:
                perm = list(range(len(mal)))
                rng.shuffle(perm)
                for k in range(n):
                    space.append((v, t, k, perm[k]))
    return space


def combos(rng):
    """→ 1000 个 (skel_var, theme, ben_idx, mal_idx) 元组：每风格 250（受限风格取满空间、缺口轮转补齐），投影唯一。"""
    variants = expand()
    styles = sorted({v["style"] for v in variants})
    per, extra = divmod(1000, len(styles))
    out = []
    spaces = {}
    for i, style in enumerate(styles):
        pool = [v for v in variants if v["style"] == style]
        spaces[style] = _pair_space(pool, rng)
        need = per + (i < extra)
        if len(spaces[style]) < need:  # v6：骨架缩编致风格-语言失衡 → 取满空间
            need = len(spaces[style])
        out += rng.sample(spaces[style], need)
    # 补齐缺口：全局轮转未用双射对
    used = {(v["id"], v["depth"], t["id"], bi, mi) for v, t, bi, mi in out}
    used_b = {(v["id"], v["depth"], t["id"], bi) for v, t, bi, mi in out}
    used_m = {(v["id"], v["depth"], t["id"], mi) for v, t, bi, mi in out}
    while len(out) < 1000:
        progressed = False
        for style in styles:
            for (v, t, bi, mi) in spaces[style]:
                key = (v["id"], v["depth"], t["id"], bi, mi)
                kb = (v["id"], v["depth"], t["id"], bi)
                km = (v["id"], v["depth"], t["id"], mi)
                if key not in used and kb not in used_b and km not in used_m:
                    used.add(key); used_b.add(kb); used_m.add(km)
                    out.append((v, t, bi, mi))
                    progressed = True
                    if len(out) == 1000:
                        break
            if len(out) == 1000:
                break
        if not progressed:
            raise AssertionError(f"组合空间不足: {len(out)}/1000")
    return out
