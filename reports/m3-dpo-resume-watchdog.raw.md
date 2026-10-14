

# RAW evidence block — 2026-10-06 14:21:45

## host time

*command* (14:21:45):
```powershell
Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
```

*output* (14:21:46):
```
2026-10-06 14:21:46.052
```

## GPU + the ONLY compute app (identification by command line, not exe name)

*command* (14:21:46):
```powershell
nvidia-smi --query-gpu=memory.used,memory.total,power.draw,utilization.gpu --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='llamafactory-cli.exe'" | Select-Object ProcessId,Name,CreationDate,CommandLine | Format-List
```

*output* (14:21:46):
```
17774 MiB, 24455 MiB, 250.97 W, 49 %
13404, [N/A]
14176, [N/A]
12948, [N/A]
15744, [N/A]
15708, [N/A]
24940, [N/A]
25688, [N/A]
24904, [N/A]
10648, [N/A]
35656, [N/A]
32660, [N/A]
35112, [N/A]
6972, [N/A]
32576, [N/A]
22216, [N/A]
15548, [N/A]
648, [N/A]
2424, [N/A]
9892, [N/A]
34648, [N/A]


ProcessId    : 24672
Name         : llamafactory-cli.exe
CreationDate : 2026/10/6 13:59:21
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\llamafactory-cli.exe" train J:\Projects\llm_for_sec\configs\m3-dp
               o-final.yaml

ProcessId    : 35220
Name         : python.exe
CreationDate : 2026/10/6 13:59:21
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "J:\Projects\llm_for_sec\.venv\Scripts\llamafactory-c
               li.exe" train J:\Projects\llm_for_sec\configs\m3-dpo-final.yaml

ProcessId    : 34648
Name         : python.exe
CreationDate : 2026/10/6 13:59:21
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "J:\Projects\llm_for_sec\.venv\Scripts\llamafactory-c
               li.exe" train J:\Projects\llm_for_sec\configs\m3-dpo-final.yaml

ProcessId    : 36668
Name         : python.exe
CreationDate : 2026/10/6 14:21:13
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" scripts/check_m25_staging.py

ProcessId    : 22168
Name         : python.exe
CreationDate : 2026/10/6 14:21:13
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" scripts/check_m25_staging.py

ProcessId    : 13572
Name         : python.exe
CreationDate : 2026/10/6 14:21:45
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" reports\m3-dpo-resume-watchdog-raw.py

ProcessId    : 3284
Name         : python.exe
CreationDate : 2026/10/6 14:21:45
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" reports\m3-dpo-resume-watchdog-raw.py
```

## host memory / commit / the training processes

*command* (14:21:46):
```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object @{n='free_phys_MiB';e={[int]($_.FreePhysicalMemory/1024)}},@{n='commit_used_MiB';e={[int](($_.TotalVirtualMemorySize-$_.FreeVirtualMemory)/1024)}},@{n='commit_limit_MiB';e={[int]($_.TotalVirtualMemorySize/1024)}} | Format-List
```

*output* (14:21:46):
```


free_phys_MiB    : 18324
commit_used_MiB  : 40089
commit_limit_MiB : 54415
```

## trainer_log.jsonl: size, mtime, first line, last line

*command* (14:21:46):
```powershell
Get-Item 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' | Select-Object Length,LastWriteTime | Format-List; Get-Content 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' -TotalCount 1; Get-Content 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' -Tail 1
```

*output* (14:21:46):
```


Length        : 29886
LastWriteTime : 2026/10/6 14:21:27



{"current_steps": 5, "total_steps": 1803, "loss": 0.6786192893981934, "accuracy": 0.32500001788139343, "lr": 1.3333333333333334e-07, "epoch": 0.0027737327508494556, "percentage": 0.28, "elapsed_time": "0:00:15", "remaining_time": "1:32:04"}
{"current_steps": 600, "total_steps": 1803, "loss": 0.13273359537124635, "accuracy": 0.949999988079071, "lr": 1.5640644378321233e-06, "epoch": 0.3328479301019347, "percentage": 33.28, "elapsed_time": "0:21:16", "remaining_time": "0:42:39"}
```

## checkpoint dirs (landing times are the file mtimes)

*command* (14:21:46):
```powershell
Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo' -Directory | Select-Object LastWriteTime,Name | Format-Table -AutoSize; Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo' | Select-Object Name,Length | Format-Table -AutoSize
```

*output* (14:21:46):
```

LastWriteTime      Name          
-------------      ----          
2026/10/6 13:36:35 checkpoint-200
2026/10/6 14:05:51 checkpoint-300
2026/10/6 14:11:04 checkpoint-400
2026/10/6 14:16:28 checkpoint-500
2026/10/6 14:21:28 checkpoint-600



Name              Length
----              ------
checkpoint-200          
checkpoint-300          
checkpoint-400          
checkpoint-500          
checkpoint-600          
README.md         2309  
trainer_log.jsonl 29886
```

## the two resume lines (the primary in-band evidence of a resume)

*command* (14:21:46):
```powershell
$logs='reports\logs\m3-dpo-resume-launch.log','reports\logs\m3-dpo-run.log'; foreach($l in $logs){ if(Test-Path $l){ Write-Host "--- $l"; Get-Content $l -Encoding Unicode | Select-String -Pattern 'Resuming training|Continuing training|global step' | Select-Object -First 6 | ForEach-Object { $_.Line } } }
```

*output* (14:21:47):
```
--- reports\logs\m3-dpo-resume-launch.log
[INFO|2026-10-06 13:59:27] llamafactory.hparams.parser:144 >> Resuming training from J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-200.
[INFO|trainer.py:1482] 2026-10-06 14:00:10,859 >>   Resuming training from checkpoint with epoch 0 and global step 200
--- reports\logs\m3-dpo-run.log
[INFO|2026-10-06 13:59:27] llamafactory.hparams.parser:144 >> Resuming training from J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-200.
[INFO|trainer.py:1482] 2026-10-06 14:00:10,859 >>   Resuming training from checkpoint with epoch 0 and global step 200
```

## the exception/error regex sweep over both logs (expect 0)

*command* (14:21:47):
```powershell
$logs='reports\logs\m3-dpo-resume-launch.log','reports\logs\m3-dpo-run.log'; foreach($p in 'Traceback','CUDA out of memory','RuntimeError','MemoryError','\bnan\b'){ $n=0; foreach($l in $logs){ if(Test-Path $l){ $n += (Get-Content $l -Encoding Unicode | Select-String -Pattern $p -AllMatches).Count } }; Write-Host ('{0,-22} {1}' -f $p,$n) }
```

*output* (14:21:47):
```
Traceback              0
CUDA out of memory     0
RuntimeError           0
MemoryError            0
\bnan\b                0
```

## stdout DPO-metric channel: how many reward dict lines per log + their step range

*command* (14:21:47):
```powershell
$logs='reports\logs\m3-dpo-launch.log','reports\logs\m3-dpo-run.log','reports\logs\m3-dpo-resume-launch.log'; foreach($l in $logs){ if(Test-Path $l){ $m = Get-Content $l -Encoding Unicode | Select-String -Pattern "^\{'loss':"; $first=($m | Select-Object -First 1).Line; $last=($m | Select-Object -Last 1).Line; Write-Host ('{0}: n={1}' -f $l,$m.Count); Write-Host ('   first: ' + $first.Substring(0,[Math]::Min(160,$first.Length))); Write-Host ('   last : ' + $last.Substring(0,[Math]::Min(160,$last.Length))) } }
```

*output* (14:21:47):
```
reports\logs\m3-dpo-launch.log: n=40
   first: {'loss': '0.6786', 'grad_norm': '166.2', 'learning_rate': '1.333e-07', 'rewards/chosen': '0.05243', 'rewards/rejected': '0.01676', 'rewards/accuracies': '0.325'
   last : {'loss': '0.04287', 'grad_norm': '37.76', 'learning_rate': '1.969e-06', 'rewards/chosen': '4.022', 'rewards/rejected': '-6.704', 'rewards/accuracies': '0.9625',
reports\logs\m3-dpo-run.log: n=80
   first: {'loss': '0.152', 'grad_norm': '67.6', 'learning_rate': '1.967e-06', 'rewards/chosen': '1.432', 'rewards/rejected': '-8.24', 'rewards/accuracies': '0.925', 'rew
   last : {'loss': '0.1327', 'grad_norm': '8.334', 'learning_rate': '1.564e-06', 'rewards/chosen': '-1.152', 'rewards/rejected': '-12.18', 'rewards/accuracies': '0.95', '
reports\logs\m3-dpo-resume-launch.log: n=80
   first: {'loss': '0.152', 'grad_norm': '67.6', 'learning_rate': '1.967e-06', 'rewards/chosen': '1.432', 'rewards/rejected': '-8.24', 'rewards/accuracies': '0.925', 'rew
   last : {'loss': '0.1327', 'grad_norm': '8.334', 'learning_rate': '1.564e-06', 'rewards/chosen': '-1.152', 'rewards/rejected': '-12.18', 'rewards/accuracies': '0.95', '
```

## trainer_state.json per checkpoint: global_step + how many rewards/* rows (cumulative)

*command* (14:21:47):
```powershell
Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-*' -Directory | ForEach-Object { $j=Get-Content (Join-Path $_.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; $rw=@($j.log_history | Where-Object { $_.'rewards/chosen' }); Write-Host ('{0}: global_step={1} n_log_history={2} rewards_rows={3} first={4} last={5}' -f $_.Name,$j.global_step,$j.log_history.Count,$rw.Count,$rw[0].step,$rw[-1].step) }
```

*output* (14:21:47):
```
checkpoint-200: global_step=200 n_log_history=40 rewards_rows=40 first=5 last=200
checkpoint-300: global_step=300 n_log_history=60 rewards_rows=60 first=5 last=300
checkpoint-400: global_step=400 n_log_history=80 rewards_rows=80 first=5 last=400
checkpoint-500: global_step=500 n_log_history=100 rewards_rows=100 first=5 last=500
checkpoint-600: global_step=600 n_log_history=120 rewards_rows=120 first=5 last=600
```

## last checkpoint's trainer_state.json max_steps + best_metric

*command* (14:21:47):
```powershell
$d=(Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-*' -Directory | Sort-Object {[int]($_.Name -replace '\D','')} | Select-Object -Last 1); $j=Get-Content (Join-Path $d.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; Write-Host ('dir={0} global_step={1} max_steps={2} epoch={3} best_metric={4}' -f $d.Name,$j.global_step,$j.max_steps,$j.epoch,$j.best_metric)
```

*output* (14:21:48):
```
dir=checkpoint-600 global_step=600 max_steps=1803 epoch=0.3328479301019347 best_metric=
```

## telemetry sampler: is it alive, and its head/tail

*command* (14:21:48):
```powershell
Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv' -TotalCount 2; Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv' -Tail 2; (Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv').Count
```

*output* (14:21:48):
```
ts,step,loss,acc,lr,epoch,elapsed,tl_mtime_ticks,tl_len,mem_used_mib,power_w,util_pct,temp_c,commit_used_mib,free_phys_mib,n_train_procs,ckpt_dirs
2026-10-06 14:05:45,295,0.042900994420051575,0.987500011920929,1.91236869355225E-06,0.16365023230011788,0:05:21,639268635328108778,15241,17734,275.31,45,57,38025,20647,2,checkpoint-100|checkpoint-200
2026-10-06 14:21:12,595,0.16089513301849365,0.9375,1.5714829396731E-06,0.33007419735108523,0:21:01,639268644723932846,29645,17774,263.84,49,59,38360,20494,2,checkpoint-100|checkpoint-200|checkpoint-300|checkpoint-400|checkpoint-500
2026-10-06 14:21:33,600,0.13273359537124635,0.949999988079071,1.56406443783212E-06,0.3328479301019347,0:21:16,639268644875901777,29886,17774,232.99,38,57,39968,17655,2,checkpoint-200|checkpoint-300|checkpoint-400|checkpoint-500|checkpoint-600
49
```

## analysis artifacts present (size + mtime)

*command* (14:21:48):
```powershell
Get-ChildItem 'reports\m3-dpo-resume-watchdog-*' | Sort-Object Name | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
```

*output* (14:21:48):
```

Name                                           Length LastWriteTime     
----                                           ------ -------------     
m3-dpo-resume-watchdog-A.json                   70560 2026/10/6 14:21:26
m3-dpo-resume-watchdog-A-resume-and-metrics.py  12221 2026/10/6 14:11:57
m3-dpo-resume-watchdog-B-data-identity.json      1007 2026/10/6 14:05:59
m3-dpo-resume-watchdog-B-data-identity.py        4663 2026/10/6 14:05:45
m3-dpo-resume-watchdog-C-ckpt-integrity.json    13639 2026/10/6 14:21:26
m3-dpo-resume-watchdog-C-ckpt-integrity.py       6979 2026/10/6 14:11:54
m3-dpo-resume-watchdog-C-sha-cache.json          1216 2026/10/6 14:21:26
m3-dpo-resume-watchdog-D-config-check.json       4177 2026/10/6 14:06:12
m3-dpo-resume-watchdog-D-config-check.py         4540 2026/10/6 14:06:10
m3-dpo-resume-watchdog-dpo-series.csv           18424 2026/10/6 14:21:27
m3-dpo-resume-watchdog-E-windows.json           11276 2026/10/6 14:21:26
m3-dpo-resume-watchdog-E-windows.py              8168 2026/10/6 14:07:13
m3-dpo-resume-watchdog-F-stdout-series.csv       9034 2026/10/6 14:21:26
m3-dpo-resume-watchdog-F-stdout-series.json      4733 2026/10/6 14:21:26
m3-dpo-resume-watchdog-F-stdout-series.py        9607 2026/10/6 14:18:09
m3-dpo-resume-watchdog-G-stats.json              5683 2026/10/6 14:21:26
m3-dpo-resume-watchdog-G-stats.py                6167 2026/10/6 14:08:42
m3-dpo-resume-watchdog-H-artifacts.json          5436 2026/10/6 14:21:26
m3-dpo-resume-watchdog-H-artifacts.py            5887 2026/10/6 14:09:44
m3-dpo-resume-watchdog-I-rule-and-lambda.json   46519 2026/10/6 14:21:26
m3-dpo-resume-watchdog-I-rule-and-lambda.py     11125 2026/10/6 14:11:15
m3-dpo-resume-watchdog-J-optimizer.json          7483 2026/10/6 14:13:42
m3-dpo-resume-watchdog-J-optimizer.py            7418 2026/10/6 14:13:39
m3-dpo-resume-watchdog-K-report.py              69109 2026/10/6 14:21:19
m3-dpo-resume-watchdog-L-episodes.json           2114 2026/10/6 14:21:26
m3-dpo-resume-watchdog-L-episodes.py             5694 2026/10/6 14:19:06
m3-dpo-resume-watchdog-M-loss-consistency.json  27307 2026/10/6 14:21:26
m3-dpo-resume-watchdog-M-loss-consistency.py     4155 2026/10/6 14:19:36
m3-dpo-resume-watchdog-raw.py                    6735 2026/10/6 14:21:43
m3-dpo-resume-watchdog-sampler.ps1               2773 2026/10/6 14:05:24
m3-dpo-resume-watchdog-telemetry.csv            11075 2026/10/6 14:21:33
```

## protocol L: below-reference episodes + distance to the pre-registered early stop

*command* (14:21:48):
```powershell
& "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "reports\m3-dpo-resume-watchdog-L-episodes.py"
```

*output* (14:21:48):
```
points=100 steps 5..500
episodes of centered5(chosen)<0 : 2
  steps  315-355  ( 9 pts /  45 steps) min_c5=-1.114@335 min_raw=-1.379@325 acc_mean=0.954 acc>=0.97:3/9 | dChosen=-0.120 dRej=-0.145 both_fell=True 
  steps  490-500  ( 3 pts /  15 steps) min_c5=-1.542@500 min_raw=-2.040@500 acc_mean=0.975 acc>=0.97:2/3 | dChosen=-1.248 dRej=-1.127 both_fell=True <-- IN PROGRESS

current step 500: chosen=-2.0398 rejected=-13.9300 acc=0.9750 margins=11.890 lambda=-0.1335
  acc>=0.97 consecutive points now = 2 (need 5; short by 3)
  margins vs run start = 333.36x ; margins span ratio over last 5 points = 0.973x (need >2)
  EARLY STOP TRIGGERED = False

worst centered5 chosen = -1.5424 @ step 500
worst raw chosen      = -2.0398 @ step 500
raw chosen<0 points   = 19/100
WROTE J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-L-episodes.json
```

## identity check M: loss >= log2*(1-acc)

*command* (14:21:48):
```powershell
& "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "reports\m3-dpo-resume-watchdog-M-loss-consistency.py"
```

*output* (14:21:48):
```
identity  loss >= log2*(1-acc) : violations 0/100  -> holds at every logging point
  excess (loss - log2*(1-acc)): min=0.0158 median=0.0836 max=0.3930
  decomposition (mean of first 20 points vs last 20):
    log2*(1-acc)  : 0.0962 -> 0.0282
    excess        : 0.1800 -> 0.0685
  flipped fraction: 0.1387 -> 0.0406
  last 4 points:
    step 485: loss=0.1322 acc=0.9500 flipped~4.0/80 lower_bound=0.0347 excess=+0.0975
    step 490: loss=0.1022 acc=0.9625 flipped~3.0/80 lower_bound=0.0260 excess=+0.0762
    step 495: loss=0.0489 acc=0.9875 flipped~1.0/80 lower_bound=0.0087 excess=+0.0402
    step 500: loss=0.0429 acc=0.9750 flipped~2.0/80 lower_bound=0.0173 excess=+0.0256
WROTE J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-M-loss-consistency.json
```


# RAW evidence block — 2026-10-06 15:28:25

## host time

*command* (15:28:25):
```powershell
Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
```

*output* (15:28:25):
```
2026-10-06 15:28:25.536
```

## GPU + the ONLY compute app (identification by command line, not exe name)

*command* (15:28:25):
```powershell
nvidia-smi --query-gpu=memory.used,memory.total,power.draw,utilization.gpu --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='llamafactory-cli.exe'" | Select-Object ProcessId,Name,CreationDate,CommandLine | Format-List
```

*output* (15:28:25):
```
1438 MiB, 24455 MiB, 15.68 W, 3 %
13404, [N/A]
14176, [N/A]
12948, [N/A]
15744, [N/A]
15708, [N/A]
24940, [N/A]
25688, [N/A]
24904, [N/A]
10648, [N/A]
35656, [N/A]
32660, [N/A]
35112, [N/A]
6972, [N/A]
32576, [N/A]
22216, [N/A]
15548, [N/A]
648, [N/A]
2424, [N/A]
9892, [N/A]


ProcessId    : 30608
Name         : python.exe
CreationDate : 2026/10/6 15:28:25
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" reports\m3-dpo-resume-watchdog-raw.py

ProcessId    : 35088
Name         : python.exe
CreationDate : 2026/10/6 15:28:25
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" reports\m3-dpo-resume-watchdog-raw.py
```

## host memory / commit / the training processes

*command* (15:28:25):
```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object @{n='free_phys_MiB';e={[int]($_.FreePhysicalMemory/1024)}},@{n='commit_used_MiB';e={[int](($_.TotalVirtualMemorySize-$_.FreeVirtualMemory)/1024)}},@{n='commit_limit_MiB';e={[int]($_.TotalVirtualMemorySize/1024)}} | Format-List
```

*output* (15:28:26):
```


free_phys_MiB    : 23031
commit_used_MiB  : 17814
commit_limit_MiB : 54415
```

## trainer_log.jsonl: size, mtime, first line, last line

*command* (15:28:26):
```powershell
Get-Item 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' | Select-Object Length,LastWriteTime | Format-List; Get-Content 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' -TotalCount 1; Get-Content 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' -Tail 1
```

*output* (15:28:26):
```


Length        : 87365
LastWriteTime : 2026/10/6 15:24:35



{"current_steps": 5, "total_steps": 1803, "loss": 0.6786192893981934, "accuracy": 0.32500001788139343, "lr": 1.3333333333333334e-07, "epoch": 0.0027737327508494556, "percentage": 0.28, "elapsed_time": "0:00:15", "remaining_time": "1:32:04"}
{"current_steps": 1803, "total_steps": 1803, "epoch": 1.0, "percentage": 100.0, "elapsed_time": "1:24:24", "remaining_time": "0:00:00"}
```

## checkpoint dirs (landing times are the file mtimes)

*command* (15:28:26):
```powershell
Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo' -Directory | Select-Object LastWriteTime,Name | Format-Table -AutoSize; Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo' | Select-Object Name,Length | Format-Table -AutoSize
```

*output* (15:28:26):
```

LastWriteTime      Name           
-------------      ----           
2026/10/6 15:08:35 checkpoint-1500
2026/10/6 15:13:52 checkpoint-1600
2026/10/6 15:18:51 checkpoint-1700
2026/10/6 15:24:24 checkpoint-1800
2026/10/6 15:24:35 checkpoint-1803



Name                            Length    
----                            ------    
checkpoint-1500                           
checkpoint-1600                           
checkpoint-1700                           
checkpoint-1800                           
checkpoint-1803                           
all_results.json                215       
chat_template.jinja             4200      
config.json                     1479      
generation_config.json          170       
model.safetensors               2384234968
README.md                       1477      
tokenizer.json                  11422650  
tokenizer_config.json           750       
trainer_log.jsonl               87365     
trainer_state.json              201305    
training_args.bin               5969      
training_loss.png               55248     
training_rewards_accuracies.png 45486     
train_results.json              215
```

## the two resume lines (the primary in-band evidence of a resume)

*command* (15:28:26):
```powershell
$logs='reports\logs\m3-dpo-resume-launch.log','reports\logs\m3-dpo-run.log'; foreach($l in $logs){ if(Test-Path $l){ Write-Host "--- $l"; Get-Content $l -Encoding Unicode | Select-String -Pattern 'Resuming training|Continuing training|global step' | Select-Object -First 6 | ForEach-Object { $_.Line } } }
```

*output* (15:28:26):
```
--- reports\logs\m3-dpo-resume-launch.log
[INFO|2026-10-06 13:59:27] llamafactory.hparams.parser:144 >> Resuming training from J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-200.
[INFO|trainer.py:1482] 2026-10-06 14:00:10,859 >>   Resuming training from checkpoint with epoch 0 and global step 200
--- reports\logs\m3-dpo-run.log
[INFO|2026-10-06 13:59:27] llamafactory.hparams.parser:144 >> Resuming training from J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-200.
[INFO|trainer.py:1482] 2026-10-06 14:00:10,859 >>   Resuming training from checkpoint with epoch 0 and global step 200
```

## the exception/error regex sweep over both logs (expect 0)

*command* (15:28:26):
```powershell
$logs='reports\logs\m3-dpo-resume-launch.log','reports\logs\m3-dpo-run.log'; foreach($p in 'Traceback','CUDA out of memory','RuntimeError','MemoryError','\bnan\b'){ $n=0; foreach($l in $logs){ if(Test-Path $l){ $n += (Get-Content $l -Encoding Unicode | Select-String -Pattern $p -AllMatches).Count } }; Write-Host ('{0,-22} {1}' -f $p,$n) }
```

*output* (15:28:26):
```
Traceback              0
CUDA out of memory     0
RuntimeError           0
MemoryError            0
\bnan\b                0
```

## stdout DPO-metric channel: how many reward dict lines per log + their step range

*command* (15:28:26):
```powershell
$logs='reports\logs\m3-dpo-launch.log','reports\logs\m3-dpo-run.log','reports\logs\m3-dpo-resume-launch.log'; foreach($l in $logs){ if(Test-Path $l){ $m = Get-Content $l -Encoding Unicode | Select-String -Pattern "^\{'loss':"; $first=($m | Select-Object -First 1).Line; $last=($m | Select-Object -Last 1).Line; Write-Host ('{0}: n={1}' -f $l,$m.Count); Write-Host ('   first: ' + $first.Substring(0,[Math]::Min(160,$first.Length))); Write-Host ('   last : ' + $last.Substring(0,[Math]::Min(160,$last.Length))) } }
```

*output* (15:28:27):
```
reports\logs\m3-dpo-launch.log: n=40
   first: {'loss': '0.6786', 'grad_norm': '166.2', 'learning_rate': '1.333e-07', 'rewards/chosen': '0.05243', 'rewards/rejected': '0.01676', 'rewards/accuracies': '0.325'
   last : {'loss': '0.04287', 'grad_norm': '37.76', 'learning_rate': '1.969e-06', 'rewards/chosen': '4.022', 'rewards/rejected': '-6.704', 'rewards/accuracies': '0.9625',
reports\logs\m3-dpo-run.log: n=320
   first: {'loss': '0.152', 'grad_norm': '67.6', 'learning_rate': '1.967e-06', 'rewards/chosen': '1.432', 'rewards/rejected': '-8.24', 'rewards/accuracies': '0.925', 'rew
   last : {'loss': '0.1124', 'grad_norm': '26.79', 'learning_rate': '2.599e-11', 'rewards/chosen': '0.3426', 'rewards/rejected': '-12.46', 'rewards/accuracies': '0.9375',
reports\logs\m3-dpo-resume-launch.log: n=320
   first: {'loss': '0.152', 'grad_norm': '67.6', 'learning_rate': '1.967e-06', 'rewards/chosen': '1.432', 'rewards/rejected': '-8.24', 'rewards/accuracies': '0.925', 'rew
   last : {'loss': '0.1124', 'grad_norm': '26.79', 'learning_rate': '2.599e-11', 'rewards/chosen': '0.3426', 'rewards/rejected': '-12.46', 'rewards/accuracies': '0.9375',
```

## trainer_state.json per checkpoint: global_step + how many rewards/* rows (cumulative)

*command* (15:28:27):
```powershell
Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-*' -Directory | ForEach-Object { $j=Get-Content (Join-Path $_.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; $rw=@($j.log_history | Where-Object { $_.'rewards/chosen' }); Write-Host ('{0}: global_step={1} n_log_history={2} rewards_rows={3} first={4} last={5}' -f $_.Name,$j.global_step,$j.log_history.Count,$rw.Count,$rw[0].step,$rw[-1].step) }
```

*output* (15:28:27):
```
checkpoint-1500: global_step=1500 n_log_history=300 rewards_rows=300 first=5 last=1500
checkpoint-1600: global_step=1600 n_log_history=320 rewards_rows=320 first=5 last=1600
checkpoint-1700: global_step=1700 n_log_history=340 rewards_rows=340 first=5 last=1700
checkpoint-1800: global_step=1800 n_log_history=360 rewards_rows=360 first=5 last=1800
checkpoint-1803: global_step=1803 n_log_history=360 rewards_rows=360 first=5 last=1800
```

## last checkpoint's trainer_state.json max_steps + best_metric

*command* (15:28:27):
```powershell
$d=(Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-*' -Directory | Sort-Object {[int]($_.Name -replace '\D','')} | Select-Object -Last 1); $j=Get-Content (Join-Path $d.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; Write-Host ('dir={0} global_step={1} max_steps={2} epoch={3} best_metric={4}' -f $d.Name,$j.global_step,$j.max_steps,$j.epoch,$j.best_metric)
```

*output* (15:28:27):
```
dir=checkpoint-1803 global_step=1803 max_steps=1803 epoch=1.0 best_metric=
```

## telemetry sampler: is it alive, and its head/tail

*command* (15:28:27):
```powershell
Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv' -TotalCount 2; Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv' -Tail 2; (Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv').Count
```

*output* (15:28:27):
```
ts,step,loss,acc,lr,epoch,elapsed,tl_mtime_ticks,tl_len,mem_used_mib,power_w,util_pct,temp_c,commit_used_mib,free_phys_mib,n_train_procs,ckpt_dirs
2026-10-06 14:05:45,295,0.042900994420051575,0.987500011920929,1.91236869355225E-06,0.16365023230011788,0:05:21,639268635328108778,15241,17734,275.31,45,57,38025,20647,2,checkpoint-100|checkpoint-200
2026-10-06 15:28:06,1803,,,,1.0,1:24:24,639268682756449740,87365,1432,15.34,1,41,18518,23018,0,checkpoint-1500|checkpoint-1600|checkpoint-1700|checkpoint-1800|checkpoint-1803
2026-10-06 15:28:26,1803,,,,1.0,1:24:24,639268682756449740,87365,1432,16.07,3,41,17814,23023,0,checkpoint-1500|checkpoint-1600|checkpoint-1700|checkpoint-1800|checkpoint-1803
248
```

## analysis artifacts present (size + mtime)

*command* (15:28:27):
```powershell
Get-ChildItem 'reports\m3-dpo-resume-watchdog-*' | Sort-Object Name | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
```

*output* (15:28:27):
```

Name                                           Length LastWriteTime     
----                                           ------ -------------     
m3-dpo-resume-watchdog-A.json                  255531 2026/10/6 15:26:18
m3-dpo-resume-watchdog-A-resume-and-metrics.py  12693 2026/10/6 15:25:47
m3-dpo-resume-watchdog-B-data-identity.json      1007 2026/10/6 15:26:18
m3-dpo-resume-watchdog-B-data-identity.py        4663 2026/10/6 14:05:45
m3-dpo-resume-watchdog-C-ckpt-integrity.json    31692 2026/10/6 15:26:18
m3-dpo-resume-watchdog-C-ckpt-integrity.py       9208 2026/10/6 14:54:27
m3-dpo-resume-watchdog-C-sha-cache.json          4851 2026/10/6 15:26:18
m3-dpo-resume-watchdog-D-config-check.json       4177 2026/10/6 15:26:18
m3-dpo-resume-watchdog-D-config-check.py         4540 2026/10/6 14:06:10
m3-dpo-resume-watchdog-dpo-series.csv           66697 2026/10/6 15:28:20
m3-dpo-resume-watchdog-E-windows.json           28202 2026/10/6 15:26:18
m3-dpo-resume-watchdog-E-windows.py              8168 2026/10/6 14:07:13
m3-dpo-resume-watchdog-F-stdout-series.csv      33451 2026/10/6 15:26:18
m3-dpo-resume-watchdog-F-stdout-series.json      6983 2026/10/6 15:26:18
m3-dpo-resume-watchdog-F-stdout-series.py        9607 2026/10/6 14:18:09
m3-dpo-resume-watchdog-G-stats.json              5688 2026/10/6 15:26:18
m3-dpo-resume-watchdog-G-stats.py                6167 2026/10/6 14:08:42
m3-dpo-resume-watchdog-H-artifacts.json          4372 2026/10/6 15:26:19
m3-dpo-resume-watchdog-H-artifacts.py            6238 2026/10/6 14:45:17
m3-dpo-resume-watchdog-I-rule-and-lambda.json  158912 2026/10/6 15:26:18
m3-dpo-resume-watchdog-I-rule-and-lambda.py     11125 2026/10/6 14:11:15
m3-dpo-resume-watchdog-J-optimizer.json          9182 2026/10/6 15:26:19
m3-dpo-resume-watchdog-J-optimizer.py            7767 2026/10/6 15:26:09
m3-dpo-resume-watchdog-K-report.py              92398 2026/10/6 15:28:17
m3-dpo-resume-watchdog-L-episodes.json           9910 2026/10/6 15:26:18
m3-dpo-resume-watchdog-L-episodes.py             6749 2026/10/6 15:03:00
m3-dpo-resume-watchdog-lint.txt                   774 2026/10/6 15:28:20
m3-dpo-resume-watchdog-M-loss-consistency.json  96274 2026/10/6 15:26:18
m3-dpo-resume-watchdog-M-loss-consistency.py     4155 2026/10/6 14:19:36
m3-dpo-resume-watchdog-N-lint.py                 3026 2026/10/6 15:04:49
m3-dpo-resume-watchdog-O-duration.json           2667 2026/10/6 15:26:41
m3-dpo-resume-watchdog-O-duration.py             5572 2026/10/6 15:26:33
m3-dpo-resume-watchdog-raw.py                    6735 2026/10/6 14:21:43
m3-dpo-resume-watchdog-sampler.ps1               2773 2026/10/6 14:05:24
m3-dpo-resume-watchdog-telemetry.csv            59075 2026/10/6 15:28:26
```

## protocol L: below-reference episodes + distance to the pre-registered early stop

*command* (15:28:27):
```powershell
& "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "reports\m3-dpo-resume-watchdog-L-episodes.py"
```

*output* (15:28:27):
```
points=360 steps 5..1800
episodes of centered5(chosen)<0 : 10
  steps  315-355  ( 9 pts /  45 steps) min_c5=-1.114@335 min_raw=-1.379@325 acc_mean=0.954 acc>=0.97:3/9 | dChosen=-0.120 dRej=-0.145 both_fell=True 
  steps  490-610  (25 pts / 125 steps) min_c5=-2.181@575 min_raw=-3.898@510 acc_mean=0.948 acc>=0.97:7/25 | dChosen=+0.203 dRej=+1.062 both_fell=False 
  steps  810-840  ( 7 pts /  35 steps) min_c5=-0.928@825 min_raw=-1.680@830 acc_mean=0.963 acc>=0.97:2/7 | dChosen=-0.024 dRej=+0.274 both_fell=False 
  steps  850-865  ( 4 pts /  20 steps) min_c5=-0.327@855 min_raw=-1.348@860 acc_mean=0.966 acc>=0.97:2/4 | dChosen=-0.043 dRej=-0.036 both_fell=True 
  steps  950-955  ( 2 pts /  10 steps) min_c5=-0.171@950 min_raw=-0.885@955 acc_mean=0.988 acc>=0.97:2/2 | dChosen=+0.102 dRej=+0.152 both_fell=False 
  steps  965-965  ( 1 pts /   5 steps) min_c5=-0.226@965 min_raw=+0.116@965 acc_mean=0.938 acc>=0.97:0/1 | dChosen=+0.000 dRej=+0.000 both_fell=False 
  steps 1105-1125 ( 5 pts /  25 steps) min_c5=-0.277@1115 min_raw=-0.621@1110 acc_mean=0.935 acc>=0.97:1/5 | dChosen=+0.046 dRej=-0.121 both_fell=False 
  steps 1205-1230 ( 6 pts /  30 steps) min_c5=-0.565@1225 min_raw=-1.205@1220 acc_mean=0.954 acc>=0.97:2/6 | dChosen=-0.091 dRej=-0.438 both_fell=True 
  steps 1240-1295 (12 pts /  60 steps) min_c5=-1.108@1275 min_raw=-1.635@1275 acc_mean=0.951 acc>=0.97:3/12 | dChosen=-0.036 dRej=-0.206 both_fell=True 
  steps 1335-1335 ( 1 pts /   5 steps) min_c5=-0.129@1335 min_raw=-0.010@1335 acc_mean=0.963 acc>=0.97:0/1 | dChosen=+0.000 dRej=+0.000 both_fell=False 

current step 1800: chosen=+0.3426 rejected=-12.4630 acc=0.9375 margins=12.806 lambda=0.1070
  acc>=0.97 consecutive points now = 0 (need 5; short by 5)
  margins vs run start = 359.03x ; margins span ratio over last 5 points = 0.961x (need >2)
  EARLY STOP TRIGGERED = False

worst centered5 chosen = -2.1814 @ step 575
worst raw chosen      = -3.8984 @ step 510
raw chosen<0 points   = 104/360
WROTE J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-L-episodes.json
```

## identity check M: loss >= log2*(1-acc)

*command* (15:28:27):
```powershell
& "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "reports\m3-dpo-resume-watchdog-M-loss-consistency.py"
```

*output* (15:28:28):
```
identity  loss >= log2*(1-acc) : violations 0/360  -> holds at every logging point
  excess (loss - log2*(1-acc)): min=0.0030 median=0.0730 max=0.3930
  decomposition (mean of first 20 points vs last 20):
    log2*(1-acc)  : 0.0962 -> 0.0316
    excess        : 0.1800 -> 0.0676
  flipped fraction: 0.1387 -> 0.0456
  last 4 points:
    step 1785: loss=0.2605 acc=0.9250 flipped~6.0/80 lower_bound=0.0520 excess=+0.2085
    step 1790: loss=0.0896 acc=0.9500 flipped~4.0/80 lower_bound=0.0347 excess=+0.0549
    step 1795: loss=0.1035 acc=0.9500 flipped~4.0/80 lower_bound=0.0347 excess=+0.0689
    step 1800: loss=0.1124 acc=0.9375 flipped~5.0/80 lower_bound=0.0433 excess=+0.0691
WROTE J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-M-loss-consistency.json
```


# RAW evidence block — 2026-10-06 15:32:03

## host time

*command* (15:32:03):
```powershell
Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
```

*output* (15:32:03):
```
2026-10-06 15:32:03.194
```

## GPU + the ONLY compute app (identification by command line, not exe name)

*command* (15:32:03):
```powershell
nvidia-smi --query-gpu=memory.used,memory.total,power.draw,utilization.gpu --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='llamafactory-cli.exe'" | Select-Object ProcessId,Name,CreationDate,CommandLine | Format-List
```

*output* (15:32:03):
```
3320 MiB, 24455 MiB, 118.79 W, 23 %
13404, [N/A]
14176, [N/A]
12948, [N/A]
15744, [N/A]
15708, [N/A]
24940, [N/A]
25688, [N/A]
24904, [N/A]
10648, [N/A]
35656, [N/A]
32660, [N/A]
35112, [N/A]
6972, [N/A]
32576, [N/A]
22216, [N/A]
15548, [N/A]
648, [N/A]
2424, [N/A]
9892, [N/A]
20880, [N/A]


ProcessId    : 23000
Name         : python.exe
CreationDate : 2026/10/6 15:29:14
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" scripts\baseline_eval.py --model J:\Projects\llm_for_
               sec\checkpoints\qwen3-06b-sec-m3-dpo --heldout J:\Projects\llm_for_sec\data\heldout\v0.3-gen --prompt-fo
               rmat chat --out J:\Projects\llm_for_sec\reports\heldout-chat-gen-m3-dpo.json --dump-responses J:\Project
               s\llm_for_sec\reports\resp-chat-gen-m3-dpo.jsonl

ProcessId    : 20880
Name         : python.exe
CreationDate : 2026/10/6 15:29:14
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" scripts\baseline_eval.py --model J:\Projects\llm_for_
               sec\checkpoints\qwen3-06b-sec-m3-dpo --heldout J:\Projects\llm_for_sec\data\heldout\v0.3-gen --prompt-fo
               rmat chat --out J:\Projects\llm_for_sec\reports\heldout-chat-gen-m3-dpo.json --dump-responses J:\Project
               s\llm_for_sec\reports\resp-chat-gen-m3-dpo.jsonl

ProcessId    : 36324
Name         : python.exe
CreationDate : 2026/10/6 15:31:48
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" scripts\check_document_gate.py

ProcessId    : 12808
Name         : python.exe
CreationDate : 2026/10/6 15:31:48
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" scripts\check_document_gate.py

ProcessId    : 31168
Name         : python.exe
CreationDate : 2026/10/6 15:31:56
CommandLine  : "C:\Python314\python.exe" scripts\check_document_gate.py --stats-out .scratch\doc_gate_stats.json

ProcessId    : 21364
Name         : python.exe
CreationDate : 2026/10/6 15:32:03
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" reports\m3-dpo-resume-watchdog-raw.py

ProcessId    : 3328
Name         : python.exe
CreationDate : 2026/10/6 15:32:03
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" reports\m3-dpo-resume-watchdog-raw.py
```

## host memory / commit / the training processes

*command* (15:32:03):
```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object @{n='free_phys_MiB';e={[int]($_.FreePhysicalMemory/1024)}},@{n='commit_used_MiB';e={[int](($_.TotalVirtualMemorySize-$_.FreeVirtualMemory)/1024)}},@{n='commit_limit_MiB';e={[int]($_.TotalVirtualMemorySize/1024)}} | Format-List
```

*output* (15:32:03):
```


free_phys_MiB    : 20735
commit_used_MiB  : 24100
commit_limit_MiB : 54415
```

## trainer_log.jsonl: size, mtime, first line, last line

*command* (15:32:03):
```powershell
Get-Item 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' | Select-Object Length,LastWriteTime | Format-List; Get-Content 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' -TotalCount 1; Get-Content 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' -Tail 1
```

*output* (15:32:03):
```


Length        : 87365
LastWriteTime : 2026/10/6 15:24:35



{"current_steps": 5, "total_steps": 1803, "loss": 0.6786192893981934, "accuracy": 0.32500001788139343, "lr": 1.3333333333333334e-07, "epoch": 0.0027737327508494556, "percentage": 0.28, "elapsed_time": "0:00:15", "remaining_time": "1:32:04"}
{"current_steps": 1803, "total_steps": 1803, "epoch": 1.0, "percentage": 100.0, "elapsed_time": "1:24:24", "remaining_time": "0:00:00"}
```

## checkpoint dirs (landing times are the file mtimes)

*command* (15:32:03):
```powershell
Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo' -Directory | Select-Object LastWriteTime,Name | Format-Table -AutoSize; Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo' | Select-Object Name,Length | Format-Table -AutoSize
```

*output* (15:32:04):
```

LastWriteTime      Name           
-------------      ----           
2026/10/6 15:08:35 checkpoint-1500
2026/10/6 15:13:52 checkpoint-1600
2026/10/6 15:18:51 checkpoint-1700
2026/10/6 15:24:24 checkpoint-1800
2026/10/6 15:24:35 checkpoint-1803



Name                            Length    
----                            ------    
checkpoint-1500                           
checkpoint-1600                           
checkpoint-1700                           
checkpoint-1800                           
checkpoint-1803                           
all_results.json                215       
chat_template.jinja             4200      
config.json                     1479      
generation_config.json          170       
model.safetensors               2384234968
README.md                       1477      
tokenizer.json                  11422650  
tokenizer_config.json           750       
trainer_log.jsonl               87365     
trainer_state.json              201305    
training_args.bin               5969      
training_loss.png               55248     
training_rewards_accuracies.png 45486     
train_results.json              215
```

## the two resume lines (the primary in-band evidence of a resume)

*command* (15:32:04):
```powershell
$logs='reports\logs\m3-dpo-resume-launch.log','reports\logs\m3-dpo-run.log'; foreach($l in $logs){ if(Test-Path $l){ Write-Host "--- $l"; Get-Content $l -Encoding Unicode | Select-String -Pattern 'Resuming training|Continuing training|global step' | Select-Object -First 6 | ForEach-Object { $_.Line } } }
```

*output* (15:32:04):
```
--- reports\logs\m3-dpo-resume-launch.log
[INFO|2026-10-06 13:59:27] llamafactory.hparams.parser:144 >> Resuming training from J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-200.
[INFO|trainer.py:1482] 2026-10-06 14:00:10,859 >>   Resuming training from checkpoint with epoch 0 and global step 200
--- reports\logs\m3-dpo-run.log
[INFO|2026-10-06 13:59:27] llamafactory.hparams.parser:144 >> Resuming training from J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-200.
[INFO|trainer.py:1482] 2026-10-06 14:00:10,859 >>   Resuming training from checkpoint with epoch 0 and global step 200
```

## the exception/error regex sweep over both logs (expect 0)

*command* (15:32:04):
```powershell
$logs='reports\logs\m3-dpo-resume-launch.log','reports\logs\m3-dpo-run.log'; foreach($p in 'Traceback','CUDA out of memory','RuntimeError','MemoryError','\bnan\b'){ $n=0; foreach($l in $logs){ if(Test-Path $l){ $n += (Get-Content $l -Encoding Unicode | Select-String -Pattern $p -AllMatches).Count } }; Write-Host ('{0,-22} {1}' -f $p,$n) }
```

*output* (15:32:04):
```
Traceback              0
CUDA out of memory     0
RuntimeError           0
MemoryError            0
\bnan\b                0
```

## stdout DPO-metric channel: how many reward dict lines per log + their step range

*command* (15:32:04):
```powershell
$logs='reports\logs\m3-dpo-launch.log','reports\logs\m3-dpo-run.log','reports\logs\m3-dpo-resume-launch.log'; foreach($l in $logs){ if(Test-Path $l){ $m = Get-Content $l -Encoding Unicode | Select-String -Pattern "^\{'loss':"; $first=($m | Select-Object -First 1).Line; $last=($m | Select-Object -Last 1).Line; Write-Host ('{0}: n={1}' -f $l,$m.Count); Write-Host ('   first: ' + $first.Substring(0,[Math]::Min(160,$first.Length))); Write-Host ('   last : ' + $last.Substring(0,[Math]::Min(160,$last.Length))) } }
```

*output* (15:32:04):
```
reports\logs\m3-dpo-launch.log: n=40
   first: {'loss': '0.6786', 'grad_norm': '166.2', 'learning_rate': '1.333e-07', 'rewards/chosen': '0.05243', 'rewards/rejected': '0.01676', 'rewards/accuracies': '0.325'
   last : {'loss': '0.04287', 'grad_norm': '37.76', 'learning_rate': '1.969e-06', 'rewards/chosen': '4.022', 'rewards/rejected': '-6.704', 'rewards/accuracies': '0.9625',
reports\logs\m3-dpo-run.log: n=320
   first: {'loss': '0.152', 'grad_norm': '67.6', 'learning_rate': '1.967e-06', 'rewards/chosen': '1.432', 'rewards/rejected': '-8.24', 'rewards/accuracies': '0.925', 'rew
   last : {'loss': '0.1124', 'grad_norm': '26.79', 'learning_rate': '2.599e-11', 'rewards/chosen': '0.3426', 'rewards/rejected': '-12.46', 'rewards/accuracies': '0.9375',
reports\logs\m3-dpo-resume-launch.log: n=320
   first: {'loss': '0.152', 'grad_norm': '67.6', 'learning_rate': '1.967e-06', 'rewards/chosen': '1.432', 'rewards/rejected': '-8.24', 'rewards/accuracies': '0.925', 'rew
   last : {'loss': '0.1124', 'grad_norm': '26.79', 'learning_rate': '2.599e-11', 'rewards/chosen': '0.3426', 'rewards/rejected': '-12.46', 'rewards/accuracies': '0.9375',
```

## trainer_state.json per checkpoint: global_step + how many rewards/* rows (cumulative)

*command* (15:32:04):
```powershell
Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-*' -Directory | ForEach-Object { $j=Get-Content (Join-Path $_.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; $rw=@($j.log_history | Where-Object { $_.'rewards/chosen' }); Write-Host ('{0}: global_step={1} n_log_history={2} rewards_rows={3} first={4} last={5}' -f $_.Name,$j.global_step,$j.log_history.Count,$rw.Count,$rw[0].step,$rw[-1].step) }
```

*output* (15:32:05):
```
checkpoint-1500: global_step=1500 n_log_history=300 rewards_rows=300 first=5 last=1500
checkpoint-1600: global_step=1600 n_log_history=320 rewards_rows=320 first=5 last=1600
checkpoint-1700: global_step=1700 n_log_history=340 rewards_rows=340 first=5 last=1700
checkpoint-1800: global_step=1800 n_log_history=360 rewards_rows=360 first=5 last=1800
checkpoint-1803: global_step=1803 n_log_history=360 rewards_rows=360 first=5 last=1800
```

## last checkpoint's trainer_state.json max_steps + best_metric

*command* (15:32:05):
```powershell
$d=(Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-*' -Directory | Sort-Object {[int]($_.Name -replace '\D','')} | Select-Object -Last 1); $j=Get-Content (Join-Path $d.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; Write-Host ('dir={0} global_step={1} max_steps={2} epoch={3} best_metric={4}' -f $d.Name,$j.global_step,$j.max_steps,$j.epoch,$j.best_metric)
```

*output* (15:32:05):
```
dir=checkpoint-1803 global_step=1803 max_steps=1803 epoch=1.0 best_metric=
```

## telemetry sampler: is it alive, and its head/tail

*command* (15:32:05):
```powershell
Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv' -TotalCount 2; Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv' -Tail 2; (Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv').Count
```

*output* (15:32:05):
```
ts,step,loss,acc,lr,epoch,elapsed,tl_mtime_ticks,tl_len,mem_used_mib,power_w,util_pct,temp_c,commit_used_mib,free_phys_mib,n_train_procs,ckpt_dirs
2026-10-06 14:05:45,295,0.042900994420051575,0.987500011920929,1.91236869355225E-06,0.16365023230011788,0:05:21,639268635328108778,15241,17734,275.31,45,57,38025,20647,2,checkpoint-100|checkpoint-200
2026-10-06 15:30:47,1803,,,,1.0,1:24:24,639268682756449740,87365,3320,119.04,28,46,23930,20858,0,checkpoint-1500|checkpoint-1600|checkpoint-1700|checkpoint-1800|checkpoint-1803
2026-10-06 15:31:07,1803,,,,1.0,1:24:24,639268682756449740,87365,3321,125.21,29,45,23836,20900,0,checkpoint-1500|checkpoint-1600|checkpoint-1700|checkpoint-1800|checkpoint-1803
256
```

## analysis artifacts present (size + mtime)

*command* (15:32:05):
```powershell
Get-ChildItem 'reports\m3-dpo-resume-watchdog-*' | Sort-Object Name | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
```

*output* (15:32:05):
```

Name                                           Length LastWriteTime     
----                                           ------ -------------     
m3-dpo-resume-watchdog-A.json                  255531 2026/10/6 15:26:18
m3-dpo-resume-watchdog-A-resume-and-metrics.py  12693 2026/10/6 15:25:47
m3-dpo-resume-watchdog-B-data-identity.json      1007 2026/10/6 15:26:18
m3-dpo-resume-watchdog-B-data-identity.py        4663 2026/10/6 14:05:45
m3-dpo-resume-watchdog-C-ckpt-integrity.json    31692 2026/10/6 15:26:18
m3-dpo-resume-watchdog-C-ckpt-integrity.py       9208 2026/10/6 14:54:27
m3-dpo-resume-watchdog-C-sha-cache.json          4851 2026/10/6 15:26:18
m3-dpo-resume-watchdog-D-config-check.json       4177 2026/10/6 15:26:18
m3-dpo-resume-watchdog-D-config-check.py         4540 2026/10/6 14:06:10
m3-dpo-resume-watchdog-dpo-series.csv           66697 2026/10/6 15:32:02
m3-dpo-resume-watchdog-E-windows.json           28202 2026/10/6 15:26:18
m3-dpo-resume-watchdog-E-windows.py              8168 2026/10/6 14:07:13
m3-dpo-resume-watchdog-F-stdout-series.csv      33451 2026/10/6 15:26:18
m3-dpo-resume-watchdog-F-stdout-series.json      6983 2026/10/6 15:26:18
m3-dpo-resume-watchdog-F-stdout-series.py        9607 2026/10/6 14:18:09
m3-dpo-resume-watchdog-G-stats.json              5688 2026/10/6 15:26:18
m3-dpo-resume-watchdog-G-stats.py                6167 2026/10/6 14:08:42
m3-dpo-resume-watchdog-H-artifacts.json          4372 2026/10/6 15:26:19
m3-dpo-resume-watchdog-H-artifacts.py            6238 2026/10/6 14:45:17
m3-dpo-resume-watchdog-I-rule-and-lambda.json  158912 2026/10/6 15:26:18
m3-dpo-resume-watchdog-I-rule-and-lambda.py     11125 2026/10/6 14:11:15
m3-dpo-resume-watchdog-J-optimizer.json          9182 2026/10/6 15:26:19
m3-dpo-resume-watchdog-J-optimizer.py            7767 2026/10/6 15:26:09
m3-dpo-resume-watchdog-K-report.py              99364 2026/10/6 15:32:00
m3-dpo-resume-watchdog-L-episodes.json           9910 2026/10/6 15:28:27
m3-dpo-resume-watchdog-L-episodes.py             6749 2026/10/6 15:03:00
m3-dpo-resume-watchdog-lint.txt                   786 2026/10/6 15:32:02
m3-dpo-resume-watchdog-M-loss-consistency.json  96274 2026/10/6 15:28:28
m3-dpo-resume-watchdog-M-loss-consistency.py     4155 2026/10/6 14:19:36
m3-dpo-resume-watchdog-N-lint.py                 3026 2026/10/6 15:04:49
m3-dpo-resume-watchdog-O-duration.json           2667 2026/10/6 15:26:41
m3-dpo-resume-watchdog-O-duration.py             5572 2026/10/6 15:26:33
m3-dpo-resume-watchdog-raw.py                    6735 2026/10/6 14:21:43
m3-dpo-resume-watchdog-sampler.ps1               2773 2026/10/6 14:05:24
m3-dpo-resume-watchdog-telemetry.csv            60498 2026/10/6 15:31:07
```

## protocol L: below-reference episodes + distance to the pre-registered early stop

*command* (15:32:05):
```powershell
& "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "reports\m3-dpo-resume-watchdog-L-episodes.py"
```

*output* (15:32:05):
```
points=360 steps 5..1800
episodes of centered5(chosen)<0 : 10
  steps  315-355  ( 9 pts /  45 steps) min_c5=-1.114@335 min_raw=-1.379@325 acc_mean=0.954 acc>=0.97:3/9 | dChosen=-0.120 dRej=-0.145 both_fell=True 
  steps  490-610  (25 pts / 125 steps) min_c5=-2.181@575 min_raw=-3.898@510 acc_mean=0.948 acc>=0.97:7/25 | dChosen=+0.203 dRej=+1.062 both_fell=False 
  steps  810-840  ( 7 pts /  35 steps) min_c5=-0.928@825 min_raw=-1.680@830 acc_mean=0.963 acc>=0.97:2/7 | dChosen=-0.024 dRej=+0.274 both_fell=False 
  steps  850-865  ( 4 pts /  20 steps) min_c5=-0.327@855 min_raw=-1.348@860 acc_mean=0.966 acc>=0.97:2/4 | dChosen=-0.043 dRej=-0.036 both_fell=True 
  steps  950-955  ( 2 pts /  10 steps) min_c5=-0.171@950 min_raw=-0.885@955 acc_mean=0.988 acc>=0.97:2/2 | dChosen=+0.102 dRej=+0.152 both_fell=False 
  steps  965-965  ( 1 pts /   5 steps) min_c5=-0.226@965 min_raw=+0.116@965 acc_mean=0.938 acc>=0.97:0/1 | dChosen=+0.000 dRej=+0.000 both_fell=False 
  steps 1105-1125 ( 5 pts /  25 steps) min_c5=-0.277@1115 min_raw=-0.621@1110 acc_mean=0.935 acc>=0.97:1/5 | dChosen=+0.046 dRej=-0.121 both_fell=False 
  steps 1205-1230 ( 6 pts /  30 steps) min_c5=-0.565@1225 min_raw=-1.205@1220 acc_mean=0.954 acc>=0.97:2/6 | dChosen=-0.091 dRej=-0.438 both_fell=True 
  steps 1240-1295 (12 pts /  60 steps) min_c5=-1.108@1275 min_raw=-1.635@1275 acc_mean=0.951 acc>=0.97:3/12 | dChosen=-0.036 dRej=-0.206 both_fell=True 
  steps 1335-1335 ( 1 pts /   5 steps) min_c5=-0.129@1335 min_raw=-0.010@1335 acc_mean=0.963 acc>=0.97:0/1 | dChosen=+0.000 dRej=+0.000 both_fell=False 

current step 1800: chosen=+0.3426 rejected=-12.4630 acc=0.9375 margins=12.806 lambda=0.1070
  acc>=0.97 consecutive points now = 0 (need 5; short by 5)
  margins vs run start = 359.03x ; margins span ratio over last 5 points = 0.961x (need >2)
  EARLY STOP TRIGGERED = False

worst centered5 chosen = -2.1814 @ step 575
worst raw chosen      = -3.8984 @ step 510
raw chosen<0 points   = 104/360
WROTE J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-L-episodes.json
```

## identity check M: loss >= log2*(1-acc)

*command* (15:32:05):
```powershell
& "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "reports\m3-dpo-resume-watchdog-M-loss-consistency.py"
```

*output* (15:32:05):
```
identity  loss >= log2*(1-acc) : violations 0/360  -> holds at every logging point
  excess (loss - log2*(1-acc)): min=0.0030 median=0.0730 max=0.3930
  decomposition (mean of first 20 points vs last 20):
    log2*(1-acc)  : 0.0962 -> 0.0316
    excess        : 0.1800 -> 0.0676
  flipped fraction: 0.1387 -> 0.0456
  last 4 points:
    step 1785: loss=0.2605 acc=0.9250 flipped~6.0/80 lower_bound=0.0520 excess=+0.2085
    step 1790: loss=0.0896 acc=0.9500 flipped~4.0/80 lower_bound=0.0347 excess=+0.0549
    step 1795: loss=0.1035 acc=0.9500 flipped~4.0/80 lower_bound=0.0347 excess=+0.0689
    step 1800: loss=0.1124 acc=0.9375 flipped~5.0/80 lower_bound=0.0433 excess=+0.0691
WROTE J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-M-loss-consistency.json
```


# RAW evidence block — 2026-10-06 15:33:06

## host time

*command* (15:33:06):
```powershell
Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
```

*output* (15:33:06):
```
2026-10-06 15:33:06.653
```

## GPU + the ONLY compute app (identification by command line, not exe name)

*command* (15:33:06):
```powershell
nvidia-smi --query-gpu=memory.used,memory.total,power.draw,utilization.gpu --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='llamafactory-cli.exe'" | Select-Object ProcessId,Name,CreationDate,CommandLine | Format-List
```

*output* (15:33:06):
```
3315 MiB, 24455 MiB, 125.74 W, 30 %
13404, [N/A]
14176, [N/A]
12948, [N/A]
15744, [N/A]
15708, [N/A]
24940, [N/A]
25688, [N/A]
24904, [N/A]
10648, [N/A]
35656, [N/A]
32660, [N/A]
35112, [N/A]
6972, [N/A]
32576, [N/A]
22216, [N/A]
15548, [N/A]
648, [N/A]
2424, [N/A]
9892, [N/A]
20880, [N/A]


ProcessId    : 23000
Name         : python.exe
CreationDate : 2026/10/6 15:29:14
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" scripts\baseline_eval.py --model J:\Projects\llm_for_
               sec\checkpoints\qwen3-06b-sec-m3-dpo --heldout J:\Projects\llm_for_sec\data\heldout\v0.3-gen --prompt-fo
               rmat chat --out J:\Projects\llm_for_sec\reports\heldout-chat-gen-m3-dpo.json --dump-responses J:\Project
               s\llm_for_sec\reports\resp-chat-gen-m3-dpo.jsonl

ProcessId    : 20880
Name         : python.exe
CreationDate : 2026/10/6 15:29:14
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" scripts\baseline_eval.py --model J:\Projects\llm_for_
               sec\checkpoints\qwen3-06b-sec-m3-dpo --heldout J:\Projects\llm_for_sec\data\heldout\v0.3-gen --prompt-fo
               rmat chat --out J:\Projects\llm_for_sec\reports\heldout-chat-gen-m3-dpo.json --dump-responses J:\Project
               s\llm_for_sec\reports\resp-chat-gen-m3-dpo.jsonl

ProcessId    : 31392
Name         : python.exe
CreationDate : 2026/10/6 15:33:06
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" reports\m3-dpo-resume-watchdog-raw.py

ProcessId    : 35072
Name         : python.exe
CreationDate : 2026/10/6 15:33:06
CommandLine  : "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" reports\m3-dpo-resume-watchdog-raw.py
```

## host memory / commit / the training processes

*command* (15:33:06):
```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object @{n='free_phys_MiB';e={[int]($_.FreePhysicalMemory/1024)}},@{n='commit_used_MiB';e={[int](($_.TotalVirtualMemorySize-$_.FreeVirtualMemory)/1024)}},@{n='commit_limit_MiB';e={[int]($_.TotalVirtualMemorySize/1024)}} | Format-List
```

*output* (15:33:07):
```


free_phys_MiB    : 20893
commit_used_MiB  : 23858
commit_limit_MiB : 54415
```

## trainer_log.jsonl: size, mtime, first line, last line

*command* (15:33:07):
```powershell
Get-Item 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' | Select-Object Length,LastWriteTime | Format-List; Get-Content 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' -TotalCount 1; Get-Content 'checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl' -Tail 1
```

*output* (15:33:07):
```


Length        : 87365
LastWriteTime : 2026/10/6 15:24:35



{"current_steps": 5, "total_steps": 1803, "loss": 0.6786192893981934, "accuracy": 0.32500001788139343, "lr": 1.3333333333333334e-07, "epoch": 0.0027737327508494556, "percentage": 0.28, "elapsed_time": "0:00:15", "remaining_time": "1:32:04"}
{"current_steps": 1803, "total_steps": 1803, "epoch": 1.0, "percentage": 100.0, "elapsed_time": "1:24:24", "remaining_time": "0:00:00"}
```

## checkpoint dirs (landing times are the file mtimes)

*command* (15:33:07):
```powershell
Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo' -Directory | Select-Object LastWriteTime,Name | Format-Table -AutoSize; Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo' | Select-Object Name,Length | Format-Table -AutoSize
```

*output* (15:33:07):
```

LastWriteTime      Name           
-------------      ----           
2026/10/6 15:08:35 checkpoint-1500
2026/10/6 15:13:52 checkpoint-1600
2026/10/6 15:18:51 checkpoint-1700
2026/10/6 15:24:24 checkpoint-1800
2026/10/6 15:24:35 checkpoint-1803



Name                            Length    
----                            ------    
checkpoint-1500                           
checkpoint-1600                           
checkpoint-1700                           
checkpoint-1800                           
checkpoint-1803                           
all_results.json                215       
chat_template.jinja             4200      
config.json                     1479      
generation_config.json          170       
model.safetensors               2384234968
README.md                       1477      
tokenizer.json                  11422650  
tokenizer_config.json           750       
trainer_log.jsonl               87365     
trainer_state.json              201305    
training_args.bin               5969      
training_loss.png               55248     
training_rewards_accuracies.png 45486     
train_results.json              215
```

## the two resume lines (the primary in-band evidence of a resume)

*command* (15:33:07):
```powershell
$logs='reports\logs\m3-dpo-resume-launch.log','reports\logs\m3-dpo-run.log'; foreach($l in $logs){ if(Test-Path $l){ Write-Host "--- $l"; Get-Content $l -Encoding Unicode | Select-String -Pattern 'Resuming training|Continuing training|global step' | Select-Object -First 6 | ForEach-Object { $_.Line } } }
```

*output* (15:33:07):
```
--- reports\logs\m3-dpo-resume-launch.log
[INFO|2026-10-06 13:59:27] llamafactory.hparams.parser:144 >> Resuming training from J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-200.
[INFO|trainer.py:1482] 2026-10-06 14:00:10,859 >>   Resuming training from checkpoint with epoch 0 and global step 200
--- reports\logs\m3-dpo-run.log
[INFO|2026-10-06 13:59:27] llamafactory.hparams.parser:144 >> Resuming training from J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-200.
[INFO|trainer.py:1482] 2026-10-06 14:00:10,859 >>   Resuming training from checkpoint with epoch 0 and global step 200
```

## the exception/error regex sweep over both logs (expect 0)

*command* (15:33:07):
```powershell
$logs='reports\logs\m3-dpo-resume-launch.log','reports\logs\m3-dpo-run.log'; foreach($p in 'Traceback','CUDA out of memory','RuntimeError','MemoryError','\bnan\b'){ $n=0; foreach($l in $logs){ if(Test-Path $l){ $n += (Get-Content $l -Encoding Unicode | Select-String -Pattern $p -AllMatches).Count } }; Write-Host ('{0,-22} {1}' -f $p,$n) }
```

*output* (15:33:07):
```
Traceback              0
CUDA out of memory     0
RuntimeError           0
MemoryError            0
\bnan\b                0
```

## stdout DPO-metric channel: how many reward dict lines per log + their step range

*command* (15:33:07):
```powershell
$logs='reports\logs\m3-dpo-launch.log','reports\logs\m3-dpo-run.log','reports\logs\m3-dpo-resume-launch.log'; foreach($l in $logs){ if(Test-Path $l){ $m = Get-Content $l -Encoding Unicode | Select-String -Pattern "^\{'loss':"; $first=($m | Select-Object -First 1).Line; $last=($m | Select-Object -Last 1).Line; Write-Host ('{0}: n={1}' -f $l,$m.Count); Write-Host ('   first: ' + $first.Substring(0,[Math]::Min(160,$first.Length))); Write-Host ('   last : ' + $last.Substring(0,[Math]::Min(160,$last.Length))) } }
```

*output* (15:33:08):
```
reports\logs\m3-dpo-launch.log: n=40
   first: {'loss': '0.6786', 'grad_norm': '166.2', 'learning_rate': '1.333e-07', 'rewards/chosen': '0.05243', 'rewards/rejected': '0.01676', 'rewards/accuracies': '0.325'
   last : {'loss': '0.04287', 'grad_norm': '37.76', 'learning_rate': '1.969e-06', 'rewards/chosen': '4.022', 'rewards/rejected': '-6.704', 'rewards/accuracies': '0.9625',
reports\logs\m3-dpo-run.log: n=320
   first: {'loss': '0.152', 'grad_norm': '67.6', 'learning_rate': '1.967e-06', 'rewards/chosen': '1.432', 'rewards/rejected': '-8.24', 'rewards/accuracies': '0.925', 'rew
   last : {'loss': '0.1124', 'grad_norm': '26.79', 'learning_rate': '2.599e-11', 'rewards/chosen': '0.3426', 'rewards/rejected': '-12.46', 'rewards/accuracies': '0.9375',
reports\logs\m3-dpo-resume-launch.log: n=320
   first: {'loss': '0.152', 'grad_norm': '67.6', 'learning_rate': '1.967e-06', 'rewards/chosen': '1.432', 'rewards/rejected': '-8.24', 'rewards/accuracies': '0.925', 'rew
   last : {'loss': '0.1124', 'grad_norm': '26.79', 'learning_rate': '2.599e-11', 'rewards/chosen': '0.3426', 'rewards/rejected': '-12.46', 'rewards/accuracies': '0.9375',
```

## trainer_state.json per checkpoint: global_step + how many rewards/* rows (cumulative)

*command* (15:33:08):
```powershell
Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-*' -Directory | ForEach-Object { $j=Get-Content (Join-Path $_.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; $rw=@($j.log_history | Where-Object { $_.'rewards/chosen' }); Write-Host ('{0}: global_step={1} n_log_history={2} rewards_rows={3} first={4} last={5}' -f $_.Name,$j.global_step,$j.log_history.Count,$rw.Count,$rw[0].step,$rw[-1].step) }
```

*output* (15:33:08):
```
checkpoint-1500: global_step=1500 n_log_history=300 rewards_rows=300 first=5 last=1500
checkpoint-1600: global_step=1600 n_log_history=320 rewards_rows=320 first=5 last=1600
checkpoint-1700: global_step=1700 n_log_history=340 rewards_rows=340 first=5 last=1700
checkpoint-1800: global_step=1800 n_log_history=360 rewards_rows=360 first=5 last=1800
checkpoint-1803: global_step=1803 n_log_history=360 rewards_rows=360 first=5 last=1800
```

## last checkpoint's trainer_state.json max_steps + best_metric

*command* (15:33:08):
```powershell
$d=(Get-ChildItem 'checkpoints\qwen3-06b-sec-m3-dpo\checkpoint-*' -Directory | Sort-Object {[int]($_.Name -replace '\D','')} | Select-Object -Last 1); $j=Get-Content (Join-Path $d.FullName 'trainer_state.json') -Raw | ConvertFrom-Json; Write-Host ('dir={0} global_step={1} max_steps={2} epoch={3} best_metric={4}' -f $d.Name,$j.global_step,$j.max_steps,$j.epoch,$j.best_metric)
```

*output* (15:33:08):
```
dir=checkpoint-1803 global_step=1803 max_steps=1803 epoch=1.0 best_metric=
```

## telemetry sampler: is it alive, and its head/tail

*command* (15:33:08):
```powershell
Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv' -TotalCount 2; Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv' -Tail 2; (Get-Content 'reports\m3-dpo-resume-watchdog-telemetry.csv').Count
```

*output* (15:33:08):
```
ts,step,loss,acc,lr,epoch,elapsed,tl_mtime_ticks,tl_len,mem_used_mib,power_w,util_pct,temp_c,commit_used_mib,free_phys_mib,n_train_procs,ckpt_dirs
2026-10-06 14:05:45,295,0.042900994420051575,0.987500011920929,1.91236869355225E-06,0.16365023230011788,0:05:21,639268635328108778,15241,17734,275.31,45,57,38025,20647,2,checkpoint-100|checkpoint-200
2026-10-06 15:30:47,1803,,,,1.0,1:24:24,639268682756449740,87365,3320,119.04,28,46,23930,20858,0,checkpoint-1500|checkpoint-1600|checkpoint-1700|checkpoint-1800|checkpoint-1803
2026-10-06 15:31:07,1803,,,,1.0,1:24:24,639268682756449740,87365,3321,125.21,29,45,23836,20900,0,checkpoint-1500|checkpoint-1600|checkpoint-1700|checkpoint-1800|checkpoint-1803
256
```

## analysis artifacts present (size + mtime)

*command* (15:33:08):
```powershell
Get-ChildItem 'reports\m3-dpo-resume-watchdog-*' | Sort-Object Name | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize
```

*output* (15:33:08):
```

Name                                           Length LastWriteTime     
----                                           ------ -------------     
m3-dpo-resume-watchdog-A.json                  255531 2026/10/6 15:26:18
m3-dpo-resume-watchdog-A-resume-and-metrics.py  12693 2026/10/6 15:25:47
m3-dpo-resume-watchdog-B-data-identity.json      1007 2026/10/6 15:26:18
m3-dpo-resume-watchdog-B-data-identity.py        4663 2026/10/6 14:05:45
m3-dpo-resume-watchdog-C-ckpt-integrity.json    31692 2026/10/6 15:26:18
m3-dpo-resume-watchdog-C-ckpt-integrity.py       9208 2026/10/6 14:54:27
m3-dpo-resume-watchdog-C-sha-cache.json          4851 2026/10/6 15:26:18
m3-dpo-resume-watchdog-D-config-check.json       4177 2026/10/6 15:26:18
m3-dpo-resume-watchdog-D-config-check.py         4540 2026/10/6 14:06:10
m3-dpo-resume-watchdog-dpo-series.csv           66697 2026/10/6 15:33:05
m3-dpo-resume-watchdog-E-windows.json           28202 2026/10/6 15:26:18
m3-dpo-resume-watchdog-E-windows.py              8168 2026/10/6 14:07:13
m3-dpo-resume-watchdog-F-stdout-series.csv      33451 2026/10/6 15:26:18
m3-dpo-resume-watchdog-F-stdout-series.json      6983 2026/10/6 15:26:18
m3-dpo-resume-watchdog-F-stdout-series.py        9607 2026/10/6 14:18:09
m3-dpo-resume-watchdog-G-stats.json              5688 2026/10/6 15:26:18
m3-dpo-resume-watchdog-G-stats.py                6167 2026/10/6 14:08:42
m3-dpo-resume-watchdog-H-artifacts.json          4372 2026/10/6 15:26:19
m3-dpo-resume-watchdog-H-artifacts.py            6238 2026/10/6 14:45:17
m3-dpo-resume-watchdog-I-rule-and-lambda.json  158912 2026/10/6 15:26:18
m3-dpo-resume-watchdog-I-rule-and-lambda.py     11125 2026/10/6 14:11:15
m3-dpo-resume-watchdog-J-optimizer.json          9182 2026/10/6 15:26:19
m3-dpo-resume-watchdog-J-optimizer.py            7767 2026/10/6 15:26:09
m3-dpo-resume-watchdog-K-report.py             101961 2026/10/6 15:33:02
m3-dpo-resume-watchdog-L-episodes.json           9910 2026/10/6 15:32:05
m3-dpo-resume-watchdog-L-episodes.py             6749 2026/10/6 15:03:00
m3-dpo-resume-watchdog-lint.txt                   787 2026/10/6 15:33:06
m3-dpo-resume-watchdog-M-loss-consistency.json  96274 2026/10/6 15:32:05
m3-dpo-resume-watchdog-M-loss-consistency.py     4155 2026/10/6 14:19:36
m3-dpo-resume-watchdog-N-lint.py                 3026 2026/10/6 15:04:49
m3-dpo-resume-watchdog-O-duration.json           2667 2026/10/6 15:26:41
m3-dpo-resume-watchdog-O-duration.py             5572 2026/10/6 15:26:33
m3-dpo-resume-watchdog-raw.py                    6735 2026/10/6 14:21:43
m3-dpo-resume-watchdog-sampler.ps1               2773 2026/10/6 14:05:24
m3-dpo-resume-watchdog-telemetry.csv            60498 2026/10/6 15:31:07
```

## protocol L: below-reference episodes + distance to the pre-registered early stop

*command* (15:33:08):
```powershell
& "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "reports\m3-dpo-resume-watchdog-L-episodes.py"
```

*output* (15:33:09):
```
points=360 steps 5..1800
episodes of centered5(chosen)<0 : 10
  steps  315-355  ( 9 pts /  45 steps) min_c5=-1.114@335 min_raw=-1.379@325 acc_mean=0.954 acc>=0.97:3/9 | dChosen=-0.120 dRej=-0.145 both_fell=True 
  steps  490-610  (25 pts / 125 steps) min_c5=-2.181@575 min_raw=-3.898@510 acc_mean=0.948 acc>=0.97:7/25 | dChosen=+0.203 dRej=+1.062 both_fell=False 
  steps  810-840  ( 7 pts /  35 steps) min_c5=-0.928@825 min_raw=-1.680@830 acc_mean=0.963 acc>=0.97:2/7 | dChosen=-0.024 dRej=+0.274 both_fell=False 
  steps  850-865  ( 4 pts /  20 steps) min_c5=-0.327@855 min_raw=-1.348@860 acc_mean=0.966 acc>=0.97:2/4 | dChosen=-0.043 dRej=-0.036 both_fell=True 
  steps  950-955  ( 2 pts /  10 steps) min_c5=-0.171@950 min_raw=-0.885@955 acc_mean=0.988 acc>=0.97:2/2 | dChosen=+0.102 dRej=+0.152 both_fell=False 
  steps  965-965  ( 1 pts /   5 steps) min_c5=-0.226@965 min_raw=+0.116@965 acc_mean=0.938 acc>=0.97:0/1 | dChosen=+0.000 dRej=+0.000 both_fell=False 
  steps 1105-1125 ( 5 pts /  25 steps) min_c5=-0.277@1115 min_raw=-0.621@1110 acc_mean=0.935 acc>=0.97:1/5 | dChosen=+0.046 dRej=-0.121 both_fell=False 
  steps 1205-1230 ( 6 pts /  30 steps) min_c5=-0.565@1225 min_raw=-1.205@1220 acc_mean=0.954 acc>=0.97:2/6 | dChosen=-0.091 dRej=-0.438 both_fell=True 
  steps 1240-1295 (12 pts /  60 steps) min_c5=-1.108@1275 min_raw=-1.635@1275 acc_mean=0.951 acc>=0.97:3/12 | dChosen=-0.036 dRej=-0.206 both_fell=True 
  steps 1335-1335 ( 1 pts /   5 steps) min_c5=-0.129@1335 min_raw=-0.010@1335 acc_mean=0.963 acc>=0.97:0/1 | dChosen=+0.000 dRej=+0.000 both_fell=False 

current step 1800: chosen=+0.3426 rejected=-12.4630 acc=0.9375 margins=12.806 lambda=0.1070
  acc>=0.97 consecutive points now = 0 (need 5; short by 5)
  margins vs run start = 359.03x ; margins span ratio over last 5 points = 0.961x (need >2)
  EARLY STOP TRIGGERED = False

worst centered5 chosen = -2.1814 @ step 575
worst raw chosen      = -3.8984 @ step 510
raw chosen<0 points   = 104/360
WROTE J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-L-episodes.json
```

## identity check M: loss >= log2*(1-acc)

*command* (15:33:09):
```powershell
& "J:\Projects\llm_for_sec\.venv\Scripts\python.exe" "reports\m3-dpo-resume-watchdog-M-loss-consistency.py"
```

*output* (15:33:09):
```
identity  loss >= log2*(1-acc) : violations 0/360  -> holds at every logging point
  excess (loss - log2*(1-acc)): min=0.0030 median=0.0730 max=0.3930
  decomposition (mean of first 20 points vs last 20):
    log2*(1-acc)  : 0.0962 -> 0.0316
    excess        : 0.1800 -> 0.0676
  flipped fraction: 0.1387 -> 0.0456
  last 4 points:
    step 1785: loss=0.2605 acc=0.9250 flipped~6.0/80 lower_bound=0.0520 excess=+0.2085
    step 1790: loss=0.0896 acc=0.9500 flipped~4.0/80 lower_bound=0.0347 excess=+0.0549
    step 1795: loss=0.1035 acc=0.9500 flipped~4.0/80 lower_bound=0.0347 excess=+0.0689
    step 1800: loss=0.1124 acc=0.9375 flipped~5.0/80 lower_bound=0.0433 excess=+0.0691
WROTE J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-M-loss-consistency.json
```
