"""M0 审计用合成安全语料生成（确定性、可复现）。

docs/02 §2：真实语料入库前，先用合成语料获得第一手 fertility 读数；
真实语料入库后用同一工具重跑对比。所有生成器以固定种子驱动。

baseline_mix 为中英自然文本混合（自撰段落池循环），代表"自然文本"
的 bytes/token 参照；其余组为安全语料的典型形态。
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import sys
from pathlib import Path

_ZH_PARAS = [
    "威胁情报的日常工作中，分析师需要把来自不同渠道的原始报告整理成结构化的判断。"
    "一条情报的价值不在于它描述了多少技术细节，而在于它能否回答三个问题："
    "谁在行动、通过什么途径、对什么资产构成影响。",
    "城市轨道交通的信号系统在设计时就考虑了冗余：两条独立的供电线路、"
    "三套互为备份的控制器，以及一套完全不依赖外部网络的人工调度流程。"
    "冗余的价值在日常运营中几乎看不见，只有在故障发生的那一刻才体现出来。",
    "软件补丁的管理常常被简化为技术问题，但它本质上是风险管理问题。"
    "每一次升级都引入变更，而变更本身就是事故的来源之一。"
    "成熟的团队会问的不是要不要打补丁，而是不打补丁的暴露窗口有多长。",
    "密码学的教材通常从替换密码讲起，因为历史足够悠久，例子也足够直观。"
    "但从教学效果看，真正让初学者理解 Kerckhoffs 原则的，"
    "往往是那些系统保密性依赖算法保密而最终失败的历史案例。",
    "一个日志系统的可靠性取决于它最脆弱的环节。如果采集端可以丢数据，"
    "那么存储端再健壮也无济于事。审计日志的特殊之处在于："
    "它的消费者常常在事件发生数月之后才需要它，而那时记忆已经不可靠了。",
]

_EN_PARAS = [
    "In day-to-day threat intelligence work, an analyst turns raw reports from "
    "disparate sources into structured judgments. The value of a report lies not "
    "in the volume of technical detail it carries, but in whether it answers "
    "three questions: who is acting, through what vector, and against which assets.",
    "Urban rail signaling systems are designed with redundancy in mind: two "
    "independent power feeds, three mutually backing controllers, and a manual "
    "dispatching procedure that works without any network at all. The value of "
    "redundancy is invisible in daily operation; it shows up only at the moment "
    "a fault actually happens.",
    "Patch management is often framed as a technical task, but it is fundamentally "
    "a risk-management problem. Every upgrade introduces change, and change is "
    "itself a source of incidents. Mature teams do not ask whether to patch; they "
    "ask how long the exposure window is if they do not.",
    "Cryptography textbooks usually begin with substitution ciphers, mostly because "
    "the history is long and the examples are intuitive. What actually teaches a "
    "beginner Kerckhoffs's principle, though, is the long list of systems whose "
    "secrecy depended on keeping the algorithm secret, and which failed because "
    "of exactly that.",
    "The reliability of a logging pipeline is set by its weakest stage. If the "
    "collection agent may drop records, no amount of storage robustness will "
    "save the audit trail. Audit logs are special: their consumers often need "
    "them months after the fact, when human memory has already decayed.",
]


def gen_baseline_mix(target, rng):
    out, n, i = [], 0, 0
    while n < target:
        para = (_ZH_PARAS if i % 2 == 0 else _EN_PARAS)[(i // 2) % 5]
        out.append(para)
        n += len(para.encode("utf-8")) + 2
        i += 1
    return "\n\n".join(out)


def gen_hex(target, rng):
    out, n = [], 0
    while n < target:
        addr = (n // 79) * 16
        bs = [rng.randrange(256) for _ in range(16)]
        hexs = " ".join(f"{x:02x}" for x in bs)
        asc = "".join(chr(x) if 32 <= x < 127 else "." for x in bs)
        line = f"{addr:08x}  {hexs}  |{asc}|"
        out.append(line)
        n += len(line) + 1
    return "\n".join(out)


def gen_base64(target, rng):
    out, n = [], 0
    while n < target:
        raw = bytes(rng.randrange(256) for _ in range(192))
        enc = base64.b64encode(raw).decode()
        block = "\n".join(enc[i:i + 76] for i in range(0, len(enc), 76))
        out.append(block)
        n += len(block) + 2
    return "\n\n".join(out)


_CVE_PRODS = ["curl", "openssl", "linux-kernel", "chromium", "nginx", "ffmpeg",
              "libpng", "openssh", "sqlite", "webkitgtk", "php", "bind"]
_CVE_DESCS = [
    "heap buffer overflow in protocol parser",
    "use-after-free in session teardown",
    "out-of-bounds read via crafted DNS response",
    "stack exhaustion through deeply nested structures",
    "integer overflow leading to heap corruption",
    "NULL pointer dereference in error path",
    "type confusion in scripting bridge",
    "race condition in file descriptor handling",
]


def gen_cve_ids(target, rng):
    out, n = [], 0
    while n < target:
        year = rng.randrange(1999, 2027)
        cve = f"CVE-{year}-{rng.randrange(1000, 99999):05d}"
        line = (f"{cve} {rng.choice(_CVE_PRODS)}: {rng.choice(_CVE_DESCS)} "
                f"(CVSS {rng.uniform(1, 10):.1f})")
        out.append(line)
        n += len(line) + 1
    return "\n".join(out)


_SYSLOG_TMPL = [
    "Failed password for {u} from {ip} port {p} ssh2",
    "Accepted publickey for {u} from {ip} port {p} ssh2: RSA SHA256:{h}",
    "kernel: [UFW BLOCK] IN=eth0 SRC={ip} DST=10.0.0.5 PROTO=TCP SPT={p} DPT={dp}",
    "CRON[{pid}]: (root) CMD (/usr/local/bin/backup.sh)",
    "systemd[1]: Started Daily apt upgrade and clean activities.",
    "postfix/smtpd[{pid}]: NOQUEUE: reject: RCPT from unknown[{ip}]: 554 5.7.1",
]
_USERS = ["root", "admin", "ubuntu", "git", "deploy", "oracle"]


def gen_syslog(target, rng):
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    hosts = ["web01", "db02", "auth", "mail", "edge"]
    out, n = [], 0
    while n < target:
        ip = f"192.0.2.{rng.randrange(1, 254)}"
        t = _SYSLOG_TMPL[rng.randrange(len(_SYSLOG_TMPL))]
        msg = t.format(u=rng.choice(_USERS), ip=ip, p=rng.randrange(1024, 65535),
                       dp=rng.choice([22, 80, 443, 3389, 5432]),
                       h="".join(rng.choice("abcdef0123456789") for _ in range(43)),
                       pid=rng.randrange(100, 99999))
        ts = (f"{months[rng.randrange(12)]} {rng.randrange(1, 29):02d} "
              f"{rng.randrange(24):02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}")
        line = f"{ts} {rng.choice(hosts)} {msg}"
        out.append(line)
        n += len(line) + 1
    return "\n".join(out)


def gen_json_logs(target, rng):
    levels = ["INFO", "WARN", "ERROR", "DEBUG"]
    services = ["auth", "api-gateway", "billing", "session", "upload"]
    msgs = ["login failed", "token refreshed", "rate limit exceeded",
            "upstream timeout", "suspicious user-agent", "certificate expiring"]
    out, n = [], 0
    while n < target:
        rec = {
            "ts": f"2026-09-{rng.randrange(1, 29):02d}T{rng.randrange(24):02d}:"
                  f"{rng.randrange(60):02d}:{rng.randrange(60):02d}Z",
            "level": rng.choice(levels),
            "service": rng.choice(services),
            "msg": rng.choice(msgs),
            "src_ip": f"203.0.113.{rng.randrange(1, 254)}",
            "attempt": rng.randrange(1, 50),
            "latency_ms": round(rng.uniform(0.5, 900), 1),
        }
        line = json.dumps(rec, separators=(",", ":"))
        out.append(line)
        n += len(line) + 1
    return "\n".join(out)


def gen_obfuscated_js(target, rng):
    out, n = [], 0
    while n < target:
        fn = "_0x" + f"{rng.randrange(16 ** 4):04x}"
        hexstr = "".join(f"\\x{x:02x}"
                         for x in bytes(rng.randrange(97, 123) for _ in range(12)))
        extra = "".join(rng.choice("0123456789abcdef") for _ in range(24))
        line = (f"function {fn}(){{var {fn}={hexstr};"
                f"return atob({fn}+'{extra}');}}eval({fn}());")
        out.append(line)
        n += len(line) + 1
    return "\n".join(out)


_C_SNIPPET = """static int parse_hdr(const char *buf, size_t len) {
    struct hdr *h = (struct hdr *)buf;
    if (len < sizeof(*h)) return -1;
    uint32_t off = h->offset;            /* attacker controlled */
    if (off + h->size > len) return -1;  /* integer overflow: off+size can wrap */
    memcpy(h->dst, buf + off, h->size);
    return 0;
}"""


def gen_c_code(target, rng):
    out, n = [], 0
    i = 0
    while n < target:
        i += 1
        snippet = _C_SNIPPET.replace("parse_hdr", f"parse_hdr_{i}")
        out.append(snippet)
        n += len(snippet) + 2
    return "\n\n".join(out)


_SH_SNIPPET = """#!/usr/bin/env bash
set -euo pipefail
for f in "$@"; do
  sha256sum "$f" >> checksums.txt
done
curl -fsSL https://example.internal/bootstrap.sh | bash"""


def gen_shell(target, rng):
    out, n = [], 0
    i = 0
    while n < target:
        i += 1
        snippet = _SH_SNIPPET.replace("checksums.txt", f"checksums_{i}.txt")
        out.append(snippet)
        n += len(snippet) + 2
    return "\n\n".join(out)


GENERATORS = {
    "baseline_mix": gen_baseline_mix,
    "hex_dump": gen_hex,
    "base64": gen_base64,
    "cve_ids": gen_cve_ids,
    "logs_syslog": gen_syslog,
    "logs_json": gen_json_logs,
    "obfuscated_js": gen_obfuscated_js,
    "c_code": gen_c_code,
    "shell": gen_shell,
}


def build_all(target_bytes=65536, seed=42):
    """生成全部语料组：{名称: 文本}。"""
    return {name: gen(target_bytes, random.Random(seed))
            for name, gen in GENERATORS.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description="合成安全语料生成（fertility 审计用）")
    ap.add_argument("--out", required=True, help="输出目录（每组一个 .txt）")
    ap.add_argument("--size", type=int, default=65536, help="每组目标字节数")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in build_all(args.size, args.seed).items():
        (out / f"{name}.txt").write_text(text, encoding="utf-8", newline="\n")
        print(f"  {name}.txt  {len(text.encode('utf-8')):,} bytes")
    print(f"完成 -> {out}")


if __name__ == "__main__":
    sys.exit(main())
