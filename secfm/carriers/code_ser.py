"""代码载体序列化（docs/01 §2.4）：路径 + 语言 + 依赖清单 + 代码体。"""

from __future__ import annotations

import os

from .base import CarrierBlock

_LANG = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".jsx": "javascript",
    ".tsx": "typescript", ".java": "java", ".c": "c", ".h": "c", ".cc": "c++",
    ".cpp": "c++", ".hpp": "c++", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".php": "php", ".sh": "shell", ".bash": "shell", ".sql": "sql",
    ".html": "html", ".htm": "html", ".css": "css", ".kt": "kotlin",
    ".swift": "swift", ".cs": "c#", ".m": "objc", ".pl": "perl",
    ".lua": "lua", ".vue": "vue", ".yml": "yaml", ".yaml": "yaml", ".json": "json",
}


def serialize_code(code, *, path, deps=None, deps_source="manifest",
                   cid="c1", body_limit=20000) -> CarrierBlock:
    lang = _LANG.get(os.path.splitext(path)[1].lower(), "unknown")
    meta = [f"path: {path}", f"language: {lang}"]
    if deps:
        shown = ", ".join(str(d) for d in deps[:5])
        more = f" … (+{len(deps) - 5})" if len(deps) > 5 else ""
        meta.append(f"deps: {shown}{more} ({len(deps)} total) [source: {deps_source}]")
    body = code
    if len(body) > body_limit:
        body = body[:body_limit] + f"\n[truncated: {len(code) - body_limit} chars omitted]"
    return CarrierBlock(ctype="code", cid=cid, meta_lines=meta, body=body)
