import json
a = [json.loads(l) for l in open(r'J:\Projects\llm_for_sec\reports\jb-resp-m5a-dpo-r9-v0.7-full.jsonl', encoding='utf-8') if l.strip()]
b = [json.loads(l) for l in open(r'J:\Projects\llm_for_sec\reports\jb-resp-m5a-dpo-r9-notmpl-v0.7-full.jsonl', encoding='utf-8') if l.strip()]
print('items:', len(a), 'vs', len(b))
def resp_text(x):
    # 提取生成文本（字段名自适应）
    for k in ('response', 'gen', 'output', 'assistant'):
        if k in x:
            return x[k]
    return json.dumps(x, ensure_ascii=False)[:100]
same = 0
diff = 0
for xa, xb in zip(a, b):
    if resp_text(xa) == resp_text(xb):
        same += 1
    else:
        diff += 1
print('response-identical:', same, '/ response-different:', diff)
# 抽样展示一个差异（若有）
if diff:
    for xa, xb in zip(a, b):
        if resp_text(xa) != resp_text(xb):
            print('--- think-version ---'); print(repr(resp_text(xa)[:200]))
            print('--- notmpl ---'); print(repr(resp_text(xb)[:200]))
            break
else:
    print('ALL RESPONSES BYTE-IDENTICAL -> generation-level null confirmed')
