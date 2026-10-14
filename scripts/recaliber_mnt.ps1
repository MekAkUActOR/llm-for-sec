# 部署预算口径重测（max_new_tokens 96→256）——**换仪器**，不动 96 的历史读数。
#
# ★动机（2026-10-06）：
#   `scripts/baseline_eval.py:73` 的 max_new_tokens 默认 96 是**评测脚本的 CLI 默认值**，
#   从来不是产品约束；而 S1 入训目标长度中位 697–1,035 字符（≈150–220 token）✗
#   ⇒ 所有历史门禁读数都在"96 token 截断"下取得，契约行（在末尾）会被切掉。
#   按 docs/01 规则 21/23：**改 max_new_tokens 不是"收紧/放宽"，而是"换仪器"**
#   ⇒ 必须用独立口径名重测，**不得覆盖** 96 的读数。
#
# 本脚本：等 GPU 空闲 ⇒ 对每个 tag 跑 eval_needlefix.ps1 -MaxNewTokens 256
#         ⇒ 用 --max-new-tokens 256 重出裁定（独立文件名）。
#
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\recaliber_mnt.ps1
[CmdletBinding()]
param(
  [int]$MaxNewTokens = 512,
  [string[]]$Tags = @('soup-a050', 'm3-dpo'),
  [int]$MaxWaitMin = 60
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$log = "$root\reports\logs\recaliber-mnt$MaxNewTokens.log"
New-Item -ItemType Directory -Force -Path "$root\reports\logs" | Out-Null

function Say([string]$m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -Path $log -Value $line -Encoding UTF8
}

$models = @{
  # ★2026-10-06：真实目录名**没有** `qwen3-06b-` 前缀（我原先凭记忆写错，
  #   导致路径不存在、HF 把它当 repo id 报 HFValidationError ✗）。
  #   ★教训：模型目录名必须实测（Get-ChildItem checkpoints），不得凭记忆推断。
  'soup-a050' = "$root\checkpoints\soup-needlefix-a050"
  'm3-dpo'    = "$root\checkpoints\qwen3-06b-sec-m3-dpo"
}

Say "口径重测启动：max_new_tokens=$MaxNewTokens  tags=$($Tags -join ',')"

# ★★★2026-10-06 第 17 轮新增：**互斥锁**（单实例保证）。
#   同一口径并发会**写同样的产物名** ⇒ 两份读数互相污染 ✗。
#   ★★起因更正：我曾把"2 个 python 匹配 baseline_eval"读成并发事故，
#     并据此**杀掉了一次健康跑批** —— 那是**误判** ✗。真因是
#     venv 的 `python.exe` 在 Windows 上是 **uv trampoline** ⇒
#     一次调用产生 2 个进程（~4MB 薄壳 + ~2GB worker），
#     外加 launcher 会调用子脚本 powershell ⇒ 一条健康链会命中 4–5 个进程 ✗。
#   ⇒ **判并发的正确判据是"重 worker 数（≥2 才是真并发）"与 GPU 占用，
#     不是模式串匹配数**（docs/01 §11.37 规则 38）。
#   ⇒ 本锁防的是**真会发生的**并发（例如两次手工发射），
#     而不是那种被我误判出来的"并发" ✓。
$lock = "$root\reports\logs\.recaliber-$MaxNewTokens.lock"
if (Test-Path $lock) {
  $old = (Get-Content $lock -Raw -ErrorAction SilentlyContinue).Trim()
  $alive = $false
  if ($old -match '^\d+$') {
    $alive = [bool](Get-Process -Id ([int]$old) -ErrorAction SilentlyContinue)
  }
  if ($alive) {
    Say "★★拒绝启动：已有 launcher 在跑（pid=$old，锁 $lock）"
    Say "   同一口径不得并发 —— 并发会写同样的产物名、污染两份读数。"
    Say "   如确认该 pid 已死，删除锁文件后重试。"
    exit 3
  }
  Say "发现**陈旧**锁（pid=$old 已不存在）⇒ 回收"
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
Set-Content -Path $lock -Value $PID -Encoding ASCII
Say "已取得互斥锁（pid=$PID）"

# ★并再退一步：即便锁正常，也要确认**此刻没有别的重 worker 在跑**。
#   ★按规则 38：判据是**重 worker 数**（工作集 >500MB），而不是匹配进程数 ——
#     否则会把自己链上的 trampoline/子脚本误计为"别的评测"，从而永远拒绝启动 ✗
$others = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.WorkingSetSize -gt 500MB -and $_.CommandLine -and
                 $_.CommandLine -match 'baseline_eval\.py|probe_longctx\.py' })
if ($others.Count -ge 1) {
  Say "★★拒绝启动：已有 $($others.Count) 个**重 worker** 在跑（pid=$($others.ProcessId -join ','))"
  Remove-Item $lock -Force -ErrorAction SilentlyContinue
  exit 4
}
Say "并发预检通过：当前无其它重 worker"

# ★★2026-10-06：**开跑前**先验证所有模型路径存在 —— 否则一个路径笔误
#   会在等完 GPU 之后才暴露（或以"跳过"的形式静默什么都不做）✗。
#   这条是在我实际踩坑后加的：`qwen3-06b-soup-needlefix-a050` 这个前缀是我凭记忆写的，
#   真实目录是 `soup-needlefix-a050`；不存在时 HF 会把它当 repo id 抛 HFValidationError。
$bad = @()
foreach ($t in $Tags) {
  $m = $models[$t]
  if (-not $m) { $bad += "$t（未登记模型路径）"; continue }
  if (-not (Test-Path $m)) { $bad += "$t -> $m（目录不存在）"; continue }
  if (-not (Test-Path "$m\config.json")) { $bad += "$t -> $m（缺 config.json，不是可用模型）" }
  if (-not (Test-Path "$m\model.safetensors")) { $bad += "$t -> $m（缺 model.safetensors）" }
}
if ($bad.Count) {
  Say "★路径预检失败，拒绝启动："
  $bad | ForEach-Object { Say "    $_" }
  Say "CALIBER-PRECHECK=FAIL paths=$($bad.Count)"
  exit 2
}
Say "CALIBER-PRECHECK=PASS（$($Tags.Count) 个模型路径均存在且含 config+safetensors）"

# ---- 等现有评测链退出（排除自身与祖先，规则 19）----
$myPid = $PID
$anc = New-Object System.Collections.Generic.HashSet[int]
$cur = $myPid
for ($i = 0; $i -lt 12; $i++) {
  [void]$anc.Add($cur)
  try { $p = Get-CimInstance Win32_Process -Filter "ProcessId=$cur" -ErrorAction Stop
        if (-not $p -or -not $p.ParentProcessId) { break }
        $cur = [int]$p.ParentProcessId } catch { break }
}
Say "等待现有评测链退出（自身+12 层祖先已排除，最长 $MaxWaitMin min）..."
$deadline = (Get-Date).AddMinutes($MaxWaitMin)
while ((Get-Date) -lt $deadline) {
  $busy = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { -not $anc.Contains([int]$_.ProcessId) -and $_.CommandLine -and
                   $_.CommandLine -match 'eval_|probe_|baseline_eval|score_heldout|pack_consistency' }
  if (-not $busy) { break }
  Start-Sleep -Seconds 20
}
Say "链进程已消失。"

# ---- 等 GPU 空闲 ----
Say "等 GPU 空闲（used < 2048 MiB）..."
$gdl = (Get-Date).AddMinutes(30)
while ((Get-Date) -lt $gdl) {
  $u = (& nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null | Select-Object -First 1)
  if ($u -and [int]$u -lt 2048) { Say "GPU 空闲（used=$u MiB）"; break }
  Start-Sleep -Seconds 20
}

foreach ($t in $Tags) {
  $m = $models[$t]
  if (-not (Test-Path $m)) { Say "★跳过 $t：模型目录不存在 $m"; continue }
  Say "===== eval_needlefix.ps1 -Tag $t -MaxNewTokens $MaxNewTokens（chat 口径）====="
  & powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_needlefix.ps1" `
      -Tag $t -Model $m -NeedlePromptFormat chat -MaxNewTokens $MaxNewTokens 2>&1 |
    ForEach-Object { $_ } | Select-Object -Last 4 | ForEach-Object { Say "  $_" }
  Say "----- $t rc=$LASTEXITCODE -----"
  Say "===== 重出裁定 $t（基线 soup-a050，口径 mnt$MaxNewTokens）====="
  & $py "$root\scripts\topup_verdict.py" --variant $t --baseline soup-a050 --family-base m15 `
      --needle-format chat --max-new-tokens $MaxNewTokens `
      --out "topup-verdict-$t-mnt$MaxNewTokens.json" 2>&1 |
    Where-Object { $_ -match 'MUST|SHOULD|决策|>>>' } | ForEach-Object { Say "  $_" }
}
Say "===== 口径重测结束 ====="
# ★第 17 轮：正常结束时释放互斥锁。若本进程被强杀，锁会残留，
#   但下次启动的**陈旧锁回收**逻辑（pid 已不存在即回收）会处理 ✓
Remove-Item $lock -Force -ErrorAction SilentlyContinue
Say "已释放互斥锁"
