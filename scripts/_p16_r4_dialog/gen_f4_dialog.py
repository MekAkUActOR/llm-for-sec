# -*- coding: utf-8 -*-
"""F4-dialog 生成器（P1.6 四轮 F 对话式扩容，792 对，2 批 g01/g02，每批 396 ≤400）。

网格（reports/p1.6-round4-design.md §二/§四，预注册）：
- 4 风格 × 198（escalation/roleplay/fictional/puzzle）；每风格 en 119 / zh 79（60:40）、
  pack default 89 / professional 79 / conservative 30、form cd_conditional_transition 99 /
  lip_refuse_deliver 99——分层配额与一轮对话层同构，形态混合不变
- 新内容全部新写（content_f4_dialog.py）：新骨架 11–20（轮深 1/2/3 组前缀交换按 3:4:3）、
  新主题 ×10、施压句 ×3（en 溢出行 j≥100 附加）
- id 延续 F 族编号 p16-F-002641…p16-F-003432（与一轮 2640 行零重叠，机器断言）；
  archetype F-dlg-{short}-11…20；src_task p16:F:dialog-r4:{style}
- 行级断言 = p16cef_common.batch_check（冻结公共库 import 零改动：schema/VERDICT/H1 标记词/
  H4 长度平价/F4F6 红线/零武器化/token ≤970）+ prompt 全局唯一 + 配额闭合 + id 与
  一轮 release 件零重叠
- 确定性：SEED_R4 = 20261014（每风格独立子流 STYLES 索引偏移；manifest 登记可复算）
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys_path_fix = __import__("sys").path
sys_path_fix.insert(0, str(ROOT / "scripts" / "_p16_parts_cef"))

import p16cef_common as K  # noqa: E402  冻结公共库（只读 import；绝不调用 write_part/PARTS_DIR）
import content_f4_dialog as FD  # noqa: E402

PARTS_DIR = HERE / "parts"
SEED_R4 = 20261014

PER_STYLE = 198
LANG_Q = {s: {"en": 119, "zh": 79} for s in FD.STYLES}
PACK_Q = {"default": 89, "professional": 79, "conservative": 30}
FORM_Q = {"cd_conditional_transition": 99, "lip_refuse_deliver": 99}

CONF_CHOSEN = [0.92, 0.93]
CONF_CD = [0.85, 0.88]
CONF_LIP = [0.86, 0.88]

LO = 0.90  # H4 垫句触发线（rejected 全文 < 0.90 × chosen 全文）

PAD_ZH = ["另：其余结论不受影响。", "补充：本条不改变其它判断。", "备注：口径如有变化另行说明。"]
PAD_EN = ["Note: everything else stands.", "Also: this doesn't change the other conclusions.",
          "One more note: any new wording applies later."]

R1_IDS_SRC = [ROOT / "data" / "dpo" / "p16-calibration" / "p16_benign_release.jsonl",
              ROOT / "data" / "dpo" / "p16-calibration" / "p16_malicious_honest.jsonl"]


def load_r1_ids() -> set:
    ids = set()
    for p in R1_IDS_SRC:
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    ids.add(json.loads(line)["id"])
    return ids


def write_part(fname: str, rows: list) -> dict:
    """parts 落盘（本目录 parts/，不触碰冻结 _p16_parts_cef/parts ✗✓）。"""
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PARTS_DIR / fname
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path.write_text(data, encoding="utf-8", newline="\n")
    b = path.read_bytes()
    return {"file": str(path.relative_to(ROOT)), "rows": len(rows),
            "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}


def build_style(style, rng, id_start):
    langs = K.quota_list(LANG_Q[style], rng)
    packs = K.quota_list(PACK_Q, rng)
    forms = K.quota_list(FORM_Q, rng)
    rows = []
    lang_ctr = {"en": 0, "zh": 0}
    for i in range(PER_STYLE):
        lang, pack, form = langs[i], packs[i], forms[i]
        skels = FD.SKELS[style][lang]
        topics = FD.TOPICS_ZH if lang == "zh" else FD.TOPICS_EN
        press = FD.PRESS_ZH if lang == "zh" else FD.PRESS_EN
        j = lang_ctr[lang]
        lang_ctr[lang] += 1
        skel = skels[j % len(skels)]
        topic = topics[(j // len(skels)) % len(topics)]
        final_user = skel["final"].format(topic=topic)
        if j >= len(skels) * len(topics):  # en 溢出行（j=100..118）：施压句附加保证组合唯一
            final_user = final_user + ("" if lang == "zh" else " ") + press[(j // (len(skels) * len(topics))) % len(press)]
        alt = []
        for u, a in skel["prefix"]:
            alt.append(("human", u))
            alt.append(("assistant", a))
        alt.append(("human", final_user))
        conv = K.conv_multi(pack, alt)
        if lang == "zh":
            chosen = K.gpt(FD.chosen_zh(style, skel, topic), "refuse", "refuse",
                           CONF_CHOSEN[i % 2], [FD.FIND_CHOSEN_ZH], pack)
        else:
            chosen = K.gpt(FD.chosen_en(style, skel, topic), "refuse", "refuse",
                           CONF_CHOSEN[i % 2], [FD.FIND_CHOSEN_EN], pack)
        if form == "cd_conditional_transition":
            body = FD.cd_zh(style, skel, topic) if lang == "zh" else FD.cd_en(style, skel, topic)
            conf = CONF_CD[i % 2]
        else:
            body = FD.lip_zh(style, skel, topic) if lang == "zh" else FD.lip_en(style, skel, topic)
            conf = CONF_LIP[i % 2]
        find = [FD.FIND_CD_ZH if lang == "zh" else FD.FIND_CD_EN]
        rejected = K.gpt(body, "refuse", "refuse", conf, find, pack)
        pads = PAD_ZH if lang == "zh" else PAD_EN
        guard = 0
        while len(rejected["value"]) < LO * len(chosen["value"]) and guard < len(pads):
            body = body + ("" if lang == "zh" else " ") + pads[(i + guard) % len(pads)]
            rejected = K.gpt(body, "refuse", "refuse", conf, find, pack)
            guard += 1
        rid = f"p16-F-{id_start + i:06d}"
        rows.append(K.make_row(
            dpo_class="p16_malicious_honest", id=rid, pack=pack, lang=lang,
            polarity="malicious_refuse", rejected_form=form,
            archetype_id=f"F-dlg-{FD.STYLE_SHORT[style]}-{skel['id']}",
            conversations=conv, chosen=chosen, rejected=rejected,
            src_task=f"p16:F:dialog-r4:{style}",
        ))
    return rows


def prompt_key(row: dict) -> str:
    return "\n".join(c["value"] for c in row["conversations"])


def main():
    K.assert_packs()
    r1_ids = load_r1_ids()
    print(f"[preflight] round-1 registered ids loaded: {len(r1_ids)} (read-only)")
    part_defs = [("part-g01.jsonl", ["escalation", "roleplay"]),
                 ("part-g02.jsonl", ["fictional", "puzzle"])]
    id_start = 2641
    all_rows = []
    all_prompts = set()
    for fname, styles in part_defs:
        rows = []
        for style in styles:
            rng = random.Random(SEED_R4 + FD.STYLES.index(style))
            rows.extend(build_style(style, rng, id_start))
            id_start += PER_STYLE
        assert len(rows) == 396, (fname, len(rows))
        # ---- 批级 fail-closed 断言 ----
        summ = K.batch_check(rows, "F")
        # prompt 全局唯一（批内 + 跨批累计）
        for r in rows:
            pk = prompt_key(r)
            assert pk not in all_prompts, f"prompt collision: {r['id']}"
            all_prompts.add(pk)
        # id 与一轮零重叠
        for r in rows:
            assert r["id"] not in r1_ids, f"id collision with round-1: {r['id']}"
        # 配额闭合（逐风格）
        for style in styles:
            sub = [r for r in rows if r["src_task"].endswith(style)]
            assert len(sub) == PER_STYLE, (style, len(sub))
            assert Counter(r["lang"] for r in sub) == Counter({"en": 119, "zh": 79}), Counter(r["lang"] for r in sub)
            assert Counter(r["pack"] for r in sub) == Counter({"default": 89, "professional": 79, "conservative": 30})
            assert Counter(r["rejected_form"] for r in sub) == Counter({"cd_conditional_transition": 99, "lip_refuse_deliver": 99})
        # 原型计数（G11 口径 ≤48）
        arch = Counter(r["archetype_id"] for r in rows)
        assert max(arch.values()) <= 48, arch.most_common(3)
        dist = K.dist_summary(rows)
        dist["style"] = dict(sorted(Counter(r["src_task"].rsplit(":", 1)[-1] for r in rows).items()))
        turns = Counter(sum(1 for c in r["conversations"] if c["from"] == "human") for r in rows)
        dist["user_turns"] = dict(sorted(turns.items()))
        K.print_summary(f"F4/{fname}", summ, dist)
        if summ["fails"]:
            for f in summ["fails"][:30]:
                print("  FAIL:", f)
            raise SystemExit(1)
        meta = write_part(fname, rows)
        (PARTS_DIR / fname.replace(".jsonl", ".check.json")).write_text(
            json.dumps({"batch": fname, "family": "F-dialog-r4", "styles": styles, **meta,
                        "seed": SEED_R4, "check": {k: v for k, v in summ.items() if k != "fails"},
                        "fails": 0, "dist": dist, "archetype_max": max(arch.values())},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print("WROTE", json.dumps(meta, ensure_ascii=False))
        all_rows.extend(rows)
    # ---- 合计恒等式 ----
    assert len(all_rows) == 792 and len(all_prompts) == 792, (len(all_rows), len(all_prompts))
    ids = [r["id"] for r in all_rows]
    assert ids == sorted(ids) and len(set(ids)) == 792
    assert ids[0] == "p16-F-002641" and ids[-1] == "p16-F-003432"
    turn_all = Counter(sum(1 for c in r["conversations"] if c["from"] == "human") for r in all_rows)
    print(f"F4-DIALOG TOTAL rows=792 (expect 792); user_turns={dict(sorted(turn_all.items()))}; "
          f"F TOTAL (old 2640 + new 792) = 3432")


if __name__ == "__main__":
    main()
