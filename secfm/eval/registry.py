"""套件与运行器（docs/01 §5.6 评估即代码）。"""

from __future__ import annotations

from .schema import EvalItem, ResultRecord


class Suite:
    def __init__(self, name, items=()):
        self.name = name
        self.items = list(items)

    def add(self, *items):
        for it in items:
            if not isinstance(it, EvalItem):
                raise TypeError("Suite.add expects EvalItem instances")
        self.items.extend(items)
        return self


def run_suite(suite, judge):
    """judge: Callable[[EvalItem], dict] —— 模型适配器接口。

    judge 返回 {"refusal": bool, "verdict": str|None,
               "confidence": float|None, "text": str}（宽松 schema）。
    """
    return [ResultRecord(item=it, response=judge(it)) for it in suite.items]
