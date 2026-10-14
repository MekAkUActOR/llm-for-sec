# -*- coding: utf-8 -*-
"""P1 探测第三轮:目录结构、规模计数、curl.exe 交叉验证、条款页抓取保存。仍是小样本。"""
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")
UA = "llm-for-sec-research/0.1 (corpus feasibility probe; contact: local-researcher)"


def fetch(url, timeout=20, max_bytes=262144):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
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


def curl_probe(url, timeout=25):
    """curl.exe(schannel TLS 栈)交叉验证,--noproxy 全禁代理,只取头部与少量正文"""
    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            ["curl.exe", "-sS", "--noproxy", "*", "-o", "NUL", "-w",
             "%{http_code}|%{time_total}|%{size_download}|%{content_type}",
             "--max-time", str(timeout), "-A", UA, "-r", "0-65535", url],
            capture_output=True, text=True, timeout=timeout + 5)
        out = p.stdout.strip()
        err = p.stderr.strip()
        return {"url": url, "via": "curl.exe", "ms": int((time.perf_counter() - t0) * 1000),
                "result": out if out else None, "stderr": err[:200] if err else ""}
    except Exception as e:
        return {"url": url, "via": "curl.exe", "ms": int((time.perf_counter() - t0) * 1000),
                "error": f"{type(e).__name__}: {e}"}


TASKS_URLS = [
    # GHSL 仓库结构(默认分支、目录)
    "https://api.github.com/repos/github/securitylab",
    "https://api.github.com/repos/github/securitylab/contents/?ref=main",
    # Project Zero 官方 GitHub 组织(本网络 github.com 可达)
    "https://api.github.com/orgs/googleprojectzero/repos?per_page=100&page=1",
    # CTFtime:writeup 高位 ID 探测 + 主页(找 ToS 链接)
    "https://ctftime.org/writeup/40000",
    "https://ctftime.org/writeup/25000",
    # Debian security tracker
    "https://security-tracker.debian.org/tracker/",
    # Debian DSA 邮件归档某年索引(计数用)
    "https://lists.debian.org/debian-security-announce/2025/",
]

results = {}
with ThreadPoolExecutor(max_workers=6) as ex:
    for r in ex.map(fetch, TASKS_URLS):
        results[r["url"]] = r
        d = r.pop("data", b"")
        r["head"] = d[:200].decode("utf-8", "replace").replace("\n", " ")
        print(json.dumps(r, ensure_ascii=True), flush=True)
        r["_data"] = d

# ---- 解析型小任务 ----
# 1. GHSL 根目录:找文章目录
root = results.get("https://api.github.com/repos/github/securitylab/contents/?ref=main", {})
if root.get("status") == 200:
    try:
        arr = json.loads(root["_data"])
        print("GHSL root entries:", json.dumps([a["name"] for a in arr], ensure_ascii=True), flush=True)
    except Exception as e:
        print("GHSL root parse err", e)

# 2. googleprojectzero 组织仓库清单
org = results.get("https://api.github.com/orgs/googleprojectzero/repos?per_page=100&page=1", {})
if org.get("status") == 200:
    try:
        arr = json.loads(org["_data"])
        print("P0 GitHub repos:", json.dumps([a["name"] for a in arr], ensure_ascii=True), flush=True)
    except Exception as e:
        print("P0 org parse err", e)

# 3. CTFtime 主页找条款链接
home = fetch("https://ctftime.org/", max_bytes=131072)
if home.get("status") == 200:
    links = re.findall(rb'href="(/[a-zA-Z0-9_\-/\.]*)">(?:Terms|terms|Rules|rules|About|about|License|license|Legal|legal)', home["data"])
    print("CTFtime legal links:", json.dumps([l.decode() for l in set(links)]), flush=True)
    footer = re.search(rb"(?is)<footer.*?</footer>", home["data"])
    if footer:
        ft = re.sub(rb"<[^>]+>", b" ", footer.group(0))
        print("CTFtime footer text:", json.dumps(b" ".join(ft.split())[:400].decode("utf-8", "replace")), flush=True)

# 4. Debian 2025 年 DSA 数量
y = results.get("https://lists.debian.org/debian-security-announce/2025/", {})
if y.get("status") == 200:
    n = len(re.findall(rb"msg\d+\.html", y["_data"]))
    print("Debian dsa-announce 2025 msgs:", n, flush=True)

# 5. Red Hat CSAF 目录结构(子目录/年份?)——拉全目录页解析
csaf = fetch("https://security.access.redhat.com/data/csaf/v2/advisories/", max_bytes=1048576)
if csaf.get("status") == 200:
    hrefs = re.findall(rb'href="([^"]+)"', csaf["data"])
    print("CSAF dir entries sample:", json.dumps([h.decode() for h in hrefs[2:14]]), flush=True)
    print("CSAF dir entry count on page:", len(hrefs) - 2, "total bytes:", csaf["bytes"], flush=True)
    # 若有年份子目录,测一个
    subs = [h.decode() for h in hrefs if re.match(r"\d{4}/?$|rhba-|rhsa-", h.decode())]
    if subs:
        sub_url = "https://security.access.redhat.com/data/csaf/v2/advisories/" + subs[0].lstrip("/")
        s = fetch(sub_url, max_bytes=65536)
        print("CSAF subdir probe:", json.dumps({"url": sub_url, "status": s.get("status"),
                                                "entries": len(re.findall(rb'href="([^"]+\.json)"', s.get("data", b"")))}), flush=True)

# 6. MSRC Updates 分页结构:解析 @odata.nextLink(不跟随,只确认模式)
msrc = fetch("https://api.msrc.microsoft.com/cvrf/v3.0/Updates", max_bytes=262144)
if msrc.get("status") == 200:
    try:
        j = json.loads(msrc["data"])
        vals = j.get("value", [])
        print("MSRC Updates page1 entries:", len(vals),
              "first:", vals[0]["ID"] if vals else None,
              "last:", vals[-1]["ID"] if vals else None, flush=True)
        print("MSRC nextLink:", j.get("@odata.nextLink", "(none)"), flush=True)
    except Exception as e:
        print("MSRC parse err", e)

# 7. curl.exe 交叉验证 Oracle / blogspot / googlesource
for u in ["https://www.oracle.com/security-alerts/",
          "https://googleprojectzero.blogspot.com/",
          "https://project-zero.googlesource.com/0day-in-the-wild/+/master/"]:
    print(json.dumps(curl_probe(u), ensure_ascii=True), flush=True)

# 8. Oracle 条款页(慢,但上轮成功过)——保存本地供逐字引用
terms = fetch("https://www.oracle.com/legal/terms/", timeout=60, max_bytes=524288)
if terms.get("status") == 200:
    with open(r"J:\Projects\llm_for_sec\docs\research\_oracle_terms_sample.html", "wb") as f:
        f.write(terms["data"])
    txt = re.sub(rb"(?is)<script.*?</script>|<style.*?</style>", b" ", terms["data"])
    txt = re.sub(rb"<[^>]+>", b" ", txt)
    txt = b" ".join(txt.split())
    m = re.search(rb"(?i)(?:proprietar\w+|ownership|license.{0,200}site|content.{0,100}owned)", txt)
    print("ORACLE TERMS saved bytes:", terms["bytes"], "ms:", terms["ms"], flush=True)
    print("ORACLE TERMS snippet:", json.dumps(txt[:600].decode("utf-8", "replace")), flush=True)
else:
    print("ORACLE TERMS fetch failed:", json.dumps({k: v for k, v in terms.items() if k != "data"}), flush=True)
print("DONE3")
