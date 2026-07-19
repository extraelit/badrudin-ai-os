"""Общий контур снабжения и закупок (минимум для переиспользования).

Сущность `quote_comparisons` создаётся один раз здесь (DATABASE.md раздел 14.2)
и используется как источник выбранных/согласованных цен поставщиков. Сметный
модуль читает из неё рекомендованный товар поставщика, но не дублирует её.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class QuoteComparison(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Сравнение коммерческих предложений поставщиков и выбранная цена."""

    __tablename__ = "quote_comparisons"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    # ссылка на исходную заявку (material_requests в MVP-модели отсутствует)
    material_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    comparison_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True
    )
    recommended_supplier_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=True
    )
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # draft | approved | rejected — согласованная цена берётся при approved
    approval_status: Mapped[str] = mapped_column(String(16), default="draft")
