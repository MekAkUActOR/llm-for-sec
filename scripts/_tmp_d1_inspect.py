import json
d = json.load(open(r'J:\Projects\llm_for_sec\reports\d1-prefill-probe-r9.json', encoding='utf-8'))
print('hit strict/loose:', d['hit_rate_strict'], d['hit_rate_loose'])
print('prompt_rebuild_mismatches:', d['prompt_rebuild_mismatches'])
print('finish_reason_hist:', d['finish_reason_hist'])
print('elapsed_s:', d['elapsed_s'])
ns = [x['new_tokens'] for x in d['items']]
ns.sort()
print('new_tokens: min', ns[0], 'p25', ns[len(ns)//4], 'median', ns[len(ns)//2], 'p75', ns[3*len(ns)//4], 'max', ns[-1])
print('mean:', round(sum(ns)/len(ns), 1))
print()
for x in d['items'][:3]:
    print('=' * 30, x['dialogue_id'], 'fin=', x['finish_reason'], 'ntok=', x['new_tokens'])
    print(repr(x['text'][:600]))
