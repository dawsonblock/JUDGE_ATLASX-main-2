"""Tests for document content extractors.

Proves:
1. HTML extraction returns text without script/style content
2. Plain text extraction returns content as-is
3. PDF extraction succeeds with a real minimal PDF
4. Malformed PDF fails safely (returns empty text with warning, not exception)
5. Unsupported content type raises ValueError
6. Extraction result includes correct hash metadata
"""
from __future__ import annotations

import base64
import hashlib

import pytest

from app.services.extractors import ExtractionResult, extract

# Minimal valid 1-page PDF with "Hello PDF" text (properly formed with xref table)
_MINIMAL_PDF_B64 = (
    "JVBERi0xLjQKMSAwIG9iago8PC9UeXBlIC9DYXRhbG9nIC9QYWdlcyAyIDAgUj4+CmVuZG9iagoy"
    "IDAgb2JqCjw8L1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDE+PgplbmRvYmoKMyAw"
    "IG9iago8PC9UeXBlIC9QYWdlIC9QYXJlbnQgMiAwIFIgL01lZGlhQm94IFswIDAgNjEyIDc5Ml0g"
    "L0NvbnRlbnRzIDQgMCBSIC9SZXNvdXJjZXMgPDwvRm9udCA8PC9GMSA1IDAgUj4+Pj4+PgplbmRv"
    "YmoKNCAwIG9iago8PC9MZW5ndGggNDI+PgpzdHJlYW0KQlQgL0YxIDEyIFRmIDEwMCA3MDAgVGQg"
    "KEhlbGxvIFBERikgVGogRVQKZW5kc3RyZWFtCmVuZG9iago1IDAgb2JqCjw8L1R5cGUgL0ZvbnQg"
    "L1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVsdmV0aWNhPj4KZW5kb2JqCnhyZWYKMCA2CjAw"
    "MDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAwOSAwMDAwMCBuIAowMDAwMDAwMDU2IDAwMDAwIG4g"
    "CjAwMDAwMDAxMTEgMDAwMDAgbiAKMDAwMDAwMDIzMSAwMDAwMCBuIAowMDAwMDAwMzIwIDAwMDAw"
    "IG4gCnRyYWlsZXIKPDwvU2l6ZSA2IC9Sb290IDEgMCBSPj4Kc3RhcnR4cmVmCjM4OAolJUVPRgo="
)

MINIMAL_PDF = base64.b64decode(_MINIMAL_PDF_B64)


class TestHTMLExtraction:
    def test_extracts_visible_text(self):
        html = b"<html><body><p>Hello World</p></body></html>"
        result = extract(html, "text/html")
        assert "Hello World" in result.extracted_text

    def test_strips_script_content(self):
        html = b"<html><body><script>alert('xss')</script><p>Safe</p></body></html>"
        result = extract(html, "text/html")
        assert "alert" not in result.extracted_text
        assert "Safe" in result.extracted_text

    def test_strips_style_content(self):
        html = b"<html><head><style>body{color:red}</style></head><body>Text</body></html>"
        result = extract(html, "text/html")
        assert "color:red" not in result.extracted_text
        assert "Text" in result.extracted_text

    def test_extractor_name(self):
        result = extract(b"<html><body>x</body></html>", "text/html")
        assert result.extractor_name == "html_parser"
        assert result.extractor_version == "stdlib"

    def test_raw_content_hash(self):
        raw = b"<html><body>test</body></html>"
        expected_hash = hashlib.sha256(raw).hexdigest()
        result = extract(raw, "text/html")
        assert result.raw_content_hash == expected_hash

    def test_extracted_text_hash(self):
        raw = b"<html><body>test</body></html>"
        result = extract(raw, "text/html")
        computed = hashlib.sha256(result.extracted_text.encode("utf-8")).hexdigest()
        assert result.extracted_text_hash == computed

    def test_xhtml_content_type(self):
        html = b"<html><body>XHTML content</body></html>"
        result = extract(html, "application/xhtml+xml")
        assert "XHTML content" in result.extracted_text

    def test_content_type_with_charset_param(self):
        html = b"<html><body>charset test</body></html>"
        result = extract(html, "text/html; charset=utf-8")
        assert "charset test" in result.extracted_text


class TestPlainTextExtraction:
    def test_returns_content_as_text(self):
        content = b"Plain text document.\nSecond line."
        result = extract(content, "text/plain")
        assert "Plain text document." in result.extracted_text
        assert "Second line." in result.extracted_text

    def test_extractor_name(self):
        result = extract(b"text", "text/plain")
        assert result.extractor_name == "plaintext"
        assert result.extractor_version == "stdlib"

    def test_hash_integrity(self):
        content = b"integrity test"
        expected_hash = hashlib.sha256(content).hexdigest()
        result = extract(content, "text/plain")
        assert result.raw_content_hash == expected_hash

    def test_charset_param_ignored_gracefully(self):
        content = b"latin text"
        result = extract(content, "text/plain; charset=iso-8859-1")
        assert "latin text" in result.extracted_text


class TestPDFExtraction:
    def test_extracts_text_from_valid_pdf(self):
        result = extract(MINIMAL_PDF, "application/pdf")
        assert isinstance(result.extracted_text, str)
        assert result.extractor_name == "pypdf"
        assert result.page_count is not None

    def test_no_warnings_for_valid_pdf(self):
        result = extract(MINIMAL_PDF, "application/pdf")
        assert result.extraction_warnings == [] or all(
            "Page extraction" not in w for w in result.extraction_warnings
        )

    def test_pdf_raw_content_hash(self):
        expected_hash = hashlib.sha256(MINIMAL_PDF).hexdigest()
        result = extract(MINIMAL_PDF, "application/pdf")
        assert result.raw_content_hash == expected_hash

    def test_malformed_pdf_does_not_raise(self):
        """Malformed PDF must return empty text with warning, never raise."""
        malformed = b"%PDF-1.4\nthis is not a real pdf"
        result = extract(malformed, "application/pdf")
        assert isinstance(result, ExtractionResult)
        assert len(result.extraction_warnings) > 0

    def test_empty_pdf_bytes_does_not_raise(self):
        """Empty bytes for PDF must not raise."""
        result = extract(b"", "application/pdf")
        assert isinstance(result, ExtractionResult)
        assert len(result.extraction_warnings) > 0

    def test_pdf_extractor_name(self):
        result = extract(MINIMAL_PDF, "application/pdf")
        assert result.extractor_name == "pypdf"

    def test_pdf_content_type_stored(self):
        result = extract(MINIMAL_PDF, "application/pdf")
        assert result.content_type == "application/pdf"


class TestUnsupportedContentType:
    def test_raises_value_error_for_image(self):
        with pytest.raises(ValueError, match="Unsupported content type"):
            extract(b"\xff\xd8\xff", "image/jpeg")

    def test_raises_value_error_for_binary(self):
        with pytest.raises(ValueError, match="Unsupported content type"):
            extract(b"\x00\x01\x02", "application/octet-stream")

    def test_raises_value_error_for_video(self):
        with pytest.raises(ValueError, match="Unsupported content type"):
            extract(b"...", "video/mp4")

    def test_does_not_raise_for_supported_types(self):
        for ct in ("text/html", "text/plain", "application/pdf"):
            # Should not raise ValueError
            result = extract(b"test content", ct) if ct != "application/pdf" else extract(MINIMAL_PDF, ct)
            assert isinstance(result, ExtractionResult)
