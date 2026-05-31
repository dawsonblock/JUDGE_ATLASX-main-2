import pytest

from app.orchestration.task_registry import _validate_url


def test_https_url_is_allowed():
    _validate_url("https://laws-lois.justice.gc.ca/eng/acts/C-46/")


def test_http_url_is_rejected_by_default():
    with pytest.raises(ValueError, match="URL scheme 'http' not allowed"):
        _validate_url("http://laws-lois.justice.gc.ca/eng/acts/C-46/")


def test_non_allowlisted_https_domain_is_rejected():
    with pytest.raises(ValueError, match="not in allowlist"):
        _validate_url("https://example.com")


def test_file_url_is_rejected():
    with pytest.raises(ValueError, match="URL scheme 'file' not allowed"):
        _validate_url("file:///etc/passwd")