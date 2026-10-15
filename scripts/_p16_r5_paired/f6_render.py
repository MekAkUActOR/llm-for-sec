# -*- coding: utf-8 -*-
"""f6_render.py — round-6 渲染器（父代理撰写）：r5 render_pair 复用 + 模糊对渲染。

- bm 对：render_pair() 从 f5_render 原样 import（最小对 2×2 镜像不变）
- amb 对：render_amb() —— 悬置 chosen 正样本（T_susp 模板 + {clarify} 填充），
  rejected = T_ref（误拒）或 T_del（盲从）；两行载荷不同（ai_ref / ai_del）
"""
from __future__ import annotations

import copy
import json

from content_f5_templates import TEMPLATES
from f6_combos import _amb_pool

try:
    from content_r6_susp import SUSP_TEMPLATES
except ImportError:
    SUSP_TEMPLATES = []

# 澄清类型填充语（与模板 {clarify} 占位配套；按模板 id 尾缀轮换）
_CLARIFY = {
    "1": "相关书面授权或委托说明",
    "2": "目标系统的归属与测试许可",
    "3": "该操作的具体使用目的",
    "4": "操作范围与时间窗",
}


def _susp_fill(tpl):
    """悬置正样本渲染：填 {clarify} + VERDICT 行（deflect 档）。"""
    suffix = tpl["id"].rsplit("-", 1)[-1]
    clarify = _CLARIFY.get(suffix, "相关授权与场景信息")
    body = tpl["body"].replace("{clarify}", clarify)
    return body + "\nVERDICT: " + json.dumps(tpl["verdict"], ensure_ascii=False)


def _fill_std(tpl, theme):
    """标准模板渲染（同 f5_render._fill 语义，独立实现避免私有依赖）。"""
    body = tpl["body"].replace("{deliver_core}", "针对该" + theme["zh"] + "请求的具体处理")
    body = body.replace("{refuse_reason}", "该请求包含风险意图")
    return body + "\nVERDICT: " + json.dumps(tpl["verdict"], ensure_ascii=False)


def render_amb(skel_var, theme, rng, idx, ai_ref, ai_del):
    """模糊对 → dict：两行（同前缀逐字节同，载荷 = 两个不同 ambiguous 短语）。

    行1（误拒教学）：payload=AMBIG[ai_ref]，chosen=T_susp（悬置正确），rejected=T_ref（误拒错误）
    行2（盲从教学）：payload=AMBIG[ai_del]，chosen=T_susp（悬置正确），rejected=T_del（盲从错误）
    """
    theme_txt = theme["zh"] if skel_var["lang"] == "zh" else theme["en"]
    prefix = copy.deepcopy(skel_var["prefix"])
    for t in prefix:
        t["value"] = t["value"].replace("{theme}", theme_txt)
    fu_tmpl = skel_var["final_user"].replace("{theme}", theme_txt)
    pool = _amb_pool(theme, skel_var["lang"])
    susp_pool = [t for t in SUSP_TEMPLATES if t["lang"] == skel_var["lang"]]
    tpl_pool = [t for t in TEMPLATES if t["lang"] == skel_var["lang"]]
    dels = [t for t in tpl_pool if t["quad"] == "T_del"]
    refs = [t for t in tpl_pool if t["quad"] == "T_ref"]
    assert susp_pool and dels and refs, f"lang {skel_var['lang']} 缺悬置/交付/拒绝模板"
    susp = _susp_fill(rng.choice(susp_pool))
    ref = _fill_std(rng.choice(refs), theme)
    dele = _fill_std(rng.choice(dels), theme)
    fu_ref = fu_tmpl.replace("{payload}", pool[ai_ref])
    fu_del = fu_tmpl.replace("{payload}", pool[ai_del])
    return {
        "id": f"p16-R6A-{idx:06d}",
        "conv_ref": [*copy.deepcopy(prefix), {"from": "human", "value": fu_ref}],
        "conv_del": [*copy.deepcopy(prefix), {"from": "human", "value": fu_del}],
        "chosen": {"from": "gpt", "value": susp},
        "rejected_ref": {"from": "gpt", "value": ref},
        "rejected_del": {"from": "gpt", "value": dele},
    }
