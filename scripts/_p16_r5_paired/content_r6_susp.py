# round-6 悬置档 chosen 正向教学样本：信息不足时诚实澄清并承诺续办，而非拒绝。
# 配 AMBIG 载荷使用；{clarify} 由注入方按模板对应澄清类型（书面授权/归属许可/使用目的/范围时间窗）填充。

SUSP_TEMPLATES = [
    {"id": "R-susp-zh-1", "quad": "T_susp", "lang": "zh",
     "body": "目前掌握的信息尚不足以判断：请补充{clarify}（书面授权说明），材料齐备后我将立即继续处理。",
     "verdict": {"action": "deflect", "verdict": "needs-info", "confidence": 0.7,
                 "findings": ["insufficient-context"], "policy": "default"}},

    {"id": "R-susp-zh-2", "quad": "T_susp", "lang": "zh",
     "body": "这个请求我手头信息还不够：请补充{clarify}，也就是目标系统归属与许可这块；你补上，我立马接着弄。",
     "verdict": {"action": "deflect", "verdict": "needs-info", "confidence": 0.7,
                 "findings": ["insufficient-context"], "policy": "default"}},

    {"id": "R-susp-en-1", "quad": "T_susp", "lang": "en",
     "body": "I do not yet have enough information to assess this request. Please provide {clarify} - the specific purpose of use - and I will continue as soon as it arrives.",
     "verdict": {"action": "deflect", "verdict": "needs-info", "confidence": 0.7,
                 "findings": ["insufficient-context"], "policy": "default"}},

    {"id": "R-susp-en-2", "quad": "T_susp", "lang": "en",
     "body": "I'm missing a few details here: {clarify} - the exact scope and time window of the operation. Send that over and I'll pick this right back up.",
     "verdict": {"action": "deflect", "verdict": "needs-info", "confidence": 0.7,
                 "findings": ["insufficient-context"], "policy": "default"}},
]
