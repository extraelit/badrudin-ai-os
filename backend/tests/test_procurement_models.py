"""Смоук-тест моделей модуля «Снабжение и закупки»."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models import (
    Counterparty,
    GoodsReceipt,
    GoodsReceiptLine,
    InventoryBalance,
    InventoryCount,
    InventoryCountLine,
    InventoryTransaction,
    Material,
    MaterialIssue,
    MaterialIssueLine,
    MaterialRequest,
    MaterialRequestLine,
    MaterialReturn,
    Organization,
    ProcurementSettings,
    Project,
    PurchaseOrder,
    PurchaseOrderLine,
    RequestForQuotation,
    RfqLine,
    RfqSupplier,
    StockReservation,
    StockTransfer,
    Supplier,
    SupplierItemOffer,
    Warehouse,
    WarehouseLocation,
    WriteOffDocument,
)


def test_create_procurement_entities(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    project = Project(organization_id=org.id, name="Проект")
    wh = Warehouse(organization_id=org.id, name="Склад")
    mat = Material(organization_id=org.id, name="Труба")
    cp = Counterparty(organization_id=org.id, name="Поставщик")
    db_session.add_all([project, wh, mat, cp])
    db_session.flush()
    loc = WarehouseLocation(warehouse_id=wh.id, name="Стеллаж A")
    sup = Supplier(counterparty_id=cp.id)
    db_session.add_all([loc, sup, ProcurementSettings(organization_id=org.id)])
    db_session.flush()

    req = MaterialRequest(organization_id=org.id, project_id=project.id)
    db_session.add(req)
    db_session.flush()
    db_session.add(MaterialRequestLine(material_request_id=req.id, material_id=mat.id, quantity=Decimal("5")))

    rfq = RequestForQuotation(organization_id=org.id, project_id=project.id)
    db_session.add(rfq)
    db_session.flush()
    db_session.add(RfqLine(rfq_id=rfq.id, material_id=mat.id, quantity=Decimal("5")))
    db_session.add(RfqSupplier(rfq_id=rfq.id, supplier_id=sup.id))
    db_session.add(SupplierItemOffer(rfq_id=rfq.id, supplier_id=sup.id, price=Decimal("100")))

    order = PurchaseOrder(organization_id=org.id, supplier_id=sup.id, warehouse_id=wh.id)
    db_session.add(order)
    db_session.flush()
    db_session.add(PurchaseOrderLine(purchase_order_id=order.id, material_id=mat.id, quantity=Decimal("5")))
    db_session.add(StockReservation(organization_id=org.id, warehouse_id=wh.id, material_id=mat.id, quantity=Decimal("5")))

    rec = GoodsReceipt(organization_id=org.id, warehouse_id=wh.id)
    db_session.add(rec)
    db_session.flush()
    db_session.add(GoodsReceiptLine(goods_receipt_id=rec.id, material_id=mat.id, quantity_accepted=Decimal("5")))

    db_session.add(InventoryBalance(organization_id=org.id, warehouse_id=wh.id, material_id=mat.id, quantity=Decimal("5")))
    db_session.add(InventoryTransaction(organization_id=org.id, warehouse_id=wh.id, material_id=mat.id,
                                        transaction_type="receipt", quantity=Decimal("5")))
    iss = MaterialIssue(organization_id=org.id, warehouse_id=wh.id)
    db_session.add(iss)
    db_session.flush()
    db_session.add(MaterialIssueLine(material_issue_id=iss.id, material_id=mat.id, quantity=Decimal("2")))
    db_session.add(StockTransfer(organization_id=org.id, from_warehouse_id=wh.id, to_warehouse_id=wh.id, material_id=mat.id, quantity=Decimal("1")))
    db_session.add(MaterialReturn(organization_id=org.id, warehouse_id=wh.id, material_id=mat.id, quantity=Decimal("1")))
    db_session.add(WriteOffDocument(organization_id=org.id, warehouse_id=wh.id, material_id=mat.id, quantity=Decimal("1"), reason="брак"))
    cnt = InventoryCount(organization_id=org.id, warehouse_id=wh.id)
    db_session.add(cnt)
    db_session.flush()
    db_session.add(InventoryCountLine(inventory_count_id=cnt.id, material_id=mat.id, expected_quantity=Decimal("5"), counted_quantity=Decimal("4")))
    db_session.commit()

    assert db_session.query(MaterialRequest).count() == 1
    assert db_session.query(PurchaseOrder).count() == 1
    assert db_session.query(GoodsReceipt).count() == 1
    assert db_session.query(InventoryTransaction).count() == 1
    assert db_session.query(WriteOffDocument).count() == 1
    assert db_session.query(InventoryCountLine).count() == 1
