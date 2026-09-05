from dataclasses import dataclass, field
from typing import List, Optional


class ConversionError(Exception):
    """Raised when a board export can't be read or written under the active strictness mode."""


@dataclass
class ChecklistItem:
    text: str
    done: bool = False


@dataclass
class Label:
    name: str
    color: Optional[str] = None  # one of Trello's fixed label colors, or None for colorless


@dataclass
class Card:
    title: str
    description: str = ""
    done: bool = False
    due: Optional[str] = None  # ISO date, e.g. "2026-01-15"
    labels: List[Label] = field(default_factory=list)
    checklist_items: List[ChecklistItem] = field(default_factory=list)


@dataclass
class BoardList:
    name: str
    cards: List[Card] = field(default_factory=list)


@dataclass
class Board:
    name: str
    lists: List[BoardList] = field(default_factory=list)


@dataclass
class Diagnostics:
    """Collects the compromises --lenient mode made: dropped fields, skipped
    archived items, rerouted cards, and the like. Empty in strict mode, since
    anything that would need a note here raises a ConversionError instead."""

    warnings: List[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
