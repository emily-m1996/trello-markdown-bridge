from dataclasses import dataclass, field
from typing import List, Optional


class ConversionError(Exception):
    """Raised when a board export can't be read or written under the active strictness mode."""


@dataclass
class Card:
    title: str
    description: str = ""
    done: bool = False
    due: Optional[str] = None  # ISO date, e.g. "2026-01-15"
    labels: List[str] = field(default_factory=list)


@dataclass
class BoardList:
    name: str
    cards: List[Card] = field(default_factory=list)


@dataclass
class Board:
    name: str
    lists: List[BoardList] = field(default_factory=list)
