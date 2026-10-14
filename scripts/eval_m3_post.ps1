# M3 DPO 训练后的**行为学五门禁**评测链 + 裁定。
# 判据见 reports/m3-dpo-preregistration.md §4；起点基线是 soup-a050（不是 m2calib）。
#
# 顺序（决定性判据优先，docs/01 §11.6）：
#   1) v0.3-gen 258 条**部署格式 chat** → MUST-A 未见载体 ASR + MUST-B 契约保留率
#   2) needle 64 次（2 lens × 2 lang × 16/格）→ SHOULD-2
#   3) v0.2.1 在训载体 → MUST-C 误拒 ORR + SHOULD-1 在训载体 ASR
#   4) v0.4-toolout 回归子集（已按 docs/01 §10.3 降级为回归集）
#   5) v0.4 PPL 双轨（batch 1，单实例，显存 ~11 GB ⇒ 必须严格串行）
#   6) 三族在分布能力观测（防伪通过）
#   7) topup_verdict 裁定（baseline = soup-a050）
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\eval_m3_post.ps1
[CmdletBinding()]
param(
  [string]$Tag = 'm3-dpo',
  [string]$Model = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo',
  [string]$Baseline = 'soup-a050'
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
Set-Location $root

Write-Host "[m3-post] ===== 前置硬校验 ====="
if (-not (Test-Path $Model)) { Write-Host "[m3-post] ✗ 缺产物 $Model"; exit 2 }
if (-not (Test-Path "$Model\config.json")) { Write-Host "[m3-post] ✗ $Model 无 config.json（训练未落盘？）"; exit 2 }
# 严格串行：按**命令行**识别 GPU 作业（不是按可执行文件名）
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'llamafactory|probe_|baseline_eval|score_heldout|train ' }
if ($procs) {
  Write-Host "[m3-post] ✗ 仍有 GPU 作业进程，拒绝并发（docs/01 §11.7 规则 5）："
  $procs | ForEach-Object { Write-Host ("        " + $_.ProcessId) }
  exit 2
}
$used = [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '')
Write-Host "[m3-post] 显存 = $used MiB（要求 <2048；WDDM 桌面基线会漂移到 ~1.4 GB）"
if ($used -ge 2048) { Write-Host "[m3-post] ✗ 显存未清空，中止"; exit 2 }

# 0) ★基线的**部署格式**needle（必须先有，否则与 M3 的 chat 读数无法比较）
#    docs/01 §11 规则 1：门禁读数必须产自部署格式。needle 探针 2026-09-30 才支持 chat，
#    因此基线 soup-a050 的既有 needle 是 raw 口径，此处补一份 chat 口径（~4 min）。
Write-Host "`n[m3-post] ===== 0：基线 $Baseline 的部署格式 needle（口径一致性前提）====="
$bModel = switch ($Baseline) {
  'soup-a050' { "$root\checkpoints\soup-needlefix-a050" }
  'm2calib'   { "$root\checkpoints\qwen3-06b-sec-m2-calib" }   # 实测路径（m2-calib，带连字符）
  default     { "$root\checkpoints\$Baseline" }
}
if (-not (Test-Path "$root\reports\longctx-$Baseline-chat.json")) {
  if (Test-Path $bModel) {
    powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_needlefix.ps1" `
      -Tag $Baseline -Model $bModel -NeedlePromptFormat chat -DecisiveOnly 2>&1 |
      Select-String -Pattern 'needlefix-eval|report ->|Traceback' | ForEach-Object { $_.Line }
  } else {
    Write-Host "[m3-post] ✗ 缺基线权重 $bModel ⇒ 无法产出 chat 口径基线读数"
  }
} else { Write-Host "[m3-post] 已有基线 chat needle 报告，跳过" }
# ★★2026-09-30 晚修（规则 30 草案）：子脚本失败必须被看见。
#   事故回顾：本脚本用 $ErrorActionPreference='Continue' 且不检查子脚本退出码 ⇒
#   eval_needlefix.ps1 在 step 1 中止后，链条照样跑完 step 6/7 并写出裁定。
#   后果不是"链没跑"（易发现），而是"链跑完、还出了裁定，只是一半输入从未被测量"。
$script:skipped = @()
if (-not (Test-Path "$root\reports\longctx-$Baseline-chat.json")) {
  Write-Host "[m3-post] ★★ FAIL 基线 chat needle 未产出 ⇒ chat 口径的 needle 比较无参照"
  $script:skipped += "基线 chat needle（$Baseline）"
}

# 1–5) 复用已验证的评测链（它会自行跳过已有报告）；needle 用 **chat** 口径
Write-Host "`n[m3-post] ===== 1–5：行为学门禁（v0.3-gen / needle(chat) / v0.2.1 / toolout / PPL）====="
powershell -NoProfile -ExecutionPolicy Bypass -File "$root\scripts\eval_needlefix.ps1" `
  -Tag $Tag -Model $Model -NeedlePromptFormat chat 2>&1 |
  Tee-Object -FilePath "$root\reports\logs\m3-post-gates.log" |
  Select-String -Pattern 'needlefix-eval|report ->|Traceback' | ForEach-Object { $_.Line }
# ★★规则 30：子链返回非零 ⇒ 记录，且**收尾必须以非零码退出**并把未成功的步骤喊出来。
$rcGates = $LASTEXITCODE
if ($rcGates -ne 0) {
  Write-Host "[m3-post] ★★ FAIL 行为门禁子链返回 rc=$rcGates ⇒ 部分输入未被测量"
  $script:skipped += "行为门禁子链 rc=$rcGates"
}

# 6) 三族在分布能力观测（防伪通过项；baseline 与 variant 都要有）
Write-Host "`n[m3-post] ===== 6：三族在分布能力观测 ====="
& $py "$root\scripts\eval_family_indistribution.py" --tags "$Baseline,$Tag" 2>&1 |
  Select-String -Pattern 'fam-ind|eval_loss|报告' | ForEach-Object { $_.Line }

# 7) 裁定（主判据 + 5 项辅判据 + 防伪观测）
Write-Host "`n[m3-post] ===== 7：topup_verdict 裁定（baseline=$Baseline）====="
& $py "$root\scripts\topup_verdict.py" --variant $Tag --baseline $Baseline --family-base m15 `
  --needle-format chat 2>&1 |
  Tee-Object -FilePath "$root\reports\logs\m3-post-verdict.log" | Select-Object -Last 30

# ★★2026-09-30 晚修（规则 30）：**不得无条件宣告 ALL DONE**。
#   只要有步骤未成功，就必须以非零码退出并把清单喊出来——
#   "某步被跳过"必须比"链失败"更响亮，而不是更安静。
if ($script:skipped.Count -gt 0) {
  Write-Host "`n[m3-post] ★★★ 链**未完成**：以下步骤未成功（裁定可能不完整，须按缺测解读）"
  $script:skipped | ForEach-Object { Write-Host "        - $_" }
  Write-Host "[m3-post] 裁定报告：reports\topup-verdict-$Tag.json（★请先核对上面的缺测清单）"
  exit 3
}
Write-Host "`n[m3-post] ALL DONE（0 个未成功步骤）；裁定报告见 reports\topup-verdict-$Tag.json"
