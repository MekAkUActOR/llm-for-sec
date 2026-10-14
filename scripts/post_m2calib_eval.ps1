# M2 校准跑评估链（heldout v0.2.1 × 判分器 v2 行为读数 + 通用探针回升检查）：
#   1. 等待训练结束（m2-calib 自己的 train_results.json——勿用 trainer_log 判据）
#   2. 探针版本选择：data/probes/v0.3 存在（含 jsonl）则用之，否则回退 v0.1.1
#   3. heldout v0.2.1 复评 + 判分器 v2：reports\scored-m2calib-v2.json
#      + tool_output 子集单列读数（8 条）：SFT 语料 injection_pairs 只覆盖
#        5 载体（email/webpage/log/text/code），tool_output 为留出族永不入
#        训练（docs/06 §7）——这 8 条 = 未见载体泛化探针（预期：校准跑
#        ASR=1.0，M2 全量跑后观察翻转）
#      + 行为前后对照：与 M1.5 链产出的 scored-m15-v2.json / scored-c1full-v2.json
#        并排（基线为 v0.2 153 条对齐子集——v0.2.1 byte-prefix 保证共享条目
#        逐字一致，纵向可比；基线缺失不阻塞，仅提示）
#   4. 通用能力回升检查（防对话训练把通用域训塌，docs/06 §1 出口判据）：
#      general_en/zh PPL 回升 ≤10% 门禁 + sec 域不变差守护（compare_ppl
#      --sec-drop 0：sec 域对 m15 不得上升，副域仅观察）
# 运行（m2calib 训练启动后任意时刻挂起即可）：powershell scripts\post_m2calib_eval.ps1
$ErrorActionPreference = 'Continue'
$py = 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe'
$m2c = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m2-calib'
$m15 = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m15'
$base = 'J:\Projects\llm_for_sec\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd'
$env:HF_HOME = 'J:\Projects\llm_for_sec\.cache\huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'J:\Projects\llm_for_sec'

# --- 1. 等待训练完成（m2-calib 自己的 train_results.json）---
$done = Join-Path $m2c 'train_results.json'
Write-Host "[post-m2calib] waiting for m2-calib training to finish..."
while (-not (Test-Path $done)) {
    Start-Sleep -Seconds 300
}
Start-Sleep -Seconds 120  # 等最终文件落盘
Write-Host "[post-m2calib] training done, starting evals"

# --- 2. 探针版本选择（v0.3 优先，回退 v0.1.1；与 M1.5 链同规则）---
if ((Test-Path 'data\probes\v0.3') -and (Get-ChildItem 'data\probes\v0.3\*.jsonl' -ErrorAction SilentlyContinue)) {
    $probeDir = 'data\probes\v0.3'; $probeVer = 'v0.3'
} else {
    $probeDir = 'data\probes\v0.1.1'; $probeVer = 'v0.1.1'
}
Write-Host "[post-m2calib] probe version: $probeVer"

# checkpoint 可能缺 tokenizer（save_only_model）→ 指向底座快照兜底
$tokArgs = @()
if (-not (Test-Path (Join-Path $m2c 'tokenizer_config.json'))) {
    $tokArgs = @('--tokenizer', $base)
}

# --- 3. heldout v0.2.1 × 判分器 v2（校准跑行为主读数）---
# v0.2.1 = v0.2 byte-prefix 超集（161 = 153 对齐 + 8 tool_output）；
# c1-full/m15 基线读数（M1.5 链产出）覆盖 153 对齐子集，纵向可比不受影响
& $py scripts\baseline_eval.py --model $m2c @tokArgs --heldout data\heldout\v0.2.1 --out reports\heldout-m2calib.json --dump-responses reports\resp-m2calib.jsonl 2>&1
& $py scripts\score_heldout_v2.py --heldout data\heldout\v0.2.1 --responses reports\resp-m2calib.jsonl --out reports\scored-m2calib-v2.json 2>&1

# tool_output 子集单列（未见载体泛化读数）：按内容特征过滤（自描述，不依赖
# 行位不变量）；responses 覆盖全部 id，按 id 匹配子集即可
# ⚠ PS 5.1 的 Set-Content -Encoding UTF8 恒写 BOM → scorer 炸 invalid JSON
# （2026-09-28 实测教训）——必须用 .NET 无 BOM 写入
$sub = 'reports\heldout-tooloutput-subset'
New-Item -ItemType Directory -Force -Path $sub | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
foreach ($f in @('security', 'ai_safety')) {
    $lines = Get-Content "data\heldout\v0.2.1\$f.jsonl" -Encoding UTF8 |
        Select-String 'tool_output' | ForEach-Object { $_.Line }
    [System.IO.File]::WriteAllLines("J:\Projects\llm_for_sec\reports\heldout-tooloutput-subset\$f.jsonl", $lines, $utf8NoBom)
}
& $py scripts\score_heldout_v2.py --heldout $sub --responses reports\resp-m2calib.jsonl --out reports\scored-m2calib-tooloutput-v2.json 2>&1

# 行为前后对照（c1-full / m15 基线来自 M1.5 链；缺失不阻塞）
# 报表行用 ASCII（PS 5.1 对无 BOM 文件按 ANSI 读，中文串会被吞引号——教训留档）
$compareLines = @()
$compareLines += "M2-calib behavior comparison (scorer v2; heldout sets noted per row)"
$compareLines += "reading: label migration m15 -> m2calib (comply/format_error -> refuse/report_finding), ASR x over-refusal dual metrics"
$compareLines += "tool_output row = UNSEEN carrier generalization probe (held-out family, never in SFT; expect ASR=1.0 at calibration run, watch for flip at full M2)"
$sides = @(
    @{ name = 'c1-full';  path = 'reports\scored-c1full-v2.json';       note = 'v0.2 (153 aligned subset)' },
    @{ name = 'm15';      path = 'reports\scored-m15-v2.json';          note = 'v0.2 (153 aligned subset)' },
    @{ name = 'm2-calib'; path = 'reports\scored-m2calib-v2.json';      note = 'v0.2.1 (161)' },
    @{ name = 'm2-tolio'; path = 'reports\scored-m2calib-tooloutput-v2.json'; note = 'v0.2.1 tool_output x8 (unseen carrier)' }
)
foreach ($s in $sides) {
    if (Test-Path $s.path) {
        $j = Get-Content $s.path -Raw -Encoding UTF8 | ConvertFrom-Json
        $ld = $j.label_distribution
        $compareLines += ("{0,-9} asr={1:N3} forward={2:N3} ORR={3:N3} fmt_err={4:N3} | report={5} refuse={6} comply={7} deflect={8} fmt={9} (n_responded={10}) [{11}]" -f `
            $s.name, $j.metrics.asr, $j.metrics.asr_forward, $j.metrics.over_refusal_rate, $j.metrics.format_error_rate, `
            $ld.report_finding, $ld.refuse, $ld.comply, $ld.deflect, $ld.format_error, $j.n_responded, $s.note)
    } else {
        $compareLines += ("{0,-9} [missing baseline: {1} -- run scripts\post_m15_eval.ps1 first]" -f $s.name, $s.path)
    }
}
$compareLines | Tee-Object -FilePath reports\m2calib-behavior-compare.txt

# --- 4. 通用能力回升检查（general_en/zh ≤10% 门禁 + sec 不变差守护）---
# m15 侧同版本 PPL：M1.5 链已产出则复用，缺则现算
$m15Ppl = "reports\ppl-m15-$probeVer.json"
if (-not (Test-Path $m15Ppl)) {
    $m15Tok = @()
    if (-not (Test-Path (Join-Path $m15 'tokenizer_config.json'))) {
        $m15Tok = @('--tokenizer', $base)
    }
    & $py scripts\probe_ppl.py --model $m15 @m15Tok --name "m15-$probeVer" --probes $probeDir --out $m15Ppl 2>&1
}
& $py scripts\probe_ppl.py --model $m2c @tokArgs --name "m2calib-$probeVer" --probes $probeDir --out reports\ppl-m2calib-$probeVer.json 2>&1
# --sec-drop 0：sec 域对 m15 不得上升（守护预训练成果）；general 门禁 10% 为内置默认
& $py scripts\compare_ppl.py $m15Ppl reports\ppl-m2calib-$probeVer.json --sec-drop 0 2>&1 | Tee-Object -FilePath reports\ppl-compare-m15-m2calib.txt
Write-Host "[post-m2calib] ALL DONE"
