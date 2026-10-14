# -*- coding: utf-8 -*-
"""P1 探测第七轮(最终):MSRC 单文档全尺寸、GHSL advisories 计数、github.blog 可达性、ISC diary 单篇字数。"""
import json
import re
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
UA = "llm-for-sec-research/0.1 (corpus feasibility probe)"


def curl_bytes(url, timeout=90):
    t0 = time.perf_counter()
    p = subprocess.run(["curl.exe", "-sSL", "--noproxy", "*", "--max-time", str(timeout), "-A", UA,
                        "-o", "NUL", "-w", "%{http_code}|%{size_download}|%{time_total}", url],
                       capture_output=True, text=True, timeout=timeout + 10)
    return {"url": url, "result": p.stdout.strip(), "ms": int((time.perf_counter() - t0) * 1000)}


print("== MSRC CVRF 单文档全尺寸(GET,仅落 NUL)==", flush=True)
for yid in ["2010-Jan", "2015-Jan", "2020-Jan", "2025-Jan", "2026-Sep"]:
    print(json.dumps(curl_bytes(f"https://api.msrc.microsoft.com/cvrf/v3.0/cvrf/{yid}")), flush=True)

print("== GHSL advisories 计数 ==", flush=True)
req = urllib.request.Request("https://securitylab.github.com/advisories/", headers={"User-Agent": UA})
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with op.open(req, timeout=30) as r:
    d = r.read(4 * 1024 * 1024).decode("utf-8", "replace")
ids = set(re.findall(r"GHSL-(20\d\d)-(\d+)", d))
years = {}
for y, n in ids:
    years[y] = years.get(y, 0) + 1
print("GHSL advisory ids on page:", len(ids), "per year:", dict(sorted(years.items())), flush=True)

print("== github.blog 可达性(GHSL 文章现址)==", flush=True)
print(json.dumps(curl_bytes("https://github.blog/security/")), flush=True)

print("== ISC diary 单篇正文字数样本 ==", flush=True)
req = urllib.request.Request("https://isc.sans.edu/diary/33366", headers={"User-Agent": UA})
with op.open(req, timeout=30) as r:
    d = r.read(262144)
t = re.sub(rb"(?is)<script.*?</script>|<style.*?</style>", b" ", d)
t = re.sub(rb"<[^>]+>", b" ", t)
t = b" ".join(t.split())
print("diary 33366 html:", len(d), "text chars:", len(t), flush=True)

print("== 0day-RCAs 目录(P0 团队 RCA writeup)==", flush=True)
req = urllib.request.Request("https://api.github.com/repos/googleprojectzero/0days-in-the-wild/contents/0day-RCAs",
                             headers={"User-Agent": UA})
with op.open(req, timeout=30) as r:
    arr = json.loads(r.read())
print("0day-RCAs entries:", len(arr), [a["name"] for a in arr[:6]], flush=True)
print("DONE7")
