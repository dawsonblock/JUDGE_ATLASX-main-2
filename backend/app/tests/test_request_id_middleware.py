import re


REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")


def test_request_id_generated_when_missing(client):
    response = client.get("/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert REQUEST_ID_RE.fullmatch(request_id)


def test_request_id_echoes_valid_header(client):
    incoming = "req-abcdef12.ok"
    response = client.get("/health", headers={"X-Request-ID": incoming})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == incoming


def test_request_id_replaces_invalid_header(client):
    incoming = "invalid request id"
    response = client.get("/health", headers={"X-Request-ID": incoming})
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert request_id != incoming
    assert REQUEST_ID_RE.fullmatch(request_id)