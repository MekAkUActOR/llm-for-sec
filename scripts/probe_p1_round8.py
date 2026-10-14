# -*- coding: utf-8 -*-
"""P1 探测第八轮(许可路径核验):Debian DSA 直页、Cisco CVRF 公共 URL、Oracle 条款逐字提取、RH CSAF 更多年份。"""
import json
import re
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
UA = "llm-for-sec-research/0.1 (corpus feasibility probe)"
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url, timeout=25, max_bytes=131072):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with op.open(req, timeout=timeout) as r:
            return r.status, r.url, r.read(max_bytes)
    except urllib.error.HTTPError as e:
        return e.code, url, b""
    except Exception as e:
        return None, url, str(e).encode()


print("== Debian DSA 直页(不重定向即 www 页,受 Debian WWW License)==", flush=True)
for u in ["https://www.debian.org/security/2024/dsa-5817",
          "https://www.debian.org/security/2025/dsa-5912"]:
    st, fu, d = get(u)
    print(json.dumps({"url": u, "status": st, "final": fu, "bytes": len(d),
                      "is_www": "lists.debian.org" not in fu}), flush=True)

print("== Cisco CVRF/CSAF 匿名 URL 探测 ==", flush=True)
for u in [
    "https://tools.cisco.com/security/center/cvrfListing.x",
    "https://sec.cloudapps.cisco.com/security/center/cvrfListing.x",
    "https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-fmc-xss-mWrGvCTE/csaf/Cisco-SA-fmc-xss-mWrGvCTE.json",
]:
    t0 = time.perf_counter()
    try:
        p = subprocess.run(["curl.exe", "-sS", "--noproxy", "*", "--max-time", "20", "-A", UA,
                            "-o", "NUL", "-w", "%{http_code}|%{size_download}", u],
                           capture_output=True, text=True, timeout=25)
        print(json.dumps({"url": u, "result": p.stdout.strip(), "err": p.stderr.strip()[:100]}), flush=True)
    except Exception as e:
        print(json.dumps({"url": u, "err": str(e)}), flush=True)

print("== Oracle Terms 逐字提取 ==", flush=True)
d = open(r"J:\Projects\llm_for_sec\docs\research\_oracle_terms_sample.html", "rb").read()
t = re.sub(rb"(?is)<script.*?</script>|<style.*?</style>", b" ", d)
t = re.sub(rb"<[^>]+>", b" ", t)
t = b" ".join(t.split()).decode("utf-8", "replace")
# 找产权/许可相关句子
for pat in [r"(?i)(.{0,80}(?:proprietary|ownership|owned by oracle).{0,220})",
            r"(?i)(.{0,80}(?:no license|license is granted|personal (?:and|or) non-?commercial).{0,220})",
            r"(?i)(.{0,60}(?:modif\w+|reproduc\w+|distribut\w+).{0,40}(?:prohibit\w+|not permit\w+).{0,160})",
            r"(?i)(.{0,80}intellectual propert.{0,220})"]:
    m = re.search(pat, t)
    if m:
        print("ORACLE-QUOTE:", json.dumps(m.group(1)[:400]), flush=True)

print("== Red Hat CSAF 早年计数(外推总量)==", flush=True)
for year in ["2005", "2010", "2015", "2018", "2021"]:
    st, fu, d = get(f"https://security.access.redhat.com/data/csaf/v2/advisories/{year}/", max_bytes=8388608)
    if st == 200:
        n = len(set(re.findall(rb'href="rhsa-\d{4}_\d+\.json"', d)))
        tot = len(set(re.findall(rb'href="rh[a-z]+-\d{4}_\d+\.json"', d)))
        print(json.dumps({"year": year, "rhsa": n, "total": tot, "bytes": len(d)}), flush=True)
    else:
        print(json.dumps({"year": year, "status": st}), flush=True)
print("DONE8")
