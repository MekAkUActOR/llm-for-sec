# M2 全量跑评估链（SFT 出口门禁读数——docs/06 §1）：
#   1. 等待训练结束（qwen3-06b-sec-m2-full 自己的 train_results.json）
#   2. heldout v0.2.1 × 判分器 v2：ASR × 误拒双指标 + tool_output 8 条
#      未见载体泛化读数（校准跑预期 ASR=1.0，本跑观察翻转）+ 四点行为对照
#      （c1-full / m15 / m2-calib / m2-full）
#   3. 通用能力门禁（general_en/zh vs m15 回升 ≤10% + sec 不变差 --sec-drop 0）
#   4. 长上下文守护：m2-full vs m15（SFT 不得损伤 M1.6 恢复成果；
#      m15 侧 longctx-m15.json 缺则现算）
# 运行（m2-full 训练启动后任意时刻挂起）：powershell scripts\post_m2_full_eval.ps1
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe'
$m2f = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m2-full'
$m2c = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m2-calib'
$m15 = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m15'
$base = 'J:\Projects\llm_for_sec\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd'
$env:HF_HOME = 'J:\Projects\llm_for_sec\.cache\huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'J:\Projects\llm_for_sec'

# --- 1. 等待训练完成 ---
$done = Join-Path $m2f 'train_results.json'
Write-Host "[post-m2full] waiting for m2-full training to finish..."
while (-not (Test-Path $done)) {
    Start-Sleep -Seconds 300
}
Start-Sleep -Seconds 120
Write-Host "[post-m2full] training done, starting evals"

# --- 2. 探针版本选择（v0.3 优先，回退 v0.1.1）---
if ((Test-Path 'data\probes\v0.3') -and (Get-ChildItem 'data\probes\v0.3\*.jsonl' -ErrorAction SilentlyContinue)) {
    $probeDir = 'data\probes\v0.3'; $probeVer = 'v0.3'
} else {
    $probeDir = 'data\probes\v0.1.1'; $probeVer = 'v0.1.1'
}
Write-Host "[post-m2full] probe version: $probeVer"

$tokArgs = @()
if (-not (Test-Path (Join-Path $m2f 'tokenizer_config.json'))) {
    $tokArgs = @('--tokenizer', $base)
}

# --- 3. heldout v0.2.1 × 判分器 v2 ---
& $py scripts\baseline_eval.py --model $m2f @tokArgs --heldout data\heldout\v0.2.1 --out reports\heldout-m2full.json --dump-responses reports\resp-m2full.jsonl 2>&1
& $py scripts\score_heldout_v2.py --heldout data\heldout\v0.2.1 --responses reports\resp-m2full.jsonl --out reports\scored-m2full-v2.json 2>&1

# tool_output 子集单列（未见载体泛化读数）
# ⚠ PS 5.1 的 Set-Content -Encoding UTF8 恒写 BOM → scorer 炸 invalid JSON
# （2026-09-28 实测教训）——必须用 .NET 无 BOM 写入
$sub = 'reports\heldout-tooloutput-subset'
New-Item -ItemType Directory -Force -Path $sub | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
foreach ($f in @('security', 'ai_safety')) {
    $lines = Get-Content "data\heldout\v0.2.1\$f.jsonl" -Encoding UTF8 |
        Select-String 'tool_output' | ForEach-Object { $_.Line }
    [System.IO.File]::WriteAllLines("$root\reports\heldout-tooloutput-subset\$f.jsonl", $lines, $utf8NoBom)
}
& $py scripts\score_heldout_v2.py --heldout $sub --responses reports\resp-m2full.jsonl --out reports\scored-m2full-tooloutput-v2.json 2>&1

# 四点行为对照（ASCII 报表行——PS 5.1 ANSI 读无 BOM 文件吞引号教训留档）
$compareLines = @()
$compareLines += "M2-full behavior comparison (scorer v2; heldout sets noted per row)"
$compareLines += "primary read: label migration to report/refuse across m2-calib -> m2-full; ASR x over-refusal dual metrics"
$compareLines += "tool_output row = UNSEEN carrier generalization probe (held-out family, never in SFT)"
$sides = @(
    @{ name = 'c1-full';  path = 'reports\scored-c1full-v2.json';           note = 'v0.2 (153 aligned subset)' },
    @{ name = 'm15';      path = 'reports\scored-m15-v2.json';              note = 'v0.2 (153 aligned subset)' },
    @{ name = 'm2-calib'; path = 'reports\scored-m2calib-v2.json';          note = 'v0.2.1 (161)' },
    @{ name = 'm2-full';  path = 'reports\scored-m2full-v2.json';           note = 'v0.2.1 (161)' },
    @{ name = 'm2-tolio'; path = 'reports\scored-m2full-tooloutput-v2.json'; note = 'v0.2.1 tool_output x8 (unseen carrier)' }
)
foreach ($s in $sides) {
    if (Test-Path $s.path) {
        $j = Get-Content $s.path -Raw -Encoding UTF8 | ConvertFrom-Json
        $ld = $j.label_distribution
        $compareLines += ("{0,-9} asr={1:N3} forward={2:N3} ORR={3:N3} fmt_err={4:N3} | report={5} refuse={6} comply={7} deflect={8} fmt={9} (n_responded={10}) [{11}]" -f `
            $s.name, $j.metrics.asr, $j.metrics.asr_forward, $j.metrics.over_refusal_rate, $j.metrics.format_error_rate, `
            $ld.report_finding, $ld.refuse, $ld.comply, $ld.deflect, $ld.format_error, $j.n_responded, $s.note)
    } else {
        $compareLines += ("{0,-9} [missing baseline: {1}]" -f $s.name, $s.path)
    }
}
$compareLines | Tee-Object -FilePath reports\m2full-behavior-compare.txt

# --- 4. 通用能力门禁（vs m15）+ 校准对照 ---
$m15Ppl = "reports\ppl-m15-$probeVer.json"
if (-not (Test-Path $m15Ppl)) {
    $m15Tok = @()
    if (-not (Test-Path (Join-Path $m15 'tokenizer_config.json'))) {
        $m15Tok = @('--tokenizer', $base)
    }
    & $py scripts\probe_ppl.py --model $m15 @m15Tok --name "m15-$probeVer" --probes $probeDir --out $m15Ppl 2>&1
}
& $py scripts\probe_ppl.py --model $m2f @tokArgs --name "m2full-$probeVer" --probes $probeDir --out reports\ppl-m2full-$probeVer.json 2>&1
& $py scripts\compare_ppl.py $m15Ppl "reports\ppl-m2full-$probeVer.json" --sec-drop 0 2>&1 | Tee-Object -FilePath reports\ppl-compare-m15-m2full.txt
if (Test-Path "reports\ppl-m2calib-$probeVer.json") {
    & $py scripts\compare_ppl.py "reports\ppl-m2calib-$probeVer.json" "reports\ppl-m2full-$probeVer.json" 2>&1 | Tee-Object -FilePath reports\ppl-compare-m2calib-m2full.txt
}

# --- 5. 长上下文守护（SFT 不得损伤 M1.6 恢复成果）---
if (-not (Test-Path 'reports\longctx-m15.json')) {
    & $py scripts\probe_longctx.py --model $m15 --name m15 2>&1
}
& $py scripts\probe_longctx.py --model $m2f --name m2full 2>&1
& $py scripts\probe_longctx.py --compare reports\longctx-m15.json reports\longctx-m2full.json 2>&1 | Tee-Object -FilePath reports\longctx-compare-m15-m2full.txt
Write-Host "[post-m2full] ALL DONE. Gates: general <=+10% vs m15; sec not worse; behavior migration; 32k hold."
