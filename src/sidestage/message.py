from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sidestage.character import Character


@dataclass
class Message:
    sender: Character
    body: str
