"""Тесты складской логики и правил модуля «Снабжение и закупки»."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    InventoryBalance,
    InventoryCount,
    InventoryCountLine,
    MaterialIssue,
    MaterialIssueLine,
    Material,
    Organization,
    ProcurementSettings,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    Counterparty,
    User,
    Warehouse,
)
from app.services import procurement as svc


def _base(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    wh = Warehouse(organization_id=org.id, name="Центральный склад")
    mat = Material(organization_id=org.id, name="Труба ПНД Ø315")
    db.add_all([wh, mat])
    db.flush()
    user = User(email=f"u{uuid.uuid4().hex[:6]}@ex.com", password_hash=hash_password("x"))
    db.add(user)
    db.flush()
    return org, wh, mat, user


def _balance(db, wh, mat):
    return db.execute(
        __import__("sqlalchemy").select(InventoryBalance).where(
            InventoryBalance.warehouse_id == wh.id,
            InventoryBalance.material_id == mat.id,
        )
    ).scalars().first()


def test_post_transaction_and_average_cost(db_session) -> None:
    org, wh, mat, _ = _base(db_session)
    svc.post_transaction(db_session, organization_id=org.id, warehouse_id=wh.id,
                         material_id=mat.id, quantity_signed=Decimal("10"),
                         transaction_type="receipt", unit_cost=Decimal("100"))
    svc.post_transaction(db_session, organization_id=org.id, warehouse_id=wh.id,
                         material_id=mat.id, quantity_signed=Decimal("10"),
                         transaction_type="receipt", unit_cost=Decimal("200"))
    db_session.commit()
    bal = _balance(db_session, wh, mat)
    assert bal.quantity == Decimal("20.000")
    assert bal.average_unit_cost == Decimal("150.00")


def test_insufficient_stock_raises(db_session) -> None:
    org, wh, mat, _ = _base(db_session)
    with pytest.raises(svc.ProcurementError):
        svc.post_transaction(db_session, organization_id=org.id, warehouse_id=wh.id,
                             material_id=mat.id, quantity_signed=Decimal("-5"),
                             transaction_type="issue")


def test_idempotent_no_double_post(db_session) -> None:
    org, wh, mat, _ = _base(db_session)
    key = "receipt:test:1"
    t1 = svc.post_transaction(db_session, organization_id=org.id, warehouse_id=wh.id,
                              material_id=mat.id, quantity_signed=Decimal("10"),
                              transaction_type="receipt", idempotency_key=key)
    db_session.commit()
    t2 = svc.post_transaction(db_session, organization_id=org.id, warehouse_id=wh.id,
                              material_id=mat.id, quantity_signed=Decimal("10"),
                              transaction_type="receipt", idempotency_key=key)
    db_session.commit()
    assert t1 is not None and t2 is None
    assert _balance(db_session, wh, mat).quantity == Decimal("10.000")


def test_settings_default_and_risk(db_session) -> None:
    org, _, _, _ = _base(db_session)
    thr, lines, mfa = svc.get_settings(db_session, org.id)
    assert thr == svc.DEFAULT_R4_AMOUNT and mfa is True
    db_session.add(ProcurementSettings(organization_id=org.id, order_r4_amount_threshold=Decimal("500")))
    db_session.commit()
    thr2, _l, _m = svc.get_settings(db_session, org.id)
    assert thr2 == Decimal("500")
    assert svc.order_risk_level(Decimal("400"), amount_threshold=thr2) == "R3"
    assert svc.order_risk_level(Decimal("600"), amount_threshold=thr2) == "R4"


def test_goods_receipt_over_order_rejected(db_session) -> None:
    org, wh, mat, user = _base(db_session)
    cp = Counterparty(organization_id=org.id, name="Поставщик")
    db_session.add(cp)
    db_session.flush()
    sup = Supplier(counterparty_id=cp.id)
    db_session.add(sup)
    db_session.flush()
    order = PurchaseOrder(organization_id=org.id, supplier_id=sup.id, warehouse_id=wh.id, status="approved")
    db_session.add(order)
    db_session.flush()
    pol = PurchaseOrderLine(purchase_order_id=order.id, material_id=mat.id, quantity=Decimal("10"))
    db_session.add(pol)
    db_session.flush()
    rec = GoodsReceipt(organization_id=org.id, purchase_order_id=order.id, warehouse_id=wh.id, status="draft")
    db_session.add(rec)
    db_session.flush()
    db_session.add(GoodsReceiptLine(goods_receipt_id=rec.id, purchase_order_line_id=pol.id,
                                    material_id=mat.id, quantity_accepted=Decimal("15")))
    db_session.commit()
    with pytest.raises(svc.ProcurementError):
        svc.post_goods_receipt(db_session, rec, user=user)


def test_goods_receipt_posts_stock(db_session) -> None:
    org, wh, mat, user = _base(db_session)
    rec = GoodsReceipt(organization_id=org.id, warehouse_id=wh.id, status="draft")
    db_session.add(rec)
    db_session.flush()
    db_session.add(GoodsReceiptLine(goods_receipt_id=rec.id, material_id=mat.id, quantity_accepted=Decimal("8")))
    db_session.commit()
    svc.post_goods_receipt(db_session, rec, user=user)
    assert rec.status == "posted"
    assert _balance(db_session, wh, mat).quantity == Decimal("8.000")


def test_issue_insufficient_and_ok(db_session) -> None:
    org, wh, mat, user = _base(db_session)
    svc.post_transaction(db_session, organization_id=org.id, warehouse_id=wh.id,
                         material_id=mat.id, quantity_signed=Decimal("5"), transaction_type="receipt")
    db_session.commit()
    iss = MaterialIssue(organization_id=org.id, warehouse_id=wh.id, status="draft")
    db_session.add(iss)
    db_session.flush()
    db_session.add(MaterialIssueLine(material_issue_id=iss.id, material_id=mat.id, quantity=Decimal("10")))
    db_session.commit()
    with pytest.raises(svc.ProcurementError):
        svc.post_material_issue(db_session, iss, user=user)


def test_inventory_count_adjustment(db_session) -> None:
    org, wh, mat, user = _base(db_session)
    svc.post_transaction(db_session, organization_id=org.id, warehouse_id=wh.id,
                         material_id=mat.id, quantity_signed=Decimal("10"), transaction_type="receipt")
    db_session.commit()
    cnt = InventoryCount(organization_id=org.id, warehouse_id=wh.id, status="counting")
    db_session.add(cnt)
    db_session.flush()
    db_session.add(InventoryCountLine(inventory_count_id=cnt.id, material_id=mat.id,
                                      expected_quantity=Decimal("10"), counted_quantity=Decimal("7")))
    db_session.commit()
    svc.apply_inventory_count(db_session, cnt, user=user)
    assert _balance(db_session, wh, mat).quantity == Decimal("7.000")
