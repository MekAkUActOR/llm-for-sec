# 误报排除记录：`llamafactory-cli train` 出现在进程列表 ≠ 有并发训练

**时间**：2026-10-06 15:54。

## 现象（看起来像严重并发违规）

`Get-CimInstance Win32_Process` 显示：

```
python.exe "…\llamafactory-cli.exe" train C:\Users\howwh\AppData\Local\Temp\fam_ind_pdp4loa0\qwen3-06b-sec-m3-dpo_t9_phish.yaml
```

在"**GPU 作业必须严格串行**"的纪律下，看到 `train` 二字很容易误判为"有训练在跑"。

## 真相：这是 `eval_family_indistribution.py` 的**正常工作机制**

- **父进程 = `eval_family_indistribution.py --tags soup-a050,m3-dpo`**（链的第 6 步）。
- 该脚本为**每个族**（`t9_phish` / `t2_mechanism` / `doc_structure` …）生成一份**临时 yaml**
  （`%TEMP%\fam_ind_<rand>\<tag>_<family>.yaml`）并调 `llamafactory-cli train` 跑**族探针**。
- **pid 每次观察都在变**（23944/33600 → 34740/12424）⇒ 它正在**族之间迭代**，属正常推进。
- 显存占用正常（1.8–3.8 GB），`nvidia-smi --query-compute-apps` 未见异常驻留。

## ⇒ 结论

**不是并发违规**。链的第 6 步健康推进中 ✓

## 登记为判据（并入规则 19 的推论）

> **判断"是否有 GPU 作业在跑"时，不得只看命令行里有没有 `train` 二字**；
> 必须同时看**父进程**与**配置路径**：
> `%TEMP%\fam_ind_*\*.yaml` ⇒ 是本项目**族探针的内部调用**，不是独立训练任务。
>
> 同类易误判项：`baseline_eval` 会被 `eval_needlefix.ps1` 调起、
> `probe_longctx` 会被链调起——**判"并发"要按"顶层作业"而不是"进程名"**。

**★ 这与规则 19 的原始教训正好相反但同源**：
规则 19 是"**把 CPU 作业误判成 GPU 作业**"（`build_document_gate --overlap` 被守卫杀掉）；
本条是"**把子调用误判成独立作业**"。
**⇒ 判据都必须落在"顶层作业的归属"上，而不是某个进程的局部特征上。**
