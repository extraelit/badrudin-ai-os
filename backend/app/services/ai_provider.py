"""Независимый слой сменяемых ИИ-провайдеров (PR-8).

Единый контракт `AIProviderAdapter.generate(...)` поверх разных поставщиков ИИ
(OpenAI, Anthropic, Gemini, локальный OpenAI-совместимый). Бизнес-логика не
привязана к конкретному SDK — вызовы идут через http-транспорт, который
внедряется (тестируемость).

Безопасность (CLAUDE.md §13–15, §19):
- реальные вызовы по умолчанию ВЫКЛЮЧЕНЫ (`settings.ai_real_calls=False`) —
  работает безопасный эхо/заглушка-режим для разработки;
- ключи доступа читаются ТОЛЬКО из окружения, никогда не хранятся в БД и не
  попадают в ответы/журналы (маскируются);
- ИИ формирует только предложения и черновики; окончательные действия — за
  уполномоченным человеком (обеспечивается вышестоящими сервисами).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AgentAIAssignment,
    AIProvider,
    AIProviderHealth,
    AIUsageRecord,
)


@dataclass
class AIUsage:
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class AIResult:
    ok: bool
    text: str = ""
    usage: AIUsage = field(default_factory=AIUsage)
    provider: str = ""
    model: str = ""
    error: str | None = None
    mode: str = "echo"  # echo | real


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mask_secret(value: str | None) -> str:
    """Маскирует секрет для интерфейса/логов (никогда не показываем ключ целиком)."""
    if not value:
        return ""
    if len(value) <= 4:
        return "•" * len(value)
    return f"{value[:2]}{'•' * 6}{value[-2:]}"


class AIProviderAdapter(Protocol):
    code: str

    def available(self) -> bool:
        """Настроен ли ключ провайдера (для реальных вызовов)."""

    def generate(self, *, prompt: str, model: str, params: dict) -> AIResult:
        ...


def _key_for(code: str) -> str:
    s = get_settings()
    return {
        "openai": s.openai_api_key, "anthropic": s.anthropic_api_key,
        "gemini": s.gemini_api_key, "local": s.local_ai_api_key,
    }.get(code, "")


def _base_for(code: str) -> str:
    s = get_settings()
    return {
        "openai": s.openai_base_url, "anthropic": s.anthropic_base_url,
        "gemini": s.gemini_base_url, "local": s.local_ai_base_url,
    }.get(code, "")


class _BaseAdapter:
    """Общая логика: эхо-режим по умолчанию, реальный вызов — через транспорт."""

    code = "base"

    def __init__(self, http_post: Callable[..., dict] | None = None) -> None:
        self._http_post = http_post

    def available(self) -> bool:
        if self.code == "local":
            return bool(get_settings().local_ai_base_url)
        return bool(_key_for(self.code))

    def _echo(self, prompt: str, model: str) -> AIResult:
        text = f"[{self.code}/{model or 'default'} эхо] " + (prompt[:280])
        return AIResult(ok=True, text=text, provider=self.code, model=model,
                        usage=AIUsage(tokens_in=len(prompt.split()),
                                      tokens_out=len(text.split())), mode="echo")

    def _call_real(self, *, prompt: str, model: str, params: dict) -> AIResult:
        raise NotImplementedError

    def generate(self, *, prompt: str, model: str, params: dict) -> AIResult:
        settings = get_settings()
        if not (settings.ai_real_calls and self.available()):
            return self._echo(prompt, model)
        try:
            return self._call_real(prompt=prompt, model=model, params=params)
        except Exception as exc:  # noqa: BLE001 — доменная ошибка вызова ИИ
            return AIResult(ok=False, provider=self.code, model=model,
                            error=str(exc), mode="real")


class OpenAIAdapter(_BaseAdapter):
    code = "openai"

    def _call_real(self, *, prompt, model, params) -> AIResult:
        assert self._http_post is not None
        r = self._http_post(
            f"{_base_for('openai')}/chat/completions", _key_for("openai"),
            {"model": model, "messages": [{"role": "user", "content": prompt}], **params},
        )
        text = r["choices"][0]["message"]["content"]
        u = r.get("usage", {})
        return AIResult(ok=True, text=text, provider="openai", model=model, mode="real",
                        usage=AIUsage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)))


class AnthropicAdapter(_BaseAdapter):
    code = "anthropic"

    def _call_real(self, *, prompt, model, params) -> AIResult:
        assert self._http_post is not None
        r = self._http_post(
            f"{_base_for('anthropic')}/messages", _key_for("anthropic"),
            {"model": model, "max_tokens": params.get("max_tokens", 1024),
             "messages": [{"role": "user", "content": prompt}]},
        )
        text = r["content"][0]["text"]
        u = r.get("usage", {})
        return AIResult(ok=True, text=text, provider="anthropic", model=model, mode="real",
                        usage=AIUsage(u.get("input_tokens", 0), u.get("output_tokens", 0)))


class GeminiAdapter(_BaseAdapter):
    code = "gemini"

    def _call_real(self, *, prompt, model, params) -> AIResult:
        assert self._http_post is not None
        r = self._http_post(
            f"{_base_for('gemini')}/models/{model}:generateContent", _key_for("gemini"),
            {"contents": [{"parts": [{"text": prompt}]}]},
        )
        text = r["candidates"][0]["content"]["parts"][0]["text"]
        u = r.get("usageMetadata", {})
        return AIResult(ok=True, text=text, provider="gemini", model=model, mode="real",
                        usage=AIUsage(u.get("promptTokenCount", 0),
                                      u.get("candidatesTokenCount", 0)))


class LocalOpenAICompatibleAdapter(_BaseAdapter):
    code = "local"

    def _call_real(self, *, prompt, model, params) -> AIResult:
        assert self._http_post is not None
        r = self._http_post(
            f"{_base_for('local')}/chat/completions", _key_for("local"),
            {"model": model, "messages": [{"role": "user", "content": prompt}], **params},
        )
        text = r["choices"][0]["message"]["content"]
        u = r.get("usage", {})
        return AIResult(ok=True, text=text, provider="local", model=model, mode="real",
                        usage=AIUsage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)))


_ADAPTERS: dict[str, Callable[[], AIProviderAdapter]] = {
    "openai": OpenAIAdapter, "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter, "local": LocalOpenAICompatibleAdapter,
}


def get_adapter(code: str) -> AIProviderAdapter:
    factory = _ADAPTERS.get(code)
    if factory is None:
        raise ValueError(f"Неизвестный провайдер: {code}")
    return factory()


# --------------------------- Сервисные операции -------------------------- #

class AIProviderError(Exception):
    """Нарушение правил слоя ИИ-провайдеров."""


def _est_cost(tokens_in: int, tokens_out: int) -> float:
    """Грубая оценка стоимости (демо-тариф); реальные тарифы задаёт заказчик."""
    return round((tokens_in + tokens_out) / 1000.0 * 0.01, 4)


def check_health(session: Session, provider: AIProvider) -> AIProviderHealth:
    """Проверка подключения провайдера (без раскрытия ключа)."""
    adapter = get_adapter(provider.code)
    settings = get_settings()
    if not adapter.available():
        status, detail = "unknown", "ключ не настроен (sandbox/echo)"
    elif not settings.ai_real_calls:
        status, detail = "unknown", "реальные вызовы выключены (ai_real_calls=false)"
    else:
        res = adapter.generate(prompt="ping", model=provider.default_model or "", params={})
        status = "ok" if res.ok else "down"
        detail = None if res.ok else (res.error or "ошибка")
    h = AIProviderHealth(provider_id=provider.id, status=status, checked_at=_now(),
                         detail=detail)
    session.add(h)
    session.flush()
    return h


def run_for_agent(
    session: Session, *, organization_id: uuid.UUID, agent_id: uuid.UUID,
    prompt: str, request_id: str | None = None,
) -> AIResult:
    """Выполняет запрос для агента: основной провайдер, при недоступности — резерв.

    Пишет метаданные расхода (`ai_usage_records`) без промптов и рассуждений.
    """
    assignment = session.scalar(
        select(AgentAIAssignment).where(AgentAIAssignment.agent_id == agent_id)
    )
    params: dict = {}
    if assignment and assignment.max_tokens:
        params["max_tokens"] = assignment.max_tokens
    if assignment and assignment.temperature is not None:
        params["temperature"] = float(assignment.temperature)

    attempts: list[tuple[uuid.UUID | None, str]] = []
    if assignment and assignment.primary_provider_id:
        attempts.append((assignment.primary_provider_id, assignment.primary_model or ""))
    if assignment and assignment.fallback_provider_id:
        attempts.append((assignment.fallback_provider_id, assignment.fallback_model or ""))
    if not attempts:
        raise AIProviderError("Для агента не назначен провайдер ИИ")

    result: AIResult | None = None
    used_provider_id: uuid.UUID | None = None
    for provider_id, model in attempts:
        provider = session.get(AIProvider, provider_id)
        if provider is None or not provider.enabled:
            continue
        adapter = get_adapter(provider.code)
        result = adapter.generate(prompt=prompt, model=model or (provider.default_model or ""),
                                  params=params)
        used_provider_id = provider.id
        if result.ok:
            break  # успех — резерв не нужен

    if result is None:
        raise AIProviderError("Нет доступного провайдера (основной и резервный отключены)")

    session.add(AIUsageRecord(
        organization_id=organization_id, agent_id=agent_id, provider_id=used_provider_id,
        model=result.model, tokens_in=result.usage.tokens_in,
        tokens_out=result.usage.tokens_out,
        cost=_est_cost(result.usage.tokens_in, result.usage.tokens_out),
        request_id=request_id,
    ))
    session.flush()
    return result
