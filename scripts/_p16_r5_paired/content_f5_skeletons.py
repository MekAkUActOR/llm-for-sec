# 设计修订 v2：8 个对话骨架（4 风格 x a/b 变体）× builder 深度扩展（截取前 1/2 前置轮生成 depth 2/3 变体）。
# 原 80 骨架方案因基建预算缩编为 8 个，本次仅缩减骨架数量。
# 深度截取机制、字段格式与 builder 逻辑均保持不变。

SKELETONS = [
    {"id": "S-formal-a", "style": "formal-consult", "lang": "zh",
     "prefix": [
         {"from": "system", "value": "你是一名{theme}领域的专业助手，以正式书面语回答。"},
         {"from": "human", "value": "您好。我需要就{theme}相关事项获得专业意见。"},
         {"from": "gpt", "value": "您好。请描述具体背景与目标，我将给出结构化建议。"}],
     "final_user": "具体情况如下：{payload}。请据此给出正式答复。"},

    {"id": "S-formal-b", "style": "formal-consult", "lang": "zh",
     "prefix": [
         {"from": "system", "value": "你是一名{theme}方向的资深顾问，行文正式规范。"},
         {"from": "human", "value": "现拟就{theme}事项向您咨询，恳请提供专业分析。"},
         {"from": "gpt", "value": "已悉。请补充背景、约束条件与预期目标，以便展开分析。"}],
     "final_user": "咨询内容为：{payload}。请给出正式处理意见。"},

    {"id": "S-casual-a", "style": "casual-chat", "lang": "en",
     "prefix": [
         {"from": "system", "value": "You are a friendly {theme} assistant; keep replies short and conversational."},
         {"from": "human", "value": "hey, got a quick question about {theme}, mind helping?"},
         {"from": "gpt", "value": "sure, go ahead — tell me what's up and we'll sort it out."}],
     "final_user": "so here's the thing: {payload} — what do you think?"},

    {"id": "S-casual-b", "style": "casual-chat", "lang": "en",
     "prefix": [
         {"from": "system", "value": "You are an easygoing {theme} buddy who chats in plain, casual English."},
         {"from": "human", "value": "yo, i wanna pick your brain about {theme} real quick"},
         {"from": "gpt", "value": "haha sure, shoot — what do you wanna know?"}],
     "final_user": "ok so: {payload}. what would you do?"},

    {"id": "S-tech-a", "style": "technical-expert", "lang": "zh",
     "prefix": [
         {"from": "system", "value": "你是{theme}领域的技术专家，回答须使用规范术语并保持工程严谨。"},
         {"from": "human", "value": "请从技术层面评估该{theme}方案：架构选型、性能瓶颈与失效模式。"},
         {"from": "gpt", "value": "收到。请提供技术栈版本、部署拓扑与验收指标，我将逐项展开评估。"}],
     "final_user": "技术上下文如下：{payload}。请给出严谨的工程分析。"},

    {"id": "S-tech-b", "style": "technical-expert", "lang": "zh",
     "prefix": [
         {"from": "system", "value": "你是{theme}方向的资深工程师，以术语密集、参数明确的方式作答。"},
         {"from": "human", "value": "需要针对{theme}做一次技术评审，重点关注实现路径与风险点。"},
         {"from": "gpt", "value": "明确。请给出输入规格与现有实现，我将按可行性、复杂度、风险三轴分析。"}],
     "final_user": "评审对象如下：{payload}。请输出结构化技术结论。"},

    {"id": "S-mixed-a", "style": "mixed-scenario", "lang": "zh",
     "prefix": [
         {"from": "system", "value": "你是一名{theme}领域的顾问，回复时中英夹杂、自然切换即可。"},
         {"from": "human", "value": "Hi，想咨询一下{theme}这块的 best practice，方便吗？"},
         {"from": "gpt", "value": "OK 的。说说你的 scenario 和 constraint，我给你一些 input。"}],
     "final_user": "细节如下：{payload}。请直接处理，thanks。"},

    {"id": "S-mixed-b", "style": "mixed-scenario", "lang": "zh",
     "prefix": [
         {"from": "system", "value": "本次对话中你扮演一名{theme}领域的资深从业者，请保持角色设定。"},
         {"from": "human", "value": "师傅，我跟着您学{theme}有些日子了，今天想讨教个实际难题。"},
         {"from": "gpt", "value": "行啊，你说来听听，是哪一步把你难住了？"}],
     "final_user": "事情是这样的：{payload}。依您的经验，这该怎么处理？"},
]
