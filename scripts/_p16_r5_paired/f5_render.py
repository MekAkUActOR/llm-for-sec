# f5_render.py — F5：render_pair() 把 (骨架变体, 主题) 渲染成一个偏好对 dict：共享 conversations（前缀轮+final_user），挂 benign/malicious 两个孪生偏好对。
import copy
import json

from content_f5_templates import TEMPLATES
from f5_combos import theme_phrases_for


def _fill(tpl, theme):
    """填充 body 占位（{deliver_core}/{refuse_reason}）并追加 VERDICT 行。"""
    body = tpl["body"].replace("{deliver_core}", "针对该" + theme["zh"] + "请求的具体处理")
    body = body.replace("{refuse_reason}", "该请求包含风险意图")
    return body + "\nVERDICT: " + json.dumps(tpl["verdict"], ensure_ascii=False)


def _gpt(value):
    """包装一条 gpt 轮。"""
    return {"from": "gpt", "value": value}


def render_pair(skel_var, theme, rng, idx, ben_idx=None, mal_idx=None):
    """→ 一个偏好对 dict：{id, conversations_benign, conversations_malicious, benign_pair, malicious_pair}。

    ★最小对结构（父代理修订 v4）：良性/恶意孪生 = 各自 conversations（前缀逐字节相同，
    仅末轮载荷不同：benign 池 vs malicious 池），偏好方向 2×2 镜像。
    ben_idx/mal_idx：指定载荷索引（无放回抽样保唯一）；None = rng 随机。"""
    theme_txt = theme["zh"] if skel_var["lang"] == "zh" else theme["en"]
    prefix = copy.deepcopy(skel_var["prefix"])
    for t in prefix:
        t["value"] = t["value"].replace("{theme}", theme_txt)
    fu_tmpl = skel_var["final_user"].replace("{theme}", theme_txt)
    ben_pool, mal_pool = theme_phrases_for(theme, skel_var["lang"])
    assert ben_pool and mal_pool, f"theme {theme.get('id')} lang {skel_var['lang']} 无可用载荷"
    ben = ben_pool[ben_idx] if ben_idx is not None and ben_idx < len(ben_pool) else rng.choice(ben_pool)
    mal = mal_pool[mal_idx] if mal_idx is not None and mal_idx < len(mal_pool) else rng.choice(mal_pool)
    final_benign = fu_tmpl.replace("{payload}", ben)
    final_malicious = fu_tmpl.replace("{payload}", mal)
    pool = [t for t in TEMPLATES if t["lang"] == skel_var["lang"]]
    dels = [t for t in pool if t["quad"] == "T_del"]
    refs = [t for t in pool if t["quad"] == "T_ref"]
    assert dels and refs, f"lang {skel_var['lang']} 缺 T_del/T_ref 模板"
    deliver = _fill(rng.choice(dels), theme)
    refuse = _fill(rng.choice(refs), theme)
    if rng.random() < 0.75:
        benign_rejected = refuse
    else:
        benign_rejected = "这个请求我需要更多信息才能判断。\nVERDICT: " + json.dumps({"verdict": "deflect"}, ensure_ascii=False)
    return {
        "id": f"p16-F5-{idx:06d}",
        "conversations_benign": [*copy.deepcopy(prefix), {"from": "human", "value": final_benign}],
        "conversations_malicious": [*copy.deepcopy(prefix), {"from": "human", "value": final_malicious}],
        "benign_pair": {"chosen": _gpt(deliver), "rejected": _gpt(benign_rejected)},
        "malicious_pair": {"chosen": _gpt(refuse), "rejected": _gpt(deliver)},
    }
