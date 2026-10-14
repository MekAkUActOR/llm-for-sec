# -*- coding: utf-8 -*-
"""临时脚本：提取 v0.2.1 旧读数作对照基线（纯读取，不改任何产物）。"""
import json
from pathlib import Path


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return [round(c - h, 4), round(c + h, 4)]


for tag in ('soup-a050', 'm4-capfix-probe'):
    sp = Path('reports') / f'scored-chat-{tag}-v2-mnt512.json'
    rp = Path('reports') / f'resp-chat-{tag}-mnt512.jsonl'
    d = json.load(open(sp, encoding='utf-8'))
    items = d['items']
    rob = [i for i in items if i.get('responded') and i.get('kind') == 'robustness']
    ali = [i for i in items if i.get('responded') and i.get('kind') == 'alignment']
    asr_k = sum(1 for i in rob if (i.get('derived') or {}).get('attack_success'))
    orr_k = sum(1 for i in ali if (i.get('derived') or {}).get('over_refusal'))
    rob_ids = {i['id'] for i in rob}
    verd = tot = 0
    for ln in rp.read_text(encoding='utf-8').splitlines():
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        if r.get('id') in rob_ids:
            tot += 1
            if 'VERDICT' in (r.get('text') or ''):
                verd += 1
    print(f'{tag}: v0.2.1-old  n={d["n"]} resp={d["n_responded"]}')
    print(f'  ASR(rob)  {asr_k}/{len(rob)} = {asr_k/len(rob):.4f} CI95={wilson(asr_k, len(rob))}')
    print(f'  ORR(ali)  {orr_k}/{len(ali)} = {orr_k/len(ali):.4f} CI95={wilson(orr_k, len(ali))}')
    print(f'  contract(VERDICT in rob resp) {verd}/{tot}')
    print(f'  labels={d["label_distribution"]}')
    print(f'  metrics={json.dumps(d["metrics"], ensure_ascii=False)}')
