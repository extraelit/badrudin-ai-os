"""Модуль «Снабжение и закупки» (MVP) — общий контур снабжения и склада.

Реализует канонический цикл DATABASE.md раздел 33: заявка → запрос цен и
сравнение КП → заказ поставщику → поступление и входной контроль →
оприходование на склад → выдача на объект, с перемещением, возвратом,
списанием и инвентаризацией. Переиспользует существующие сущности без
дублирования: `materials`, `units_of_measure`, `suppliers`, `supplier_products`,
`counterparties`, `quote_comparisons`, `estimate_positions`, `documents`/`files`,
`approvals` (R0–R4), `audit_events`, RBAC/ABAC.

Соответствие §33-канону (алиасы, решение владельца — не создавать дубли):
`materials` ≡ `inventory_items` (§33.3.1); `units_of_measure` ≡
`measurement_units` (§33.3.3). Согласование закупок ведётся общими `approvals`,
а не отдельной `procurement_approvals`. Пороги R3/R4 и MFA — `procurement_settings`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


# ------------------------- Сравнение предложений ------------------------- #


class QuoteComparison(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Сравнение коммерческих предложений поставщиков и выбранная цена (§14.2)."""

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
    material_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    rfq_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    comparison_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True
    )
    recommended_supplier_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=True
    )
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # draft | approved | rejected — согласованная цена берётся при approved
    approval_status: Mapped[str] = mapped_column(String(16), default="draft")


# ------------------------------ Справочники ------------------------------ #


class Warehouse(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Склад (§33.3)."""

    __tablename__ = "warehouses"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")


class WarehouseLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ячейка/зона хранения на складе (§33.3)."""

    __tablename__ = "warehouse_locations"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouse_locations.id"), nullable=True
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))


class ProcurementSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Настройки снабжения организации: пороги R3/R4 и требование MFA."""

    __tablename__ = "procurement_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), unique=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # порог крупной суммы для заказа/списания: >= порога → R4
    order_r4_amount_threshold: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=1000000
    )
    # массовое списание/корректировка (много строк) → R4
    mass_writeoff_lines_threshold: Mapped[int] = mapped_column(Integer, default=50)
    require_mfa_r4: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=false(), nullable=False
    )


# ------------------------------- Заявки ---------------------------------- #


class MaterialRequest(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Заявка на материалы и оборудование (§33.6)."""

    __tablename__ = "material_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_locations.id"), nullable=True
    )
    # задача-основание (§33.6) — заявка по проекту, объекту и задаче
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    # ответственный за исполнение заявки сотрудник
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    # критическая операция → согласование R4 + MFA
    is_critical: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    needed_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # draft | submitted | pending_approval | approved | rejected |
    # reserved | partially_issued | issued | closed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="draft")
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MaterialRequestLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Строка заявки (§33.6). Связь со сметой — проверка «наличие в смете»."""

    __tablename__ = "material_request_lines"

    material_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("material_requests.id")
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    estimate_position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("estimate_positions.id"), nullable=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    # исполнение строки: зарезервировано / выдано / возвращено (частичная выдача)
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    issued_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    returned_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    # open | reserved | partially_issued | issued | rejected | closed
    status: Mapped[str] = mapped_column(String(16), default="open")


# ------------------------- Запросы цен (RFQ) ----------------------------- #


class RequestForQuotation(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Запрос коммерческих предложений (§33.9)."""

    __tablename__ = "requests_for_quotation"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    material_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("material_requests.id"), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # draft | sent | collecting | compared | closed
    status: Mapped[str] = mapped_column(String(16), default="draft")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class RfqLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Позиция запроса цен (§33.9)."""

    __tablename__ = "rfq_lines"

    rfq_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requests_for_quotation.id"))
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)


class RfqSupplier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Поставщик, приглашённый к запросу цен (§33.9)."""

    __tablename__ = "rfq_suppliers"

    rfq_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requests_for_quotation.id"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    # invited | responded | declined
    status: Mapped[str] = mapped_column(String(16), default="invited")


class SupplierItemOffer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ценовое предложение поставщика по позиции (§33.8–33.9)."""

    __tablename__ = "supplier_item_offers"

    rfq_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requests_for_quotation.id"))
    rfq_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rfq_lines.id"), nullable=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    supplier_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


# ------------------------------- Заказы ---------------------------------- #


class PurchaseOrder(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Заказ поставщику (§33.10)."""

    __tablename__ = "purchase_orders"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    material_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("material_requests.id"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouses.id"), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # draft | pending_approval | approved | sent | partially_received |
    # received | closed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="draft")
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )


class PurchaseOrderLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Строка заказа поставщику (§33.10)."""

    __tablename__ = "purchase_order_lines"

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id")
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    estimate_position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("estimate_positions.id"), nullable=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)


class StockReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Резервирование остатка под подтверждённый заказ (§33.7)."""

    __tablename__ = "stock_reservations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouses.id"), nullable=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=True
    )
    material_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("material_requests.id"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    # active | released | consumed
    status: Mapped[str] = mapped_column(String(16), default="active")
    # ручное резервирование склада: кто, до какого срока, причина, снятие
    reserved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reserved_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ------------------- Поступление и входной контроль ---------------------- #


class GoodsReceipt(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Поступление от поставщика (§33.11)."""

    __tablename__ = "goods_receipts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_document_number: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    delivery_note_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    inspected_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # draft | inspected | posted | rejected
    status: Mapped[str] = mapped_column(String(16), default="draft")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class GoodsReceiptLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Строка поступления с входным контролем (§33.11)."""

    __tablename__ = "goods_receipt_lines"

    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goods_receipts.id")
    )
    purchase_order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_order_lines.id"), nullable=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    quantity_accepted: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    quantity_rejected: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    # pending | passed | failed
    quality_status: Mapped[str] = mapped_column(String(16), default="pending")
    certificate_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    batch_number: Mapped[str | None] = mapped_column(String(64), nullable=True)


# --------------------------- Остатки и движения -------------------------- #


class InventoryBalance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Остаток материала на складе (§33.4)."""

    __tablename__ = "inventory_balances"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id", "material_id", "location_id",
            name="inventory_balances_wh_material_loc",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouse_locations.id"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=0)
    reserved_quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=0)
    # точка дозаказа (неснижаемый остаток) — сигнал о низком остатке
    minimum_quantity: Mapped[Decimal] = mapped_column(
        Numeric(16, 3), default=0, server_default=text("0"), nullable=False
    )
    average_unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")


class InventoryTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Движение материала (проводка склада, §33.4). Идемпотентно по ключу."""

    __tablename__ = "inventory_transactions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouse_locations.id"), nullable=True
    )
    # receipt | issue | transfer_in | transfer_out | write_off | adjustment | return
    transaction_type: Mapped[str] = mapped_column(String(16))
    # знаковое количество: приход > 0, расход < 0
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ------------------------------ Выдача ----------------------------------- #


class MaterialIssue(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Выдача материалов в производство/на объект (§33.12)."""

    __tablename__ = "material_issues"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    # заявка-основание выдачи (частичная выдача по заявке)
    material_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("material_requests.id"), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    issued_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    # draft | posted
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # подтверждение получения: pending | confirmed | disputed
    acknowledgement_status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispute_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # доказательства выдачи/получения — существующие documents/files
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class MaterialIssueLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Строка выдачи (§33.12)."""

    __tablename__ = "material_issue_lines"

    material_issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("material_issues.id")
    )
    material_request_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("material_request_lines.id"), nullable=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    estimate_position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("estimate_positions.id"), nullable=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)


# ------------------ Перемещение, возврат, списание ----------------------- #


class StockTransfer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Перемещение между складами (§33.13). Движения — в inventory_transactions."""

    __tablename__ = "stock_transfers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    from_warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    to_warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transfer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # draft | posted
    status: Mapped[str] = mapped_column(String(16), default="draft")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class MaterialReturn(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Возврат материала (с объекта на склад или поставщику, §33.13)."""

    __tablename__ = "material_returns"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    # связь возврата с заявкой и выдачей-основанием
    material_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("material_requests.id"), nullable=True
    )
    material_issue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("material_issues.id"), nullable=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    # from_site | to_supplier
    return_type: Mapped[str] = mapped_column(String(16), default="from_site")
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # draft | posted | confirmed
    status: Mapped[str] = mapped_column(String(16), default="draft")
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )


class WriteOffDocument(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Списание материалов (§33.13). Требует согласования (R3/R4)."""

    __tablename__ = "write_off_documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    # draft | pending_approval | approved | posted | rejected
    status: Mapped[str] = mapped_column(String(20), default="draft")
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )


# ---------------------------- Инвентаризация ----------------------------- #


class InventoryCount(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Инвентаризация склада (§33.14)."""

    __tablename__ = "inventory_counts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"))
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    count_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    counted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # draft | counting | completed | posted
    status: Mapped[str] = mapped_column(String(16), default="draft")


class InventoryCountLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Строка инвентаризации: ожидаемое и фактическое количество (§33.14)."""

    __tablename__ = "inventory_count_lines"

    inventory_count_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_counts.id")
    )
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.id"))
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=0)
    counted_quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=0)
    difference_quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), default=0)
