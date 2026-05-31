"""Export format descriptors — declare supported output formats and negotiate content."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    TSV = "tsv"
    JSONL = "jsonl"
    XML = "xml"
    MARKDOWN = "markdown"
    TEXT = "text"


# Default MIME types for each format
_DEFAULT_MIME: Dict[ExportFormat, str] = {
    ExportFormat.JSON: "application/json",
    ExportFormat.CSV: "text/csv",
    ExportFormat.TSV: "text/tab-separated-values",
    ExportFormat.JSONL: "application/jsonlines",
    ExportFormat.XML: "application/xml",
    ExportFormat.MARKDOWN: "text/markdown",
    ExportFormat.TEXT: "text/plain",
}

_DEFAULT_EXTENSION: Dict[ExportFormat, str] = {
    ExportFormat.JSON: ".json",
    ExportFormat.CSV: ".csv",
    ExportFormat.TSV: ".tsv",
    ExportFormat.JSONL: ".jsonl",
    ExportFormat.XML: ".xml",
    ExportFormat.MARKDOWN: ".md",
    ExportFormat.TEXT: ".txt",
}


@dataclass(frozen=True)
class FormatDescriptor:
    """Describes a single supported export format."""

    fmt: ExportFormat
    mime_type: str
    extension: str
    streaming: bool = False  # True for formats that support incremental output
    binary: bool = False  # True for binary output formats

    @classmethod
    def for_format(cls, fmt: ExportFormat, **kwargs) -> "FormatDescriptor":
        return cls(
            fmt=fmt,
            mime_type=_DEFAULT_MIME[fmt],
            extension=_DEFAULT_EXTENSION[fmt],
            **kwargs,
        )

    def accepts_mime(self, mime: str) -> bool:
        return mime.lower().strip() == self.mime_type.lower()


@dataclass
class ExportFormatRegistry:
    """Registry of all supported export formats and content-negotiation."""

    _descriptors: Dict[ExportFormat, FormatDescriptor] = field(
        default_factory=dict, init=False
    )

    def register(self, descriptor: FormatDescriptor) -> None:
        self._descriptors[descriptor.fmt] = descriptor

    def unregister(self, fmt: ExportFormat) -> bool:
        if fmt in self._descriptors:
            del self._descriptors[fmt]
            return True
        return False

    def get(self, fmt: ExportFormat) -> Optional[FormatDescriptor]:
        return self._descriptors.get(fmt)

    def supported(self) -> List[ExportFormat]:
        return sorted(self._descriptors.keys(), key=lambda f: f.value)

    def mime_types(self) -> List[str]:
        return [d.mime_type for d in self._descriptors.values()]

    def negotiate(self, accept: str) -> Optional[FormatDescriptor]:
        """Return the descriptor whose mime type matches the Accept header value."""
        normalized = accept.lower().strip()
        for desc in self._descriptors.values():
            if desc.mime_type.lower() == normalized:
                return desc
        return None

    def from_extension(self, ext: str) -> Optional[FormatDescriptor]:
        ext = ext.lower().strip()
        if not ext.startswith("."):
            ext = "." + ext
        for desc in self._descriptors.values():
            if desc.extension == ext:
                return desc
        return None

    def streaming_formats(self) -> List[ExportFormat]:
        return [d.fmt for d in self._descriptors.values() if d.streaming]

    @classmethod
    def with_defaults(cls) -> "ExportFormatRegistry":
        reg = cls()
        for fmt in ExportFormat:
            reg.register(
                FormatDescriptor.for_format(
                    fmt,
                    streaming=fmt in {ExportFormat.JSONL, ExportFormat.CSV},
                )
            )
        return reg


__all__ = ["ExportFormat", "FormatDescriptor", "ExportFormatRegistry"]
