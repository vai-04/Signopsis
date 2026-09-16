"""Session-level types."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Mode = Literal["LISTEN", "WATCH", "CONVERSE", "SCREEN"]
SignLang = Literal["isl", "asl"]
AskWhenUnsure = Literal["cautious", "balanced", "fluent"]


class SessionConfig(BaseModel):
    mode: Mode = "LISTEN"
    sign_lang: SignLang = "isl"
    spoken_langs: list[str] = ["en"]
    role: str = "listener"
    ask_when_unsure: AskWhenUnsure = "balanced"
    sign_output: bool = True
    avatar_frames: bool = True
