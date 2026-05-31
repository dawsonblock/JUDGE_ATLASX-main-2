"""Tests for StatsCan ingestion helpers — extract_csv_from_response."""

import io
import zipfile

import pytest

from app.ingestion.crime_sources.statscan import extract_csv_from_bytes, extract_csv_from_response


class FakeResponse:
    """Minimal httpx.Response stand-in for testing."""

    def __init__(self, content: bytes, text: str = ""):
        self.content = content
        self.text = text


def _make_zip_bytes(filename: str, csv_text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, csv_text)
    return buf.getvalue()


class TestExtractCsvFromResponse:
    def test_plain_text_response_returned_as_is(self):
        csv_text = "col1,col2\nval1,val2\n"
        resp = FakeResponse(content=csv_text.encode("utf-8"), text=csv_text)
        assert extract_csv_from_response(resp) == csv_text

    def test_zip_with_single_csv_extracted(self):
        csv_text = "year,count\n2023,42\n"
        content = _make_zip_bytes("data.csv", csv_text)
        resp = FakeResponse(content=content)
        result = extract_csv_from_response(resp)
        assert result == csv_text

    def test_zip_with_multiple_csvs_returns_first_sorted(self):
        csv_a = "a,b\n1,2\n"
        csv_b = "x,y\n9,8\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("zzz.csv", csv_b)
            zf.writestr("aaa.csv", csv_a)
        content = buf.getvalue()
        resp = FakeResponse(content=content)
        result = extract_csv_from_response(resp)
        # sorted([zzz.csv, aaa.csv])[0] == aaa.csv
        assert result == csv_a

    def test_zip_with_no_csv_returns_none(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "nothing here")
        resp = FakeResponse(content=buf.getvalue())
        assert extract_csv_from_response(resp) is None

    def test_zip_csv_decoded_utf8_sig(self):
        csv_text = "col\nval\n"
        raw = csv_text.encode("utf-8-sig")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("data.csv", raw)
        resp = FakeResponse(content=buf.getvalue())
        result = extract_csv_from_response(resp)
        # BOM stripped by utf-8-sig decode
        assert "col" in result

    def test_zip_csv_decoded_latin1_fallback(self):
        # latin-1 byte that is invalid utf-8
        csv_text_bytes = b"col\ncaf\xe9\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("data.csv", csv_text_bytes)
        resp = FakeResponse(content=buf.getvalue())
        result = extract_csv_from_response(resp)
        assert result is not None
        assert "caf" in result


# ---------------------------------------------------------------------------
# extract_csv_from_bytes — direct bytes API (no httpx dependency)
# ---------------------------------------------------------------------------


class TestExtractCsvFromBytes:
    def test_plain_utf8_bytes(self):
        csv_text = "col1,col2\nval1,val2\n"
        result = extract_csv_from_bytes(csv_text.encode("utf-8"))
        assert result == csv_text

    def test_plain_utf8_sig_bom_stripped(self):
        csv_text = "col\nval\n"
        result = extract_csv_from_bytes(csv_text.encode("utf-8-sig"))
        assert result == csv_text

    def test_zip_with_single_csv_extracted(self):
        csv_text = "year,count\n2023,42\n"
        result = extract_csv_from_bytes(_make_zip_bytes("data.csv", csv_text))
        assert result == csv_text

    def test_zip_with_no_csv_returns_none(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "nothing here")
        assert extract_csv_from_bytes(buf.getvalue()) is None

    def test_zip_returns_first_alphabetically(self):
        csv_a = "a,b\n1,2\n"
        csv_z = "z,y\n9,8\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("zzz.csv", csv_z)
            zf.writestr("aaa.csv", csv_a)
        assert extract_csv_from_bytes(buf.getvalue()) == csv_a
