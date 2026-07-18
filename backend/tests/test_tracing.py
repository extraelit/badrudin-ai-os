"""Тесты сквозной трассировки correlation_id (T-1.G2)."""


def test_response_has_request_id(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")


def test_incoming_request_id_is_propagated(client) -> None:
    resp = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert resp.headers.get("X-Request-ID") == "trace-abc-123"


def test_error_response_includes_request_id(client) -> None:
    resp = client.get("/no-such", headers={"X-Request-ID": "trace-err"})
    assert resp.json()["error"]["request_id"] == "trace-err"
