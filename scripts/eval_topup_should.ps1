# Remaining SHOULD-criteria measurements for the C-path top-up variants.
# The decisive criterion (unseen-carrier gate) is measured by eval_gen_gate_all.ps1;
# this script fills in the secondary axes: trained-carrier deploy-format suite,
# tool_output regression subset, needle (64 trials), and the three-family
# in-distribution probe (data/heldout/v0.5-topup-families) when it exists.
#
# Run AFTER eval_gen_gate_all.ps1 finishes (GPU work is strictly serial on this box;
# concurrent GPU work is known to cause 10x slowdowns here).
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\eval_topup_should.ps1
#   powershell ... -File scripts\eval_topup_should.ps1 -Tags m2calib     # 只跑指定臂
#
# ★2026-09-30 事故记录：本脚本的 PPL 步骤**单实例就要 ~11–12 GB 显存**
#  （实测两个实例把 24 GB 卡挤到 23.5 GB / 455 MiB 可用 → WDDM 分页抖动，
#   同口径 PPL 从正常的 ~107 s 劣化到 >20 min）。因此：
#   ① 同一时刻**只允许一个** probe_ppl 实例；② 跑前用 nvidia-smi 确认
#   memory.used < 1 GB；③ 若发现 memory.used 高而 nvidia-smi 无属主进程，
#   先确认是否有多个 python 实例，杀干净再看读数。
[CmdletBinding()]
param(
  [string[]]$Tags = @('m2calib', 'm3base-topup-e1', 'm3base-topup-e2')
)
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
$utf8 = New-Object System.Text.UTF8Encoding($false)
$h021 = "$root\data\heldout\v0.2.1"
$famDir = "$root\data\heldout\v0.5-topup-families"

$models = @(
  @{ tag = 'm2calib';         path = "$root\checkpoints\qwen3-06b-sec-m2-calib" },
  @{ tag = 'm3base-topup-e1'; path = "$root\checkpoints\qwen3-06b-sec-m3base-topup-e1" },
  @{ tag = 'm3base-topup-e2'; path = "$root\checkpoints\qwen3-06b-sec-m3base-topup-e2" }
)
foreach ($m in $models) {
  if ($Tags -notcontains $m.tag) { Write-Host "[should] 跳过（-Tags 未选）: $($m.tag)"; continue }
  if (-not (Test-Path $m.path)) { Write-Host "[should] SKIP $($m.tag)（缺产物）"; continue }
  Write-Host "`n[should] ================ $($m.tag) ================"
  $gpu = (nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', ''
  Write-Host "[should] 发射前显存占用 = $gpu MiB（应 < 1024）"

  # 1) 在训载体（heldout v0.2.1）部署格式：ASR / ORR / 分轴
  if (-not (Test-Path "$root\reports\resp-chat-$($m.tag).jsonl") -or
      -not (Test-Path "$root\reports\scored-chat-$($m.tag)-v2.json")) {
    & $py scripts\baseline_eval.py --model $m.path --heldout $h021 `
        --prompt-format chat --out "$root\reports\heldout-chat-$($m.tag).json" `
        --dump-responses "$root\reports\resp-chat-$($m.tag).jsonl" 2>&1 |
      Tee-Object -FilePath "$logdir\should-heldout-$($m.tag).log" |
      Select-String -Pattern 'prompt-format|report ->|Traceback' | ForEach-Object { $_.Line }
    if ($LASTEXITCODE -eq 0) {
      & $py scripts\score_heldout_v2.py --heldout $h021 `
          --responses "$root\reports\resp-chat-$($m.tag).jsonl" `
          --out "$root\reports\scored-chat-$($m.tag)-v2.json" 2>&1 |
        Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
    }
  } else { Write-Host "[should] 已有 v0.2.1 部署格式读数，跳过" }

  # 2) tool_output 同载体回归子集（v0.4-toolout，若存在）——只用鲁棒性条
  $to = "$root\data\heldout\v0.4-toolout"
  if (Test-Path $to) {
    if (-not (Test-Path "$root\reports\resp-chat-to-$($m.tag).jsonl")) {
      & $py scripts\baseline_eval.py --model $m.path --heldout $to `
          --prompt-format chat --out "$root\reports\heldout-to-$($m.tag).json" `
          --dump-responses "$root\reports\resp-chat-to-$($m.tag).jsonl" 2>&1 |
        Select-String -Pattern 'prompt-format|report ->|Traceback' | ForEach-Object { $_.Line }
      & $py scripts\score_heldout_v2.py --heldout $to `
          --responses "$root\reports\resp-chat-to-$($m.tag).jsonl" `
          --out "$root\reports\scored-chat-to-$($m.tag)-v2.json" 2>&1 |
        Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
    }
  } else { Write-Host "[should] v0.4-toolout 不存在，跳过回归子集" }

  # 3) needle（8 深度 × 2 变体 = 16 次/格，2 lens × 2 lang = 64）
  if (-not (Test-Path "$root\reports\longctx-$($m.tag).json")) {
    & $py scripts\probe_longctx.py --model $m.path --name $m.tag `
        --lens 16384,32768 --n-docs 4 @('--tokenizer', $base) 2>&1 |
      Tee-Object -FilePath "$logdir\should-needle-$($m.tag).log" |
      Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  } else { Write-Host "[should] 已有 needle 报告，跳过" }

  # 3b) PPL（v0.4 修正口径；m2calib/m2full 缺失会让判定器 G2 双轨回退到污染口径 v0.3）
  if (-not (Test-Path "$root\reports\ppl-$($m.tag)-v0.4.json")) {
    Write-Host "[should] v0.4 PPL（修正口径）: $($m.tag)"
    & $py scripts\probe_ppl.py --model $m.path --name "$($m.tag)-v0.4" `
        --probes data\probes\v0.4 --tokenizer $base 2>&1 |
      Tee-Object -FilePath "$logdir\should-ppl-$($m.tag).log" |
      Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  } else { Write-Host "[should] 已有 v0.4 PPL，跳过" }

  # 4) 三族在分布内观测探针（防伪通过）；未交付则明确记为未测
  if (Test-Path $famDir) {
    foreach ($f in Get-ChildItem "$famDir\*.jsonl") {
      $fam = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
      if (Test-Path "$root\reports\resp-chat-fam-$($m.tag)-$fam.jsonl") { continue }
      $sub = "$root\reports\heldout-fam-$fam"
      New-Item -ItemType Directory -Force -Path $sub | Out-Null
      Copy-Item $f.FullName "$sub\$($f.Name)" -Force
      & $py scripts\baseline_eval.py --model $m.path --heldout $sub `
          --prompt-format chat --out "$root\reports\heldout-fam-$($m.tag)-$fam.json" `
          --dump-responses "$root\reports\resp-chat-fam-$($m.tag)-$fam.jsonl" 2>&1 |
        Select-String -Pattern 'prompt-format|report ->|Traceback' | ForEach-Object { $_.Line }
      & $py scripts\score_heldout_v2.py --heldout $sub `
          --responses "$root\reports\resp-chat-fam-$($m.tag)-$fam.jsonl" `
          --out "$root\reports\scored-chat-fam-$($m.tag)-$fam-v2.json" 2>&1 |
        Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
    }
  } else { Write-Host "[should] v0.5-topup-families 未交付 → 观测项记为未测（决策将判 PENDING）" }
}
Write-Host "`n[should] ALL DONE"
