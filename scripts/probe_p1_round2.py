# -*- coding: utf-8 -*-
"""P1 探测第二轮:修正 URL、抓取小样本结构、重试受阻源。仍是小样本(单 GET,≤128KB)。"""
import base64
import json
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")
UA = "llm-for-sec-research/0.1 (corpus feasibility probe; contact: local-researcher)"


def fetch(url, timeout=20, max_bytes=131072, accept="*/*"):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as r:
            data = r.read(max_bytes)
            return {"url": url, "status": r.status, "ms": int((time.perf_counter() - t0) * 1000),
                    "ctype": r.headers.get("Content-Type", ""), "bytes": len(data), "final_url": r.url, "data": data}
    except urllib.error.HTTPError as e:
        try:
            body = e.read(400)
        except Exception:
            body = b""
        return {"url": url, "status": e.code, "ms": int((time.perf_counter() - t0) * 1000),
                "error": str(e.reason), "data": body}
    except Exception as e:
        return {"url": url, "status": None, "ms": int((time.perf_counter() - t0) * 1000),
                "error": f"{type(e).__name__}: {e}", "data": b""}


def show(r, n=260):
    d = r.pop("data", b"") or b""
    head = d[:n].decode("utf-8", "replace").replace("\n", " ").replace("\r", "")
    r["head"] = head
    return r


TARGETS = [
    # MSRC CVRF v3 —— 服务根已经 200,试实体集与文档
    "https://api.msrc.microsoft.com/cvrf/v3.0/Updates",
    "https://api.msrc.microsoft.com/cvrf/v3.0/Updates?$top=3",
    # Red Hat CSAF 目录(正确 URL,来自官方 security/data 页)
    "https://security.access.redhat.com/data/csaf/v2/advisories/",
    # Debian 正确路径
    "https://www.debian.org/security/2024/dsa-5817",
    "https://www.debian.org/security/",
    "https://lists.debian.org/debian-security-announce/",
    # CTFtime writeup 样本 + 条款页
    "https://ctftime.org/writeup/30768",
    "https://ctftime.org/api/",
    "https://ctftime.org/terms/",
    # Oracle 重试(第一轮超时)
    "https://www.oracle.com/security-alerts/",
    # Project Zero 重试(Atom feed 是入库友好的格式)
    "https://googleprojectzero.blogspot.com/feeds/posts/default?max-results=3",
    "https://project-zero.googlesource.com/0day-in-the-wild/+/master/",
]

results = []
with ThreadPoolExecutor(max_workers=6) as ex:
    for r in ex.map(lambda u: fetch(u), TARGETS):
        results.append(r)
        print(json.dumps(show(r), ensure_ascii=True), flush=True)

# ---- 依赖前面结果的追加探测 ----
# 1. MSRC Updates 样本里若有 CVRF 文档 ID,抓单篇
for r in results:
    if "api.msrc.microsoft.com/cvrf/v3.0/Updates" in r["url"] and r.get("status") == 200:
        try:
            j = json.loads(r.get("data") or b"{}")
        except Exception:
            continue
        break

# 直接单抓一个已知月份文档(v2 时代的模式: cvrf/2016-Feb)
doc = show(fetch("https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/2025-Jan", max_bytes=262144))
print(json.dumps(doc, ensure_ascii=True), flush=True)

# 2. SANS ISC:从 RSS 拿一条 diary 链接再抓
rss = fetch("https://isc.sans.edu/rssfeed.xml")
m = re.search(rb"<link>(https://isc\.sans\.edu/diary/[^<]+)</link>", rss.get("data", b"") or b"")
if m:
    diary_url = m.group(1).decode()
    print(json.dumps(show(fetch(diary_url)), ensure_ascii=True), flush=True)

# 3. MSRC API 文档:api.github.com 取官方仓库 README(base64)
rd = fetch("https://api.github.com/repos/microsoft/MSRC-Microsoft-Security-Updates-API/readme")
if rd.get("status") == 200:
    try:
        j = json.loads(rd["data"])
        txt = base64.b64decode(j["content"]).decode("utf-8", "replace")
        print("MSRC-README-HEAD:", json.dumps(txt[:1500], ensure_ascii=True), flush=True)
    except Exception as e:
        print("MSRC-README-ERR", e)
else:
    print(json.dumps(show(rd), ensure_ascii=True), flush=True)

# 4. GitHub Security Lab:数 _posts 文件数(contents API 单次 GET,目录列表)
posts = fetch("https://api.github.com/repos/github/securitylab/contents/_posts?per_page=100&page=1")
if posts.get("status") == 200:
    try:
        arr = json.loads(posts["data"])
        print("GHSL posts page1 count:", len(arr), "first:", arr[0]["name"], "last:", arr[-1]["name"], flush=True)
    except Exception as e:
        print("GHSL posts parse err", e)
else:
    print(json.dumps(show(posts), ensure_ascii=True), flush=True)
print("DONE2")
