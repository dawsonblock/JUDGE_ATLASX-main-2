"""Content extraction pipeline: text extraction from HTML, PDF, and plain text."""

from __future__ import annotations

import re


def extract_text(content: bytes, content_type: str | None = None) -> str:
    """Extract plain text from *content* bytes.

    Extraction strategy (in priority order):

    1. **PDF** — ``pypdf`` (``PdfReader``).  Falls back to raw byte decode if
       pypdf is not installed or extraction returns empty text.
    2. **HTML** — ``html2text`` for markdown-style text.  Falls back to a
       lightweight regex tag-stripper if html2text is not installed.
    3. **Plain text / unknown** — UTF-8 decode with ``errors='replace'``.

    Args:
        content: Raw bytes to extract text from.
        content_type: MIME type string (e.g. ``"application/pdf"``,
            ``"text/html; charset=utf-8"``).  When *None* the function
            auto-detects based on magic bytes and heuristics.

    Returns:
        Extracted plain text.  Returns empty string on total failure rather
        than raising; callers that need to distinguish empty from error should
        inspect the returned value.
    """
    detected = _detect_content_type(content, content_type)

    if detected == "pdf":
        return _extract_pdf(content)
    if detected == "html":
        return _extract_html(content)
    return _extract_plain(content)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_content_type(content: bytes, hint: str | None) -> str:
    """Return a simplified content-type bucket: 'pdf', 'html', or 'text'."""
    if hint:
        h = hint.lower()
        if "pdf" in h:
            return "pdf"
        if "html" in h or "xml" in h:
            return "html"

    # Magic bytes
    if content[:4] == b"%PDF":
        return "pdf"
    # HTML heuristic: BOM / tag / doctype in the first 512 bytes
    sample = content[:512].lstrip(b"\xef\xbb\xbf \t\n\r")  # strip BOM + whitespace
    if sample.lower().startswith((b"<!doctype", b"<html", b"<head", b"<body")):
        return "html"
    if b"<html" in sample.lower():
        return "html"
    return "text"


def _extract_pdf(content: bytes) -> str:
    """Extract text from PDF bytes using pypdf."""
    try:
        import io

        import pypdf  # type: ignore[import]

        reader = pypdf.PdfReader(io.BytesIO(content))
        parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            parts.append(page_text)
        result = "\n".join(parts).strip()
        if result:
            return result
    except Exception:  # noqa: BLE001
        pass
    # Fallback: decode raw bytes, replacing bad chars
    return content.decode("utf-8", errors="replace")


def _extract_html(content: bytes) -> str:
    """Extract text from HTML bytes using html2text."""
    raw = content.decode("utf-8", errors="replace")
    try:
        import html2text  # type: ignore[import]

        handler = html2text.HTML2Text()
        handler.ignore_links = True
        handler.ignore_images = True
        handler.body_width = 0  # no line wrapping
        return handler.handle(raw).strip()
    except Exception:  # noqa: BLE001
        pass
    # Fallback: strip HTML tags with a lightweight regex
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_plain(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")
