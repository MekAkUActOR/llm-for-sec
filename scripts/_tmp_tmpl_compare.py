from transformers import AutoTokenizer
import transformers
print('transformers version:', transformers.__version__)
msgs = [{"role": "user", "content": "hello"}]
ta = AutoTokenizer.from_pretrained(r'J:\Projects\llm_for_sec\checkpoints\qwen3-8b-sec-m5a-dpo-r9-merged')
tb = AutoTokenizer.from_pretrained(r'J:\Projects\llm_for_sec\checkpoints\qwen3-8b-sec-m5a-dpo-r9-merged-notmpl')
oa = ta.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
ob = tb.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
print('--- merged (think) ---')
print(repr(oa))
print('--- notmpl ---')
print(repr(ob))
print('IDENTICAL:', oa == ob)
