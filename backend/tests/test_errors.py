"""Тесты единого формата ошибок (T-1.G1)."""


def test_not_found_uniform_error(client) -> None:
    resp = client.get("/no-such-endpoint")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "not_found"
    assert "message" in body["error"]
    assert "request_id" in body["error"]


def test_validation_uniform_error(client) -> None:
    resp = client.post("/auth/login", json={"email": "not-an-email"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
    # детали валидации не раскрывают внутреннюю структуру
    assert isinstance(body["error"]["message"], str)
