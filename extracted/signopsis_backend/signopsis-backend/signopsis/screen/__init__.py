"""Pipeline E (screen -> sign/voice), rule-based first version.

The client sends a *structural* snapshot of the page (never pixels):
    {"title", "kind", "items": [{"name","qty","price","id"}], "total",
     "actions": [{"label","id","where","primary"}], "private": <count>}
and a question. The answer is short, ordered, action-first, and never offers to press anything.
The GPU build swaps this for a screen-parser model behind the same contract.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

NUM = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


class ScreenItem(BaseModel):
    name: str
    qty: int = 1
    price: float = 0
    id: Optional[str] = None


class ScreenAction(BaseModel):
    label: str
    id: Optional[str] = None
    where: str = "centre"
    primary: bool = False


class ScreenSnapshot(BaseModel):
    title: str = ""
    kind: str = "page"
    items: list[ScreenItem] = []
    total: Optional[float] = None
    actions: list[ScreenAction] = []
    private: int = 0


class ScreenRequest(BaseModel):
    question: str = ""
    intent: Optional[Literal["overview", "items", "checkout", "free"]] = None
    snapshot: ScreenSnapshot = Field(default_factory=ScreenSnapshot)


class Target(BaseModel):
    id: Optional[str]
    label: str


class ScreenAnswer(BaseModel):
    intent: str
    answer: str
    targets: list[Target] = []
    source: str = "server-rules"


def _inr(n: float) -> str:
    n = int(round(n))
    s = str(n)
    if len(s) > 3:                       # Indian grouping: 1,23,456
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"₹{s}"


def _count(n: int) -> str:
    return NUM[n] if n <= 10 else str(n)


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def describe(req: ScreenRequest) -> ScreenAnswer:
    s, q = req.snapshot, req.question.lower()
    intent = req.intent or ("checkout" if re.search(r"checkout|pay|buy", q)
                            else "items" if re.search(r"item|list|read|inside", q) else "overview")
    primary = next((a for a in s.actions if a.primary), s.actions[0] if s.actions else None)
    if intent == "items":
        parts = [f"{f'{i.qty} × ' if i.qty > 1 else ''}{i.name}, {_inr(i.price * i.qty)}" for i in s.items]
        return ScreenAnswer(intent=intent, answer=f"{_cap(_count(len(s.items)))} items. {'. '.join(parts)}.",
                            targets=[Target(id=i.id, label=i.name) for i in s.items])
    if intent == "checkout":
        if not primary:
            return ScreenAnswer(intent=intent, answer="I can't find a checkout button on this page.")
        return ScreenAnswer(intent=intent,
                            answer=f"{primary.label} is at the {primary.where}. Press it when you're ready. I won't press it for you.",
                            targets=[Target(id=primary.id, label=primary.label)])
    total = f", total {_inr(s.total)}" if s.total is not None else ""
    act = f" {primary.label} is a button at the {primary.where}." if primary else ""
    return ScreenAnswer(intent="overview", answer=f"{_cap(s.kind)} page. {_cap(_count(len(s.items)))} items{total}.{act}",
                        targets=[Target(id=primary.id, label=primary.label)] if primary else [])
