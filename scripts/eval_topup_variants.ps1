# Evaluate the C-path top-up variants against the FROZEN acceptance criteria in
# reports/c-path-topup-preregistration.md:
#   MUST  : unseen-carrier gate (data\heldout\v0.3-gen, 70 robustness items, deploy
#           format, judge v2) must not be significantly worse than m2-calib's 4/70
#   SHOULD: trained-carrier ASR/ORR, needle, dual-track PPL, G5 sec hold
# Everything runs in DEPLOY prompt format (--prompt-format chat) per docs/01 §11.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\eval_topup_variants.ps1
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$base = "$root\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root
$logdir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$tokArgs = @('--tokenizer', $base)

$tags = @('m3base-topup-e1', 'm3base-topup-e2')
foreach ($tag in $tags) {
  $model = "$root\checkpoints\$tag"
  if (-not (Test-Path $model)) { Write-Host "[eval-topup] SKIP $tag (缺产物)"; continue }
  Write-Host "`n[eval-topup] ================= $tag ================="

  # 1) 在训载体（heldout v0.2.1）与未见载体门禁（v0.3-gen），部署格式
  foreach ($suite in @(@{h='data\heldout\v0.2.1'; s='chat-'; n='v021'},
                       @{h='data\heldout\v0.3-gen'; s='chat-gen-'; n='gen'})) {
    $h = Join-Path $root $suite.h
    & $py scripts\baseline_eval.py --model $model @tokArgs --heldout $h `
        --prompt-format chat --out "$root\reports\heldout-$($suite.s)$tag.json" `
        --dump-responses "$root\reports\resp-$($suite.s)$tag.jsonl" 2>&1 |
      Select-String -Pattern 'prompt-format|ASR=|report ->|Traceback' | ForEach-Object { $_.Line }
    if ($LASTEXITCODE -ne 0) { Write-Host "[eval-topup] baseline_eval FAIL ($tag/$($suite.n))"; continue }
    & $py scripts\score_heldout_v2.py --heldout $h `
        --responses "$root\reports\resp-$($suite.s)$tag.jsonl" `
        --out "$root\reports\scored-$($suite.s)$tag-v2.json" 2>&1 |
      Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  }

  # 2) 未见载体逐载体子集（image_metadata / av_metadata）
  foreach ($c in @('image_metadata', 'av_metadata')) {
    $sub = "$root\reports\heldout-gen-$c"
    New-Item -ItemType Directory -Force -Path $sub | Out-Null
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    foreach ($f in Get-ChildItem "$root\data\heldout\v0.3-gen\*.jsonl") {
      $lines = Get-Content $f.FullName -Encoding UTF8 | Select-String $c | ForEach-Object { $_.Line }
      if ($lines) { [System.IO.File]::WriteAllLines("$sub\$($f.Name)", $lines, $utf8NoBom) }
    }
    & $py scripts\score_heldout_v2.py --heldout $sub `
        --responses "$root\reports\resp-chat-gen-$tag.jsonl" `
        --out "$root\reports\scored-chat-gen-$tag-$c-v2.json" 2>&1 |
      Select-String -Pattern 'report ->' | ForEach-Object { $_.Line }
  }

  # 3) tool_output 同载体回归子集（从 v0.2.1 里挑出该载体）
  $subT = "$root\reports\heldout-tooloutput"
  New-Item -ItemType Directory -Force -Path $subT | Out-Null
  $utf8NoBom2 = New-Object System.Text.UTF8Encoding($false)
  foreach ($f in Get-ChildItem "$root\data\heldout\v0.2.1\*.jsonl") {
    $lines = Get-Content $f.FullName -Encoding UTF8 | Select-String 'tool_output' | ForEach-Object { $_.Line }
    if ($lines) { [System.IO.File]::WriteAllLines("$subT\$($f.Name)", $lines, $utf8NoBom2) }
  }
  & $py scripts\score_heldout_v2.py --heldout $subT `
      --responses "$root\reports\resp-chat-$tag.jsonl" `
      --out "$root\reports\scored-chat-$tag-tooloutput-v2.json" 2>&1 |
    Select-String -Pattern 'report ->' | ForEach-Object { $_.Line }

  # 4) PPL（v0.3 与 v0.4，双轨判据需要）与长上下文（64 次 needle）
  & $py scripts\probe_ppl.py --model $model --name "$tag-v0.3" --probes data\probes\v0.3 @tokArgs 2>&1 |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  & $py scripts\probe_ppl.py --model $model --name "$tag-v0.4" --probes data\probes\v0.4 @tokArgs 2>&1 |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  & $py scripts\probe_longctx.py --model $model --name $tag --lens 16384,32768 --n-docs 4 2>&1 |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  # 产物名对齐判定器预期（ppl-<tag>.json / longctx-<tag>.json）
  Copy-Item "$root\reports\ppl-$tag-v0.3.json" "$root\reports\ppl-$tag.json" -Force -ErrorAction SilentlyContinue

  # 5) 判定器 v2（起点 = m2-calib 同源上一档；家族入口 = m15）
  & $py scripts\m25_exit_verdict.py --tag $tag --suffix chat- `
      --ppl-prev m2calib --out-name "verdict-$tag" 2>&1 |
    Select-String -Pattern 'VERDICT=|failed=|G1 |G2 |G3 |G4 |G5 |asr_|over_refusal|Traceback' |
    ForEach-Object { $_.Line }
}
Write-Host "`n[eval-topup] ALL DONE"
