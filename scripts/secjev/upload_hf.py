# -*- coding: utf-8 -*-
"""sec-jev HF 上传（私有仓库 llm-for-sec-secjev）。

布局：
  仓库根   = 合并自包含模型（model.safetensors + head.pt + slots.json + tokenizer
             + render_eval.py + README.md 模型卡）
  adapter-r1/ = r1 LoRA + head + slots
  adapter-r2/ = r2 LoRA + head + slots
凭证：环境变量 HF_TOKEN（写权限；不落盘）。
"""
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(r"J:\Projects\llm_for_sec")
REPO = "howwhenRaw/llm-for-sec-secjev"  # whoami 实测：token 属主命名空间
MERGED = ROOT / "checkpoints" / "secjev-0.6b-r1-merged"
R1 = ROOT / "checkpoints" / "secjev-0.6b-r1"
R2 = ROOT / "checkpoints" / "secjev-0.6b-r2"

token = os.environ.get("HF_TOKEN")
if not token:
    sys.exit("缺 HF_TOKEN 环境变量（写权限 token）")
api = HfApi(token=token)
who = api.whoami()
print(f"登录身份: {who['name']} (orgs: {[o.get('name') for o in who.get('orgs', [])]})")
url = api.create_repo(repo_id=REPO, private=True, exist_ok=True)
print(f"repo: {url}")

# 根：合并模型 + 卡 + shim（README 用上传目录里的）
for f in MERGED.iterdir():
    if f.name == "README.md":
        continue
    api.upload_file(path_or_fileobj=str(f), path_in_repo=f.name, repo_id=REPO)
    print(f"  root/{f.name} ({f.stat().st_size/1e6:.1f}MB) 上传完成")
api.upload_file(path_or_fileobj=str(MERGED / "README.md"), path_in_repo="README.md", repo_id=REPO)
print("  root/README.md 上传完成")
api.upload_file(path_or_fileobj=str(ROOT / "scripts" / "secjev" / "render_eval.py"),
                path_in_repo="render_eval.py", repo_id=REPO)
print("  root/render_eval.py 上传完成")

# adapter 子目录
for tag, src in (("adapter-r1", R1), ("adapter-r2", R2)):
    for f in (src / "adapter").iterdir():
        api.upload_file(path_or_fileobj=str(f), path_in_repo=f"{tag}/{f.name}", repo_id=REPO)
    for name in ("head.pt", "slots.json"):
        api.upload_file(path_or_fileobj=str(src / name), path_in_repo=f"{tag}/{name}", repo_id=REPO)
    print(f"  {tag}/ 上传完成")

files = api.list_repo_files(repo_id=REPO)
print(f"UPLOAD-SECJEV=OK repo={REPO} files={len(files)}")
for f in files:
    print("  ", f)
