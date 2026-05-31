"""Document content extractors for source snapshots.

Supports: text/html, application/pdf, text/plain

The raw bytes are always the evidence authority.
Extracted text is derived from raw bytes for searching/verification only.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = {"text/html", "application/pdf", "text/plain"}


@dataclass
class ExtractionResult:
    extracted_text: str
    extractor_name: str
    extractor_version: str
    content_type: str
    raw_content_hash: str
    extracted_text_hash: str
    page_count: int | None = None
    extraction_warnings: list[str] = field(default_factory=list)


def extract(raw_bytes: bytes, content_type: str) -> ExtractionResult:
    """Extract text from raw bytes based on content type.

    Args:
        raw_bytes: Raw bytes of the document
        content_type: MIME content type (e.g., "application/pdf")

    Returns:
        ExtractionResult with extracted text and metadata

    Raises:
        ValueError: For unsupported content types
    """
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    base_ct = content_type.split(";")[0].strip().lower()

    if base_ct == "application/pdf":
        return _extract_pdf(raw_bytes, raw_hash, content_type)
    elif base_ct in ("text/html", "application/xhtml+xml"):
        return _extract_html(raw_bytes, raw_hash, content_type)
    elif base_ct == "text/plain":
        return _extract_plain(raw_bytes, raw_hash, content_type)
    else:
        raise ValueError(f"Unsupported content type: {base_ct}")


def _extract_pdf(raw_bytes: bytes, raw_hash: str, content_type: str) -> ExtractionResult:
    warnings = []
    page_count = None
    text = ""
    try:
        import io

        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        page_count = len(reader.pages)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception as e:
                warnings.append(f"Page extraction warning: {e}")
        text = "\n".join(parts)
    except Exception as exc:
        warnings.append(f"PDF extraction failed: {exc}")
        log.warning("PDF extraction failed: %s", exc)

    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ExtractionResult(
        extracted_text=text,
        extractor_name="pypdf",
        extractor_version=_pypdf_version(),
        content_type=content_type,
        raw_content_hash=raw_hash,
        extracted_text_hash=text_hash,
        page_count=page_count,
        extraction_warnings=warnings,
    )


def _extract_html(raw_bytes: bytes, raw_hash: str, content_type: str) -> ExtractionResult:
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self.skip = {"script", "style", "noscript"}
            self.skip_depth = 0

        def handle_starttag(self, tag, attrs):
            if tag in self.skip:
                self.skip_depth += 1

        def handle_endtag(self, tag):
            if tag in self.skip and self.skip_depth > 0:
                self.skip_depth -= 1

        def handle_data(self, data):
            if self.skip_depth == 0:
                self.parts.append(data)

    warnings = []
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=")[-1].split(";")[0].strip()
    try:
        html_text = raw_bytes.decode(charset, errors="replace")
        extractor = TextExtractor()
        extractor.feed(html_text)
        text = " ".join(extractor.parts)
    except Exception as exc:
        warnings.append(f"HTML extraction warning: {exc}")
        text = ""

    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ExtractionResult(
        extracted_text=text,
        extractor_name="html_parser",
        extractor_version="stdlib",
        content_type=content_type,
        raw_content_hash=raw_hash,
        extracted_text_hash=text_hash,
        extraction_warnings=warnings,
    )


def _extract_plain(raw_bytes: bytes, raw_hash: str, content_type: str) -> ExtractionResult:
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=")[-1].split(";")[0].strip()
    text = raw_bytes.decode(charset, errors="replace")
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ExtractionResult(
        extracted_text=text,
        extractor_name="plaintext",
        extractor_version="stdlib",
        content_type=content_type,
        raw_content_hash=raw_hash,
        extracted_text_hash=text_hash,
    )


def _pypdf_version() -> str:
    try:
        import pypdf
        return getattr(pypdf, "__version__", "unknown")
    except ImportError:
        return "not_installed"
