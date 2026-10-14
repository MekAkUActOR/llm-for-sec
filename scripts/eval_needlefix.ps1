# needle 修复产物的验收评测链（判据见 reports/needlefix-preregistration.md §3）。
#
# 顺序按 docs/01 §11.6（决定性判据必须排在队列最前）：
#   MUST-3 未见载体 ASR（v0.3-gen 258 条，**部署格式 chat**）
#   MUST-2 契约保留率（同上产物里的 VERDICT 保留）
#   MUST-1 needle（64 次 = 2 lens × 2 lang × 16/格）
# 之后才是 SHOULD：在训载体 v0.2.1、v0.4-toolout 回归子集、v0.4 PPL、三族观测探针。
#
# GPU 严格串行：跑前必须确认无其它 GPU 作业（见 docs/01 §11.7）。
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\eval_needlefix.ps1
[CmdletBinding()]
param(
  [string]$Tag = 'm2calib-needlefix-e1',
  [string]$Model = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m2calib-needlefix-e1',
  [string]$NeedlePromptFormat = 'raw',
  # ★2026-10-06 新增：部署生成预算（token）。
  #   来历：`scripts/baseline_eval.py:73` 的 max_new_tokens 默认 96 是**评测脚本的 CLI 默认值**，
  #   从来不是产品约束；而 S1 入训目标长度中位 697–1,035 字符（≈150–220 token）✗
  #   ⇒ 96 会让约 68% 的响应被截断，契约行（在末尾）必然丢失。
  #   ⇒ 提高它是"换仪器"（docs/01 规则 21/23），**必须用独立口径名，不得覆盖 96 的读数**。
  #   ★2026-10-06 第 16 轮：默认值由 96 改为 **512（部署口径）**。
  #   token 实测：SFT 三族目标 p50=380/228/146、p90=469/292/221、max=576/309/276，
  #   DPO chosen max=987。覆盖 @96 = 0.0%/0.0%/35.0% ✗；@512 = 97.2%/100%/100% ✓。
  #   ⇒ **默认必须是正确口径**，否则"直接跑脚本"就会得到错口径读数
  #     —— 这正是本问题的历史成因。要复现 96 的旧读数请显式 -MaxNewTokens 96。
  #   （96 时产物名不带后缀，故 96 的历史读数仍可原样复现，零覆盖风险。）
  [int]$MaxNewTokens = 512,
  [switch]$DecisiveOnly
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$base = "$root\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
Set-Location $root
# ★口径后缀：96 时为空（保持历史产物名不变）；其它值编码进**每一个**产物名与日志名，
#   使不同口径的读数**永不互相覆盖**（docs/01 规则 2/21）。
$mnt = if ($MaxNewTokens -eq 96) { '' } else { "-mnt$MaxNewTokens" }
$logdir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
Write-Host "[needlefix-eval] 口径：max_new_tokens=$MaxNewTokens  产物后缀='$mnt'"

# ★★2026-09-30 晚修（docs/01 规则 30 草案）：本脚本原先**无条件 exit 0**——
#   即使 needle 因 ModuleNotFoundError 崩掉（reports/logs/nf-eval-needle-soup-a050-chat.log
#   有 traceback），第 80 行照样 `DECISIVE ONLY DONE; exit 0`。
#   后果：编排层无法通过退出码发现失败，"chat 口径 needle 从未成功"被静默吞掉数周。
#   现引入逐步成败追踪：**判据是"产物存在"，不只信退出码**（退出码会说谎，已实证）。
$script:stepFail = New-Object System.Collections.Generic.List[string]
function Note-Step([string]$name, [string]$artPath) {
  # 判据：**产物存在**（给定产物路径时）。这样"跳过"分支也天然正确——
  # 跳过的前提就是产物已在，故必过；而真跑崩了必然产物缺失。
  if ($artPath) {
    if (Test-Path $artPath) { Write-Host "[needlefix-eval] OK  $name"; return }
    $msg = "$name（产物缺失 $(Split-Path $artPath -Leaf)；rc=$LASTEXITCODE）"
    $script:stepFail.Add($msg); Write-Host "[needlefix-eval] ★FAIL $msg"; return
  }
  if ($LASTEXITCODE -eq 0) { Write-Host "[needlefix-eval] OK  $name（rc=0）" }
  else {
    $msg = "$name（rc=$LASTEXITCODE）"
    $script:stepFail.Add($msg); Write-Host "[needlefix-eval] ★FAIL $msg"
  }
}
function Stop-IfFailed([string]$label) {
  if ($script:stepFail.Count -eq 0) { return }
  Write-Host "`n[needlefix-eval] ★★ $label 未完成：以下步骤失败（编排层必须看到非零退出码）"
  $script:stepFail | ForEach-Object { Write-Host "        - $_" }
  exit 3
}

if (-not (Test-Path $Model)) { Write-Host "[needlefix-eval] 缺产物 $Model → 中止"; exit 2 }
$used = [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '')
# ★2026-09-30 晚修：原消息写"应 < 1024"而下一行实际判 > 3072，自相矛盾且误导排查
#   （我当时据此误以为显存是中止原因）。阈值 3072 按 WDDM 桌面基线（实测 ~1.4 GB）设定。
Write-Host "[needlefix-eval] 显存占用 = $used MiB（WDDM 桌面基线 ~1.4 GB；阈值 3072）"
if ($used -gt 3072) { Write-Host "[needlefix-eval] 显存未清空 → 中止（GPU 严格串行）"; exit 2 }
# ★★2026-09-30 晚修（严重，docs/01 §11.18 规则 19）：原实现是**按进程名**判定——
#   "只要有任何 python.exe 就中止"。这会把**纯 CPU 作业**（如 build_document_gate.py --overlap）
#   误判为 GPU 作业 ⇒ 2026-09-30 晚 **M3 后的整条评测链在第 1 步被误杀**，
#   而 eval_m3_post.ps1 因 $ErrorActionPreference='Continue' 会继续往下跑，
#   导致 step 1-5（全部行为门禁）被整段跳过、step 7 在无产物的情况下出 PENDING 裁定。
#   现改为**按命令行**识别真正的 GPU 作业，与 wait_then_post_m3 / post_m3_safety_net /
#   run_needlefix / eval_m3_post 一致（本项目其余脚本早已如此，唯独本文件未回填）。
$gpuPat = 'llamafactory|probe_|baseline_eval|score_heldout|pack_consistency|eval_family_indistribution'
$other = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -and $_.CommandLine -match $gpuPat })
if ($other.Count -gt 0) {
  Write-Host "[needlefix-eval] 检测到 $($other.Count) 个在跑 GPU 作业 → 中止（GPU 严格串行）"
  $other | ForEach-Object { Write-Host "   pid=$($_.ProcessId)  $($_.CommandLine)" }
  exit 2
}

# ---- 决定性 1+2：v0.3-gen（未见载体 + 契约保留率），必须部署格式 chat
$gen = "$root\data\heldout\v0.3-gen"
if (-not (Test-Path "$root\reports\scored-chat-gen-$Tag-v2$mnt.json")) {
  Write-Host "`n[needlefix-eval] ★MUST-3/2 v0.3-gen 部署格式（$Tag，max_new_tokens=$MaxNewTokens）"
  & $py scripts\baseline_eval.py --model $Model --heldout $gen --prompt-format chat `
      --max-new-tokens $MaxNewTokens `
      --out "$root\reports\heldout-chat-gen-$Tag$mnt.json" `
      --dump-responses "$root\reports\resp-chat-gen-$Tag$mnt.jsonl" 2>&1 |
    Tee-Object -FilePath "$logdir\nf-eval-gen-$Tag$mnt.log" |
    Select-String -Pattern 'prompt-format|report ->|Traceback' | ForEach-Object { $_.Line }
  if ($LASTEXITCODE -eq 0) {
    & $py scripts\score_heldout_v2.py --heldout $gen `
        --responses "$root\reports\resp-chat-gen-$Tag$mnt.jsonl" `
        --out "$root\reports\scored-chat-gen-$Tag-v2$mnt.json" 2>&1 |
      Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  }
} else { Write-Host "[needlefix-eval] 已有 v0.3-gen 读数（$mnt），跳过" }
Note-Step 'MUST-3/2 v0.3-gen(chat)' "$root\reports\scored-chat-gen-$Tag-v2$mnt.json"

# ---- 决定性 3：needle（64 次）
# 报告名随口径变化：chat ⇒ longctx-<Tag>-chat.json（与 topup_verdict --needle-format chat 一致）
$nfName = if ($NeedlePromptFormat -eq 'chat') { "$Tag-chat" } else { $Tag }
if (-not (Test-Path "$root\reports\longctx-$nfName.json")) {
  Write-Host "`n[needlefix-eval] ★MUST-1 needle 64 次（$Tag）口径=$NeedlePromptFormat"
  & $py scripts\probe_longctx.py --model $Model --name $nfName `
      --lens 16384,32768 --n-docs 4 --prompt-format $NeedlePromptFormat 2>&1 |
    Tee-Object -FilePath "$logdir\nf-eval-needle-$nfName.log" |
    Select-String -Pattern 'report ->|Traceback|success' | ForEach-Object { $_.Line }
} else { Write-Host "[needlefix-eval] 已有 needle 报告（$nfName），跳过" }
Note-Step "MUST-1 needle($NeedlePromptFormat)" "$root\reports\longctx-$nfName.json"

if ($DecisiveOnly) {
  # ★原先此处**无条件 exit 0**，即使 needle 崩了也报成功（2026-09-30 事故的静默层）。
  Stop-IfFailed 'DECISIVE ONLY'
  Write-Host "`n[needlefix-eval] DECISIVE ONLY DONE"; exit 0
}

# ---- SHOULD 1：在训载体 v0.2.1 部署格式（ASR/ORR/分轴）
$h021 = "$root\data\heldout\v0.2.1"
if (-not (Test-Path "$root\reports\scored-chat-$Tag-v2$mnt.json")) {
  Write-Host "`n[needlefix-eval] SHOULD v0.2.1 部署格式（$Tag，max_new_tokens=$MaxNewTokens）"
  & $py scripts\baseline_eval.py --model $Model --heldout $h021 --prompt-format chat `
      --max-new-tokens $MaxNewTokens `
      --out "$root\reports\heldout-chat-$Tag$mnt.json" `
      --dump-responses "$root\reports\resp-chat-$Tag$mnt.jsonl" 2>&1 |
    Tee-Object -FilePath "$logdir\nf-eval-h021-$Tag$mnt.log" |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  & $py scripts\score_heldout_v2.py --heldout $h021 `
      --responses "$root\reports\resp-chat-$Tag$mnt.jsonl" `
      --out "$root\reports\scored-chat-$Tag-v2$mnt.json" 2>&1 |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
} else { Write-Host "[needlefix-eval] 已有 v0.2.1 读数（$mnt），跳过" }
Note-Step 'SHOULD v0.2.1(chat)' "$root\reports\scored-chat-$Tag-v2$mnt.json"

# ---- SHOULD 2：v0.4-toolout 回归子集
$to = "$root\data\heldout\v0.4-toolout"
if (-not (Test-Path "$root\reports\scored-chat-to-$Tag-v2$mnt.json")) {
  Write-Host "`n[needlefix-eval] SHOULD v0.4-toolout 回归子集（$Tag，max_new_tokens=$MaxNewTokens）"
  & $py scripts\baseline_eval.py --model $Model --heldout $to --prompt-format chat `
      --max-new-tokens $MaxNewTokens `
      --out "$root\reports\heldout-to-$Tag$mnt.json" `
      --dump-responses "$root\reports\resp-chat-to-$Tag$mnt.jsonl" 2>&1 |
    Tee-Object -FilePath "$logdir\nf-eval-to-$Tag$mnt.log" |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
  & $py scripts\score_heldout_v2.py --heldout $to `
      --responses "$root\reports\resp-chat-to-$Tag$mnt.jsonl" `
      --out "$root\reports\scored-chat-to-$Tag-v2$mnt.json" 2>&1 |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
} else { Write-Host "[needlefix-eval] 已有 toolout 读数（$mnt），跳过" }
Note-Step 'v0.4-toolout(chat)' "$root\reports\scored-chat-to-$Tag-v2$mnt.json"

# ---- SHOULD 3：v0.4 PPL（修正口径，单实例；显存 ~11GB，必须无并发）
if (-not (Test-Path "$root\reports\ppl-$Tag-v0.4.json")) {
  Write-Host "`n[needlefix-eval] SHOULD v0.4 PPL（$Tag）"
  & $py scripts\probe_ppl.py --model $Model --name "$Tag-v0.4" `
      --probes data\probes\v0.4 --tokenizer $base --batch-size 1 2>&1 |
    Tee-Object -FilePath "$logdir\nf-eval-ppl-$Tag.log" |
    Select-String -Pattern 'report ->|Traceback' | ForEach-Object { $_.Line }
} else { Write-Host "[needlefix-eval] 已有 v0.4 PPL，跳过" }
Note-Step 'SHOULD v0.4 PPL' "$root\reports\ppl-$Tag-v0.4.json"

# ★2026-09-30 晚修：原先此处无条件 "ALL DONE"（即使上面每一步都崩了）。
#   现在只要有任何一步失败，就以非零码退出，让编排层能中止而不是继续写 PENDING 裁定。
Stop-IfFailed 'ALL'
Write-Host "`n[needlefix-eval] ALL DONE（$($script:stepFail.Count) 个失败步骤）"
