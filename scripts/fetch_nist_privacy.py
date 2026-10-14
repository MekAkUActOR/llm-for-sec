"""NIST 隐私/数据分级框架 → C2 隐私知识语料（docs/04 C2 小节）。

来源（美国国家标准技术研究院,美国政府的作品 = 公有领域,17 U.S.C. §105）：
  Privacy Framework 1.0   NIST.CSWP.01162020.pdf（企业隐私风险管理框架）
  SP 800-188              政府数据集去标识化指南（De-Identifying Government
                          Datasets, 2023 final）
  FIPS 199                信息与信息系统的安全定级标准（低/中/高影响）
  SP 800-171r3            保护非联邦系统中的受控未分类信息（CUI）摘要层
  SP 800-53 v5.1 XML      安全与隐私控制目录——仅抽取 AC(访问控制)+SC(系统与
                          通信保护)两族,逐控制一 doc（含控制增强）

通路：nvlpubs.nist.gov / csrc.nist.gov 静态直链,curl.exe 下载;PDF 文本用
pypdf 抽取（2026-09-26 为本任务装入 venv:pip 26.1.2 + pypdf 6.19.0）。

产物：data/corpora/raw/c2-privacy/nist/*.pdf|*.xml（断点续抓）
      data/corpora/clean/c2_privacy_nist.jsonl
manifest：id=nist-privacy

用法：python scripts/fetch_nist_privacy.py [--skip-fetch] [--no-tokens]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402
from fetch_gdpr_full import curl_get  # noqa: E402  (同 curl.exe 引擎)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "corpora" / "raw" / "c2-privacy" / "nist"
UA = "llm-for-sec-c2-privacy/0.1 (privacy corpus research pipeline)"

PDFS = {
    "nist-privacy-framework-v1.0.pdf":
        "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.01162020.pdf",
    "nist-sp800-188-deid.pdf":
        "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-188.pdf",
    "fips-199.pdf":
        "https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.199.pdf",
    "nist-sp800-171r3-cui.pdf":
        "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-171r3.pdf",
}
XML_800_53 = {
    "sp800-53r5-v5.1.xml":
        ("https://csrc.nist.gov/CSRC/media/Projects/risk-management/"
         "800-53%20Downloads/800-53r5/SP_800-53_v5_1_XML.xml"),
}
PDF_DOCS = {
    "nist-privacy-framework-v1.0.pdf": "NIST Privacy Framework 1.0",
    "nist-sp800-188-deid.pdf": "NIST SP 800-188: De-Identifying Government Datasets",
    "fips-199.pdf": "FIPS 199: Standards for Security Categorization of Federal Information and Information Systems",
    "nist-sp800-171r3-cui.pdf": "NIST SP 800-171 Rev 3: Protecting Controlled Unclassified Information in Nonfederal Systems",
}

SPEC = {
    "url": "https://nvlpubs.nist.gov/ + https://csrc.nist.gov/ (SP 800-53 v5.1 XML)",
    "license": "Public domain (works of the U.S. Government, 17 U.S.C. 105)",
    "domain": "privacy",
    "lang": "en",
    "note": ("NIST publications and FIPS are works of the U.S. Government and "
             "therefore public domain under 17 U.S.C. §105 (no domestic "
             "copyright). Includes Privacy Framework 1.0, SP 800-188 "
             "(de-identification), FIPS 199 (security categorization), SP "
             "800-171r3 (CUI), and the AC (Access Control) + SC (System and "
             "Communications Protection) families from the SP 800-53 rev 5.1 "
             "control catalog XML (one document per control, enhancements "
             "included). PDF text extracted with pypdf."),
    "files": ["data/corpora/clean/c2_privacy_nist.jsonl"],
}

_NS = "{http://scap.nist.gov/schema/sp800-53/2.0}"
_WS = re.compile(r"\s+")


# ---------------------------------------------------------------- 转换器（纯函数） --
def pdf_to_text(pdf_bytes: bytes) -> str:
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    for pg in reader.pages:
        try:
            parts.append(pg.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(parts)


def clean_pdf_text(text: str, max_repeat: int = 3) -> str:
    """压 PDF 版式噪声:页码行/重复页眉、过密换行。"""
    lines = [ln.strip() for ln in text.split("\n")]
    out, prev = [], None
    for ln in lines:
        if not ln:
            continue
        if re.fullmatch(r"\d{1,4}", ln):        # 独立页码行
            continue
        if len(ln) < 40 and out and out[-1].endswith(ln):  # 重复页眉
            continue
        if ln == prev:
            continue
        prev = ln
        out.append(ln)
    return "\n".join(out)


def _el_text(el) -> str:
    """元素全部文本（含嵌套 <p>）。"""
    if el is None:
        return ""
    return _WS.sub(" ", "".join(el.itertext())).strip()


def convert_80053_controls(xml_text: str,
                           families: tuple[str, ...] = ("AC", "SC")) -> list[str]:
    """SP 800-53 v5.1 XML → AC/SC 族逐控制 docs。

    根 <controls> 直挂 <control> 元素（族总览项 number='AC'/'SC',基础控制
    number='AC-2',控制增强嵌套为 <control-enhancement> 子元素）。
    """
    root = ET.fromstring(xml_text)
    docs = []
    for ctrl in root:
        num = _el_text(ctrl.find(_NS + "number"))
        fam = num.split("-")[0]
        if fam not in families:
            continue
        title = _el_text(ctrl.find(_NS + "title"))
        statement = _el_text(ctrl.find(_NS + "statement"))
        if not statement:  # 族总览项有时只有 description
            statement = _el_text(ctrl.find(_NS + "description"))
        discussion = _el_text(ctrl.find(_NS + "discussion"))
        parts = [f"NIST SP 800-53 rev 5.1 control {num}: {title}"]
        if statement:
            parts.append(f"Control: {statement}")
        if discussion:
            parts.append(f"Discussion: {discussion}")
        enh_parts = []
        for enh in ctrl.findall(_NS + "control-enhancement"):
            en = _el_text(enh.find(_NS + "number"))
            et = _el_text(enh.find(_NS + "title"))
            es = _el_text(enh.find(_NS + "statement"))
            ed = _el_text(enh.find(_NS + "discussion"))
            seg = f"{en} {et}: {es}"
            if ed:
                seg += f" (Discussion: {ed})"
            enh_parts.append(seg)
        if enh_parts:
            parts.append("Control enhancements: " + " | ".join(enh_parts))
        text = "\n".join(parts)
        if len(text) > 80:
            docs.append(text)
    return docs


def main(argv=None):
    ap = argparse.ArgumentParser(description="NIST privacy frameworks (C2)")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-tokens", action="store_true")
    args = ap.parse_args(argv)

    RAW.mkdir(parents=True, exist_ok=True)
    docs = []

    # PDF 部分
    for fname, url in PDFS.items():
        p = RAW / fname
        if not (p.exists() and p.stat().st_size > 10000):
            if args.skip_fetch:
                print(f"  {fname}: no cache, skip", flush=True)
                continue
            p.write_bytes(curl_get(url))
            time.sleep(0.8)
        text = clean_pdf_text(pdf_to_text(p.read_bytes()))
        head = PDF_DOCS[fname]
        if len(text) > 2000:
            docs.append(f"{head} (full text)\n{text}")
            print(f"  {fname}: {len(text)} chars", flush=True)
        else:
            print(f"  {fname}: EXTRACT TOO SHORT ({len(text)})", flush=True)

    # SP 800-53 XML 部分
    for fname, url in XML_800_53.items():
        p = RAW / fname
        if not (p.exists() and p.stat().st_size > 100000):
            if args.skip_fetch:
                print(f"  {fname}: no cache, skip", flush=True)
                continue
            p.write_bytes(curl_get(url))
        ctrls = convert_80053_controls(p.read_text(encoding="utf-8",
                                                   errors="replace"))
        print(f"  {fname}: {len(ctrls)} AC/SC control docs", flush=True)
        docs.extend(ctrls)

    print(f"nist docs total: {len(docs)}", flush=True)
    out, n = write_clean("c2_privacy_nist", docs)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("nist-privacy", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
