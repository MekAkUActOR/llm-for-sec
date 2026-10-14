# DPO M3 v2

新建 `dpo_m3_v2.jsonl`/`_q`（主选）22,842 行、`_strict` 19,521 行（消融），源未改。**父代理审计表有误**：只数 chosen 侧——bt330_refusal 的 1,913 行 rejected 侧也缺 VERDICT（63,527 侧）；只追加一行，余者逐字未动。

q 版只改一处：同立场对（3,321）两侧共用同一 VERDICT 行，去人造 −0.02 校准偏好（2,149 人造+1,172 计算差）。判据：cue → refuse/propose/insufficient-context/conditional/allow。覆盖 100%；reserve 25%（v2/q）、13.55%（strict）。

局限：①启发式误判 action。②strict 丢 refusal_quality 246/300。③policy 类 rejected 引 rejected_pack 属源设计。
