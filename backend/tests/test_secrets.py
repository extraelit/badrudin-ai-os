"""Тесты маскирования секретов (T-1.H1)."""

import logging

from app.core.secrets import SecretMaskingFilter, mask_secret


def test_mask_secret() -> None:
    assert mask_secret("supersecretvalue").startswith("su")
    assert mask_secret("supersecretvalue").endswith("ue")
    assert "*" in mask_secret("supersecretvalue")
    assert mask_secret("") == ""
    assert mask_secret("ab") == "**"


def test_masking_filter_redacts_known_secret(monkeypatch) -> None:
    from app.core import secrets as secrets_mod

    monkeypatch.setattr(secrets_mod, "_secret_values", lambda: ["TOPSECRETKEY"])
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "leaked TOPSECRETKEY here", None, None
    )
    SecretMaskingFilter().filter(record)
    assert "TOPSECRETKEY" not in record.getMessage()
