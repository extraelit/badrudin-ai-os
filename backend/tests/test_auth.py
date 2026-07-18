"""Тесты аутентификации: вход, выход, блокировка, отзыв сессии (T-1.C1)."""

from app.core.security import hash_password, verify_password


def test_password_hashing_roundtrip() -> None:
    h = hash_password("Secret123!")
    assert h != "Secret123!"
    assert verify_password("Secret123!", h) is True
    assert verify_password("wrong", h) is False


def test_login_success_and_me(client, seed_user) -> None:
    resp = client.post(
        "/auth/login", json={"email": "foreman@example.com", "password": "Secret123!"}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "foreman@example.com"


def test_login_wrong_password(client, seed_user) -> None:
    resp = client.post(
        "/auth/login", json={"email": "foreman@example.com", "password": "nope"}
    )
    assert resp.status_code == 401


def test_logout_revokes_session(client, seed_user) -> None:
    token = client.post(
        "/auth/login", json={"email": "foreman@example.com", "password": "Secret123!"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 200
    # после выхода токен отозван
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_lockout_after_repeated_failures(client, seed_user) -> None:
    for _ in range(5):
        client.post(
            "/auth/login",
            json={"email": "foreman@example.com", "password": "bad"},
        )
    # даже с верным паролем — заблокировано
    resp = client.post(
        "/auth/login",
        json={"email": "foreman@example.com", "password": "Secret123!"},
    )
    assert resp.status_code == 401
    assert "заблокирован" in resp.json()["detail"].lower()
