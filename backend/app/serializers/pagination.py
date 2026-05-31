"""Pagination helpers — cursor, offset, and keyset pagination descriptors."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class PageStrategy(str, Enum):
    OFFSET = "offset"
    CURSOR = "cursor"
    KEYSET = "keyset"


@dataclass(frozen=True)
class PageRequest:
    """Describes a pagination request."""

    strategy: PageStrategy = PageStrategy.OFFSET
    page: int = 1  # 1-based; used for OFFSET
    page_size: int = 20
    cursor: Optional[str] = None  # opaque token; used for CURSOR
    sort_field: Optional[str] = None
    sort_asc: bool = True

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.page_size < 1:
            raise ValueError("page_size must be >= 1")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def next_page(self) -> "PageRequest":
        return PageRequest(
            strategy=self.strategy,
            page=self.page + 1,
            page_size=self.page_size,
            sort_field=self.sort_field,
            sort_asc=self.sort_asc,
        )

    def prev_page(self) -> Optional["PageRequest"]:
        if self.page <= 1:
            return None
        return PageRequest(
            strategy=self.strategy,
            page=self.page - 1,
            page_size=self.page_size,
            sort_field=self.sort_field,
            sort_asc=self.sort_asc,
        )


@dataclass
class Cursor:
    """Opaque serialisable cursor for cursor-based pagination."""

    payload: Dict[str, Any] = field(default_factory=dict)

    def encode(self) -> str:
        raw = json.dumps(self.payload, separators=(",", ":"), sort_keys=True)
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @classmethod
    def decode(cls, token: str) -> "Cursor":
        try:
            raw = base64.urlsafe_b64decode(token.encode()).decode()
            payload = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"Invalid cursor token: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Cursor payload must be a JSON object")
        return cls(payload=payload)

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.payload[key] = value


@dataclass
class PageMeta:
    """Metadata about a single page of results."""

    page: int
    page_size: int
    total_items: Optional[int]  # None when unknown (cursor pages)
    has_next: bool
    has_prev: bool
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None

    @property
    def total_pages(self) -> Optional[int]:
        if self.total_items is None:
            return None
        if self.total_items == 0:
            return 1
        return (self.total_items + self.page_size - 1) // self.page_size

    def as_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total_items": self.total_items,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
            "next_cursor": self.next_cursor,
            "prev_cursor": self.prev_cursor,
        }

    @classmethod
    def for_offset(
        cls,
        page: int,
        page_size: int,
        total_items: int,
    ) -> "PageMeta":
        total_pages = (total_items + page_size - 1) // page_size if total_items else 1
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


@dataclass
class Page(Generic[T]):
    """A page of results with associated metadata."""

    items: List[T]
    meta: PageMeta

    def __len__(self) -> int:
        return len(self.items)

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def as_dict(self) -> Dict[str, Any]:
        return {"items": self.items, "meta": self.meta.as_dict()}


__all__ = ["PageStrategy", "PageRequest", "Cursor", "PageMeta", "Page"]
