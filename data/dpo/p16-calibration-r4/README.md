# p16-calibration-r4（P1.6 四轮：F 对话式扩容）

- 配方：良性侧 = r3 良性件逐字节副本（2,736）；恶意侧 = 一轮恶意件逐字节副本（2,880）+ **F4-dialog 新生成 792**（四风格 ×198，轮深 2/3/4 = 240/280/272，id p16-F-002641…3432）。
- 合计 6,408（良 2,736 : 恶 3,672 = 42.7 : 57.3）；+ m4 基座 28,842 = 35,250。
- 新生成内容门禁：行级断言（p16cef_common.batch_check，fails=0）+ prompt 全局唯一 + G9 同款 8-gram 污染检查对 heldout 冻结件 + probes 全量（官方 gate_g9 代码路径，PASS）。
- 冻结纪律：一轮/二轮/三轮产物只读零覆写；本目录为 r4 新版本目录，manifest sha 为冻结锚。
- 权威：reports/p1.6-round4-design.md（§三 T1–T4 预注册）+ scripts/_p16_r4_dialog/progress.md。
