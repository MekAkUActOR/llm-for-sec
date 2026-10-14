"""LOLBAS + GTFOBins 攻击技术参考库（描述级）→ C2 知识语料层。

M1.5 高危操作域的结构化知识：条目 = "某二进制 + 某参数 = 某滥用技术"
（GTFOBins：Unix 合法二进制绕过本地安全限制；LOLBAS：Windows 微软签名
二进制 living-off-the-land 滥用）。含检测 IOC（LOLBAS）——识别导向。

**红线分类（父代理 2026-09-25 指定，与 GHSL SecurityExploits 排除同源
框架）**：攻击模式的描述/分类/技术参考 = OK；可直接投喂的攻击提示词
集合/越狱载荷库 = NO。本二源为描述级参考条目（面向防御者的识别知识，
LOLBAS 条目含 Detection IOC），按父代理判定纳入。

**许可（D3 评审项，均与父代理原口径 "MIT" 不符，已上报）**：
- LOLBAS：GPL-3.0（NOTICE.md："The LOLBAS Project is licensed under
  GPL 3.0."）
- GTFOBins：GPL-3.0（LICENSE 文件全文）

仓库（clone 幂等：已存在即跳过）：
    raw/lolbas  ← https://github.com/LOLBAS-Project/LOLBAS
    raw/gtfobins ← https://github.com/GTFOBins/GTFOBins.github.io
    （GTFOBins 数据仓库已并入 site 仓库，_gtfobins/ 下 478 个无扩展名
     YAML 文件，每二进制一个）

输出：data/corpora/clean/c2_aisafety_lolbas.jsonl / c2_aisafety_gtfo.jsonl
用法：python scripts/fetch_lolbas_gtfo.py [--count]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "corpora" / "raw"
CLEAN = ROOT / "data" / "corpora" / "clean"
MANIFEST = ROOT / "data" / "corpora" / "manifest.jsonl"

REPOS = {
    "lolbas": "https://github.com/LOLBAS-Project/LOLBAS.git",
    "gtfobins": "https://github.com/GTFOBins/GTFOBins.github.io.git",
}

_CTX_DESC = {
    "sudo": "via sudo", "suid": "via SUID bit",
    "capabilities": "via file capabilities", "unprivileged": "unprivileged",
}


def clone_all() -> None:
    for name, url in REPOS.items():
        d = RAW / name
        if (d / ".git").exists():
            print(f"[{name}] 已存在，跳过 clone", flush=True)
            continue
        subprocess.run(["git", "clone", "--depth", "1", url, str(d)],
                       check=True, capture_output=True, timeout=600)
        print(f"[{name}] cloned", flush=True)


def _clean(s: str) -> str:
    return " ".join(s.split())


def convert_gtfobin(name: str, data: dict) -> str:
    """单个 GTFOBins 条目 → 文本。"""
    parts = [f"GTFOBins reference entry: {name}."]
    if data.get("alias"):
        parts.append(f"Aliases: {_clean(str(data['alias']))}.")
    parts.append("GTFOBins documents how legitimate Unix binaries can be "
                 "abused to bypass local security restrictions in "
                 "misconfigured systems.")
    funcs = data.get("functions") or {}
    for fn, variants in funcs.items():
        for v in variants or []:
            code = _clean(v.get("code", ""))
            ctxs = ", ".join(_CTX_DESC.get(c, c)
                             for c in (v.get("contexts") or {}))
            bits = [f"{fn}: {code}"]
            if ctxs:
                bits.append(f"(works {ctxs})")
            if v.get("comment"):
                bits.append(f"Note: {_clean(v['comment'])}")
            parts.append(" ".join(bits) + ".")
    return "\n".join(parts)


def convert_lolbas(data: dict) -> str:
    """单个 LOLBAS 条目 → 文本。"""
    name = data.get("Name", "unknown")
    parts = [f"LOLBAS reference entry: {name}."]
    if data.get("Description"):
        parts.append(_clean(str(data["Description"])) + ".")
    parts.append("LOLBAS documents Microsoft-signed binaries and scripts "
                 "abused in living-off-the-land attacks.")
    for c in data.get("Commands") or []:
        seg = [f"Command: {_clean(str(c.get('Command', '')))}"]
        for k in ("Description", "Usecase", "Category", "Privileges",
                  "MitreID", "OperatingSystem"):
            if c.get(k):
                seg.append(f"{k}: {_clean(str(c[k]))}")
        parts.append("; ".join(seg) + ".")
    for p in data.get("Full_Path") or []:
        if p.get("Path"):
            parts.append(f"Path: {p['Path']}")
    for d in data.get("Detection") or []:
        if d.get("IOC"):
            parts.append(f"Detection IOC: {_clean(str(d['IOC']))}")
    return "\n".join(parts)


def convert_repo(kind: str) -> list[str]:
    """kind='lolbas'|'gtfobins' → 全部条目文本。"""
    docs = []
    if kind == "lolbas":
        for p in sorted((RAW / "lolbas" / "yml").rglob("*.yml")):
            if p.name == "YML-Template.yml":
                continue
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("Name"):
                docs.append(convert_lolbas(data))
    else:
        # 以 git 索引为枚举源：Windows 保留名条目（如 "node"）会被
        # scandir 整个隐藏（实测：磁盘枚举 477 vs git 索引 478），
        # 工作树读取失败时回退 git show 读 blob
        repo = RAW / "gtfobins"
        r = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "_gtfobins"],
            capture_output=True, timeout=60)
        rels = [l.strip() for l in r.stdout.decode().splitlines() if l.strip()]
        print(f"[gtfobins] git 索引 {len(rels)} 条目", flush=True)
        for rel in rels:
            p = repo / rel
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                r2 = subprocess.run(
                    ["git", "-C", str(repo), "show", f"HEAD:{rel}"],
                    capture_output=True, timeout=60)
                if r2.returncode != 0:
                    print(f"    [warn] {rel}: 工作树与 git blob 均不可读",
                          flush=True)
                    continue
                text = r2.stdout.decode("utf-8", "replace")
            try:
                # 文件形如 "---\nfunctions:...\n---\n"（frontmatter）
                texts = [d for d in yaml.safe_load_all(text) if d]
                if not texts:
                    continue
                docs.append(convert_gtfobin(p.name, texts[0]))
            except yaml.YAMLError as e:
                print(f"    [warn] {rel}: YAML 解析失败 {e}", flush=True)
    return docs


def write_jsonl(path: Path, docs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for t in docs:
            f.write(json.dumps({"text": t}, ensure_ascii=True) + "\n")


def upsert_manifest(sid: str, url: str, files: list[str], docs: int,
                    tokens: int, license_: str, domain: str, lang: str,
                    note: str) -> None:
    rows = []
    if MANIFEST.exists():
        rows = [json.loads(l) for l in
                MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("id") != sid]
    rows.append({
        "id": sid, "name": sid, "url": url, "license": license_,
        "tier": "public", "domain": domain, "lang": lang,
        "est_tokens": tokens, "docs": docs, "status": "ingested",
        "ingested_at": time.strftime("%Y-%m-%d"), "files": files,
        "notes": note,
    })
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")


def main():
    ap = argparse.ArgumentParser(description="LOLBAS+GTFOBins → C2 知识层")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--skip-clone", action="store_true")
    args = ap.parse_args()

    if not args.skip_clone:
        clone_all()

    tokens_map = {}
    for kind, out_name, sid, url, license_, note in [
        ("lolbas", "c2_aisafety_lolbas.jsonl", "lolbas",
         "https://github.com/LOLBAS-Project/LOLBAS",
         "GPL-3.0",
         "LOLBAS 攻击技术参考库（描述级，M1.5 高危操作域）。许可："
         "NOTICE.md 逐字 \"The LOLBAS Project is licensed under GPL 3.0.\""
         "（与父代理原口径 MIT 不符，已上报；GPL copyleft → D3 评审项："
         "若开放权重需重估）。红线分类：条目=某二进制+某参数=某滥用技术"
         "的描述 + Detection IOC（识别导向），按父代理 2026-09-25 判定"
         "纳入知识层"),
        ("gtfobins", "c2_aisafety_gtfo.jsonl", "gtfobins",
         "https://github.com/GTFOBins/GTFOBins.github.io",
         "GPL-3.0",
         "GTFOBins 攻击技术参考库（描述级，M1.5 高危操作域；Unix 侧）。"
         "许可：LICENSE 文件为 GPL-3.0 全文（与父代理原口径 MIT 不符，"
         "已上报；GPL copyleft → D3 评审项）。数据仓库已并入 site 仓库"
         "（_gtfobins/ 478 条目）。红线分类同 lolbas：描述级技术参考，"
         "按父代理 2026-09-25 判定纳入"),
    ]:
        docs = convert_repo(kind)
        out = CLEAN / out_name
        write_jsonl(out, docs)
        tokens = 0
        if args.count:
            sys.path.insert(0, str(ROOT / "scripts"))
            from fetch_zhwiki import count_tokens
            tokens = count_tokens(out)
            tokens_map[kind] = tokens
        print(f"[{kind}] {len(docs)} docs, {tokens:,} tokens -> {out.name}",
              flush=True)
        upsert_manifest(sid, url, [str(out.relative_to(ROOT))],
                        len(docs), tokens, license_,
                        "ai_safety", "en", note)
    print("manifest updated", flush=True)


if __name__ == "__main__":
    main()
