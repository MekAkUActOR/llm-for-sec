# -*- coding: utf-8 -*-
"""临时分析脚本：v0.2.2 重测读数提取（纯读取）。

对每臂输出：ASR(rob64)+CI、ORR(ali510)+CI、must_refuse 拆分、分维 ORR/ASR、
契约（VERDICT 保留，robustness 口径 + 全量口径）、标签分布、截断率；
并与 v0.2.1 旧 scored/resp 逐 id 对齐，验证 161 条前缀的行为一致性（贪心确定性）。
"""
import json
import sys
from pathlib import Path


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(c - h, 4), round(c + h, 4)]


def dom_map(d):
    out = {}
    for p in sorted(Path(d).glob('*.jsonl')):
        for ln in p.read_text(encoding='utf-8-sig').splitlines():
            ln = ln.strip()
            if ln:
                r = json.loads(ln)
                out[str(r['id'])] = r.get('domain')
    return out


DM = dom_map('data/heldout/v0.2.2')
OLD_DM = dom_map('data/heldout/v0.2.1')

for tag in sys.argv[1:]:
    sp = Path('reports') / f'scored-chat-v022-{tag}-v2-mnt512.json'
    rp = Path('reports') / f'resp-chat-v022-{tag}-mnt512.jsonl'
    d = json.load(open(sp, encoding='utf-8'))
    resp = {}
    trunc = 0
    for ln in rp.read_text(encoding='utf-8').splitlines():
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        resp[r['id']] = r
        if r.get('finish_reason') == 'length':
            trunc += 1
    items = d['items']
    rob = [i for i in items if i.get('responded') and i.get('kind') == 'robustness']
    ali = [i for i in items if i.get('responded') and i.get('kind') == 'alignment']
    asr_k = sum(1 for i in rob if (i.get('derived') or {}).get('attack_success'))
    orr_k = sum(1 for i in ali if (i.get('derived') or {}).get('over_refusal'))

    # must_refuse 拆分（v0.2.2 heldout 行的 expected）
    mr = {}
    for p in sorted(Path('data/heldout/v0.2.2').glob('*.jsonl')):
        for ln in p.read_text(encoding='utf-8-sig').splitlines():
            ln = ln.strip()
            if ln:
                r = json.loads(ln)
                mr[r['id']] = (r.get('expected') or {}).get('must_refuse')
    ali_f = [i for i in ali if mr.get(i['id']) is False]
    ali_t = [i for i in ali if mr.get(i['id']) is True]
    orr_f = sum(1 for i in ali_f if (i.get('derived') or {}).get('over_refusal'))
    orr_t = sum(1 for i in ali_t if (i.get('derived') or {}).get('over_refusal'))

    print(f'===== {tag} (v0.2.2, chat, mnt512) =====')
    print(f'n={d["n"]} resp={d["n_responded"]} missing={d["n_missing"]}')
    print(f'ASR(rob)  {asr_k}/{len(rob)} = {asr_k/len(rob):.4f} CI95={wilson(asr_k, len(rob))}')
    print(f'ORR(ali)  {orr_k}/{len(ali)} = {orr_k/len(ali):.4f} CI95={wilson(orr_k, len(ali))}')
    print(f'  must_refuse=False: {orr_f}/{len(ali_f)}  |  must_refuse=True(conservative): {orr_t}/{len(ali_t)}')
    # 分维
    for label, sel, key in (('ORR', ali, 'over_refusal'), ('ASR', rob, 'attack_success')):
        agg = {}
        for i in sel:
            dom = DM.get(str(i['id']))
            c = agg.setdefault(dom, [0, 0])
            c[1] += 1
            if (i.get('derived') or {}).get(key):
                c[0] += 1
        parts = [f'{k}: {v[0]}/{v[1]} ({v[0]/v[1]:.4f})' for k, v in sorted(agg.items()) if k]
        print(f'  {label} by domain: ' + '  '.join(parts))
    # 契约
    rob_ids = {i['id'] for i in rob}
    verd_rob = sum(1 for i in rob if 'VERDICT' in (resp.get(i['id'], {}).get('text') or ''))
    verd_all = sum(1 for iid, r in resp.items() if 'VERDICT' in (r.get('text') or ''))
    print(f'contract: robustness {verd_rob}/{len(rob)}  |  all {verd_all}/{len(resp)}')
    print(f'truncation (finish_reason=length): {trunc}/{len(resp)}')
    print(f'labels: {json.dumps(d["label_distribution"], ensure_ascii=False)}')
    # 与 v0.2.1 旧行为一致性（161 条前缀逐 id 对齐）
    osp = Path('reports') / f'scored-chat-{tag}-v2-mnt512.json'
    orp = Path('reports') / f'resp-chat-{tag}-mnt512.jsonl'
    if osp.exists() and orp.exists():
        od = json.load(open(osp, encoding='utf-8'))
        old_resp = {}
        for ln in orp.read_text(encoding='utf-8').splitlines():
            ln = ln.strip()
            if ln:
                r = json.loads(ln)
                old_resp[r['id']] = r.get('text') or ''
        same_label = diff_label = same_text = 0
        for oi in od['items']:
            iid = oi['id']
            ni = next((x for x in items if x['id'] == iid), None)
            if ni is None or not ni.get('responded'):
                continue
            if ni['label'] == oi['label']:
                same_label += 1
            else:
                diff_label += 1
            if (resp.get(iid, {}).get('text') or '') == old_resp.get(iid, ''):
                same_text += 1
        print(f'consistency vs v0.2.1 (161 prefix ids): label same={same_label} diff={diff_label};'
              f' response text identical={same_text}')
