"""API модуля «Снабжение и закупки».

Backend — единственная точка доступа к данным. Все действия проходят серверную
проверку прав (RBAC) и изоляцию по организации/проекту (ABAC). Согласования —
общий контур `approvals` (R2/R3/R4); заказ/списание уровня R4 требуют MFA.
Складские проводки идемпотентны; все действия — в `audit_events`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import (
    Approval,
    Employee,
    GoodsReceipt,
    GoodsReceiptLine,
    InventoryBalance,
    InventoryCount,
    InventoryCountLine,
    MaterialIssue,
    MaterialIssueLine,
    MaterialRequest,
    MaterialRequestLine,
    MaterialReturn,
    Project,
    PurchaseOrder,
    PurchaseOrderLine,
    QuoteComparison,
    RequestForQuotation,
    RfqLine,
    RfqSupplier,
    Site,
    StockTransfer,
    SupplierItemOffer,
    User,
    Warehouse,
    WriteOffDocument,
)
from app.schemas.procurement import (
    AcknowledgeIn,
    BalanceOut,
    ComparisonOut,
    ConfirmReturnIn,
    CountIn,
    CountOut,
    DecisionIn,
    DocStatusOut,
    IssueDetailOut,
    IssueIn,
    IssueOut,
    IssueRequestIn,
    OfferIn,
    OrderIn,
    OrderOut,
    ProcurementSummary,
    ReceiptIn,
    ReceiptOut,
    RequestDetailOut,
    RequestIn,
    RequestLineOut,
    RequestOut,
    ReserveIn,
    ReturnIn,
    RequestReturnIn,
    ReturnOut,
    RfqIn,
    RfqOut,
    TransferIn,
    WarehouseIn,
    WarehouseOut,
    WriteOffIn,
    WriteOffOut,
)
from app.services import procurement as svc
from app.services.auth import verify_totp

router = APIRouter(prefix="/procurement", tags=["procurement"])


def _org_of(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проект не найден")
    if not svc.can_access(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    return project


def _count_lines(db: Session, model, fk_col, entity_id) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(fk_col == entity_id)) or 0)


# ------------------------------ Справочники ------------------------------ #


@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.view")),
) -> list[WarehouseOut]:
    org = _org_of(db, user)
    rows = db.execute(
        select(Warehouse).where(
            Warehouse.organization_id == org, Warehouse.deleted_at.is_(None)
        )
    ).scalars()
    return [WarehouseOut(id=w.id, name=w.name, code=w.code, site_id=w.site_id, status=w.status) for w in rows]


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> WarehouseOut:
    org = _org_of(db, user)
    w = Warehouse(organization_id=org, name=payload.name, code=payload.code,
                  site_id=payload.site_id, address=payload.address, created_by=user.id)
    db.add(w)
    db.commit()
    return WarehouseOut(id=w.id, name=w.name, code=w.code, site_id=w.site_id, status=w.status)


# ------------------------------- Заявки ---------------------------------- #


def _request_out(db: Session, r: MaterialRequest) -> RequestOut:
    return RequestOut(
        id=r.id, project_id=r.project_id, site_id=r.site_id, task_id=r.task_id,
        number=r.number, status=r.status, priority=r.priority,
        is_critical=r.is_critical, risk_level=r.risk_level, needed_by=r.needed_by,
        approval_id=r.approval_id,
        lines_count=_count_lines(db, MaterialRequestLine, MaterialRequestLine.material_request_id, r.id),
    )


def _get_request(db: Session, user: User, request_id: uuid.UUID) -> MaterialRequest:
    req = db.get(MaterialRequest, request_id)
    if req is None or req.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    _project(db, user, req.project_id)
    return req


@router.get("/projects/{project_id}/requests", response_model=list[RequestOut])
def list_requests(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.view")),
) -> list[RequestOut]:
    _project(db, user, project_id)
    rows = list(
        db.execute(
            select(MaterialRequest).where(
                MaterialRequest.project_id == project_id,
                MaterialRequest.deleted_at.is_(None),
            )
        ).scalars()
    )
    return [_request_out(db, r) for r in rows]


@router.post("/projects/{project_id}/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    project_id: uuid.UUID,
    payload: RequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> RequestOut:
    project = _project(db, user, project_id)
    req = MaterialRequest(
        organization_id=project.organization_id, project_id=project_id,
        site_id=payload.site_id, location_id=payload.location_id,
        task_id=payload.task_id,
        responsible_employee_id=payload.responsible_employee_id, number=payload.number,
        requested_by=user.employee_id, priority=payload.priority,
        is_critical=payload.is_critical, needed_by=payload.needed_by,
        reason=payload.reason, status="draft", created_by=user.id,
    )
    db.add(req)
    db.flush()
    for ln in payload.lines:
        db.add(MaterialRequestLine(
            material_request_id=req.id, material_id=ln.material_id,
            estimate_position_id=ln.estimate_position_id, unit_id=ln.unit_id,
            description=ln.description, quantity=ln.quantity,
        ))
    svc.record_event(db, actor_type="user", action="procurement.request.created",
                     actor_user_id=user.id, organization_id=project.organization_id,
                     entity_type="material_request", entity_id=req.id,
                     new_values={"number": req.number}, commit=False)
    db.commit()
    return _request_out(db, req)


@router.get("/requests/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.view")),
) -> RequestDetailOut:
    req = _get_request(db, user, request_id)
    lines = list(
        db.execute(
            select(MaterialRequestLine).where(
                MaterialRequestLine.material_request_id == req.id
            )
        ).scalars()
    )
    base = _request_out(db, req)
    return RequestDetailOut(
        **base.model_dump(), reason=req.reason, rejection_reason=req.rejection_reason,
        lines=[
            RequestLineOut(
                id=ln.id, material_id=ln.material_id, description=ln.description,
                quantity=str(ln.quantity), reserved_quantity=str(ln.reserved_quantity),
                issued_quantity=str(ln.issued_quantity),
                returned_quantity=str(ln.returned_quantity), status=ln.status,
            )
            for ln in lines
        ],
    )


@router.post("/requests/{request_id}/submit", response_model=RequestOut)
def submit_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> RequestOut:
    req = _get_request(db, user, request_id)
    try:
        svc.submit_request(db, req, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _request_out(db, req)


@router.post("/requests/{request_id}/request-approval", response_model=RequestOut)
def request_request_approval(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> RequestOut:
    req = _get_request(db, user, request_id)
    try:
        svc.request_request_approval(db, req, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _request_out(db, req)


@router.post("/requests/{request_id}/decision", response_model=RequestOut)
def decide_request(
    request_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.approve")),
) -> RequestOut:
    req = _get_request(db, user, request_id)
    mfa_verified = _check_mfa(req.risk_level, payload, user)
    try:
        svc.decide_request(db, req, user=user, decision=payload.decision,
                           comment=payload.comment, mfa_verified=mfa_verified)
    except (svc.ProcurementError, svc.ProcurementAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _request_out(db, req)


@router.post("/requests/{request_id}/approve", response_model=RequestOut)
def approve_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.approve")),
) -> RequestOut:
    """Быстрое согласование заявки уровня R2 (без отдельного шага запроса)."""
    req = _get_request(db, user, request_id)
    try:
        svc.approve_request(db, req, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _request_out(db, req)


@router.post("/requests/{request_id}/reserve", response_model=RequestOut)
def reserve_request(
    request_id: uuid.UUID,
    payload: ReserveIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> RequestOut:
    req = _get_request(db, user, request_id)
    try:
        svc.reserve_request(db, req, warehouse_id=payload.warehouse_id, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _request_out(db, req)


@router.post("/requests/{request_id}/issue", response_model=IssueDetailOut, status_code=status.HTTP_201_CREATED)
def issue_request(
    request_id: uuid.UUID,
    payload: IssueRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> IssueDetailOut:
    req = _get_request(db, user, request_id)
    items = [(it.request_line_id, Decimal(str(it.quantity))) for it in payload.items]
    try:
        iss = svc.issue_request(
            db, req, warehouse_id=payload.warehouse_id, items=items, user=user,
            issued_to=payload.issued_to, number=payload.number,
            evidence_document_id=payload.evidence_document_id,
            evidence_file_id=payload.evidence_file_id,
        )
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return IssueDetailOut(
        id=iss.id, warehouse_id=iss.warehouse_id, material_request_id=iss.material_request_id,
        number=iss.number, status=iss.status, acknowledgement_status=iss.acknowledgement_status,
        acknowledged_by=iss.acknowledged_by,
        lines_count=_count_lines(db, MaterialIssueLine, MaterialIssueLine.material_issue_id, iss.id),
    )


@router.post("/issues/{issue_id}/acknowledge", response_model=IssueDetailOut)
def acknowledge_issue(
    issue_id: uuid.UUID,
    payload: AcknowledgeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> IssueDetailOut:
    iss = db.get(MaterialIssue, issue_id)
    if iss is None or iss.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Выдача не найдена")
    if iss.project_id is not None and not svc.can_access(db, user, iss.project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    try:
        svc.acknowledge_issue(
            db, iss, user=user, employee_id=payload.employee_id,
            confirmed=payload.confirmed, reason=payload.reason,
            evidence_document_id=payload.evidence_document_id,
            evidence_file_id=payload.evidence_file_id,
        )
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return IssueDetailOut(
        id=iss.id, warehouse_id=iss.warehouse_id, material_request_id=iss.material_request_id,
        number=iss.number, status=iss.status, acknowledgement_status=iss.acknowledgement_status,
        acknowledged_by=iss.acknowledged_by,
        lines_count=_count_lines(db, MaterialIssueLine, MaterialIssueLine.material_issue_id, iss.id),
    )


def _return_out(r: MaterialReturn) -> ReturnOut:
    return ReturnOut(
        id=r.id, material_id=r.material_id, quantity=str(r.quantity),
        return_type=r.return_type, status=r.status,
        material_request_id=r.material_request_id, confirmed_by=r.confirmed_by,
    )


@router.post("/requests/{request_id}/return", response_model=ReturnOut, status_code=status.HTTP_201_CREATED)
def return_from_request(
    request_id: uuid.UUID,
    payload: RequestReturnIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> ReturnOut:
    req = _get_request(db, user, request_id)
    try:
        ret = svc.return_from_request(
            db, req, warehouse_id=payload.warehouse_id, material_id=payload.material_id,
            quantity=Decimal(str(payload.quantity)), user=user,
            request_line_id=payload.request_line_id, issue_id=payload.issue_id,
            reason=payload.reason, number=payload.number,
        )
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _return_out(ret)


@router.post("/returns/{return_id}/confirm", response_model=ReturnOut)
def confirm_return(
    return_id: uuid.UUID,
    payload: ConfirmReturnIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> ReturnOut:
    ret = db.get(MaterialReturn, return_id)
    if ret is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Возврат не найден")
    try:
        svc.confirm_return(db, ret, user=user, employee_id=payload.employee_id,
                           evidence_document_id=payload.evidence_document_id)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _return_out(ret)


# --------------------------- Запросы цен (RFQ) --------------------------- #


@router.post("/rfq", response_model=RfqOut, status_code=status.HTTP_201_CREATED)
def create_rfq(
    payload: RfqIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> RfqOut:
    org = _org_of(db, user)
    if payload.project_id is not None:
        _project(db, user, payload.project_id)
    rfq = RequestForQuotation(
        organization_id=org, project_id=payload.project_id,
        material_request_id=payload.material_request_id, number=payload.number,
        due_date=payload.due_date, status="sent", created_by=user.id,
    )
    db.add(rfq)
    db.flush()
    for ln in payload.lines:
        db.add(RfqLine(rfq_id=rfq.id, material_id=ln.material_id, unit_id=ln.unit_id,
                       description=ln.description, quantity=ln.quantity))
    for sid in payload.supplier_ids:
        db.add(RfqSupplier(rfq_id=rfq.id, supplier_id=sid))
    db.commit()
    return RfqOut(id=rfq.id, number=rfq.number, status=rfq.status,
                  lines_count=len(payload.lines), suppliers_count=len(payload.supplier_ids), offers_count=0)


@router.post("/rfq/{rfq_id}/offers", response_model=RfqOut)
def add_offer(
    rfq_id: uuid.UUID,
    payload: OfferIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> RfqOut:
    rfq = db.get(RequestForQuotation, rfq_id)
    if rfq is None or rfq.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запрос цен не найден")
    db.add(SupplierItemOffer(
        rfq_id=rfq_id, rfq_line_id=payload.rfq_line_id, supplier_id=payload.supplier_id,
        supplier_product_id=payload.supplier_product_id, price=payload.price,
        lead_time_days=payload.lead_time_days, note=payload.note,
    ))
    db.commit()
    return RfqOut(
        id=rfq.id, number=rfq.number, status=rfq.status,
        lines_count=_count_lines(db, RfqLine, RfqLine.rfq_id, rfq.id),
        suppliers_count=_count_lines(db, RfqSupplier, RfqSupplier.rfq_id, rfq.id),
        offers_count=_count_lines(db, SupplierItemOffer, SupplierItemOffer.rfq_id, rfq.id),
    )


@router.post("/rfq/{rfq_id}/compare", response_model=ComparisonOut)
def compare_rfq(
    rfq_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> ComparisonOut:
    rfq = db.get(RequestForQuotation, rfq_id)
    if rfq is None or rfq.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запрос цен не найден")
    offers = list(db.execute(select(SupplierItemOffer).where(SupplierItemOffer.rfq_id == rfq_id)).scalars())
    if not offers:
        raise HTTPException(status.HTTP_409_CONFLICT, "Нет предложений для сравнения")
    best = min(offers, key=lambda o: Decimal(o.price))
    org = _org_of(db, user)
    comp = QuoteComparison(
        organization_id=org, project_id=rfq.project_id, rfq_id=rfq_id,
        material_request_id=rfq.material_request_id,
        recommended_supplier_id=best.supplier_id,
        recommended_supplier_product_id=best.supplier_product_id,
        recommendation_reason=f"Минимальная цена {best.price}", approval_status="draft",
        reviewed_by_user_id=user.id,
    )
    db.add(comp)
    rfq.status = "compared"
    db.commit()
    return ComparisonOut(id=comp.id, recommended_supplier_id=comp.recommended_supplier_id,
                         recommendation_reason=comp.recommendation_reason, approval_status=comp.approval_status)


# ------------------------------- Заказы ---------------------------------- #


def _order_out(o: PurchaseOrder) -> OrderOut:
    return OrderOut(id=o.id, supplier_id=o.supplier_id, number=o.number, status=o.status,
                    total_amount=str(o.total_amount), currency=o.currency,
                    risk_level=o.risk_level, approval_id=o.approval_id)


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> OrderOut:
    org = _org_of(db, user)
    if payload.project_id is not None:
        _project(db, user, payload.project_id)
    order = PurchaseOrder(
        organization_id=org, project_id=payload.project_id, supplier_id=payload.supplier_id,
        material_request_id=payload.material_request_id, warehouse_id=payload.warehouse_id,
        number=payload.number, expected_delivery_date=payload.expected_delivery_date,
        status="draft", created_by=user.id,
    )
    db.add(order)
    db.flush()
    for ln in payload.lines:
        db.add(PurchaseOrderLine(
            purchase_order_id=order.id, material_id=ln.material_id,
            estimate_position_id=ln.estimate_position_id, unit_id=ln.unit_id,
            description=ln.description, quantity=ln.quantity, unit_price=ln.unit_price,
        ))
    db.flush()
    svc.recalc_order_total(db, order)
    db.commit()
    return _order_out(order)


@router.post("/orders/{order_id}/request-approval", response_model=OrderOut)
def request_order_approval(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> OrderOut:
    order = db.get(PurchaseOrder, order_id)
    if order is None or order.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заказ не найден")
    try:
        svc.request_order_approval(db, order, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_out(order)


@router.post("/orders/{order_id}/decision", response_model=OrderOut)
def decide_order(
    order_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.approve")),
) -> OrderOut:
    order = db.get(PurchaseOrder, order_id)
    if order is None or order.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заказ не найден")
    mfa_verified = _check_mfa(order.risk_level, payload, user)
    try:
        svc.decide_order(db, order, user=user, decision=payload.decision,
                         comment=payload.comment, mfa_verified=mfa_verified)
    except (svc.ProcurementError, svc.ProcurementAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _order_out(order)


def _check_mfa(risk_level: str, payload: DecisionIn, user: User) -> bool:
    if risk_level == "R4" and payload.decision == "approved":
        if not user.mfa_enabled or not user.mfa_secret or not payload.mfa_code:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Для действия уровня R4 требуется код MFA")
        if not verify_totp(user.mfa_secret, payload.mfa_code):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код MFA")
        return True
    return False


# ---------------------- Поступление и приёмка ---------------------------- #


@router.post("/receipts", response_model=ReceiptOut, status_code=status.HTTP_201_CREATED)
def create_receipt(
    payload: ReceiptIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> ReceiptOut:
    org = _org_of(db, user)
    rec = GoodsReceipt(
        organization_id=org, purchase_order_id=payload.purchase_order_id,
        supplier_id=payload.supplier_id, warehouse_id=payload.warehouse_id,
        number=payload.number, receipt_date=payload.receipt_date,
        delivery_document_number=payload.delivery_document_number, status="draft",
        created_by=user.id,
    )
    db.add(rec)
    db.flush()
    for ln in payload.lines:
        db.add(GoodsReceiptLine(
            goods_receipt_id=rec.id, purchase_order_line_id=ln.purchase_order_line_id,
            material_id=ln.material_id, unit_id=ln.unit_id,
            quantity_received=ln.quantity_received, quantity_accepted=ln.quantity_accepted,
            quantity_rejected=ln.quantity_rejected, quality_status=ln.quality_status,
            certificate_document_id=ln.certificate_document_id, batch_number=ln.batch_number,
        ))
    db.commit()
    return ReceiptOut(id=rec.id, warehouse_id=rec.warehouse_id, number=rec.number,
                      status=rec.status, lines_count=len(payload.lines))


@router.post("/receipts/{receipt_id}/post", response_model=ReceiptOut)
def post_receipt(
    receipt_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> ReceiptOut:
    rec = db.get(GoodsReceipt, receipt_id)
    if rec is None or rec.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Поступление не найдено")
    try:
        svc.post_goods_receipt(db, rec, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ReceiptOut(id=rec.id, warehouse_id=rec.warehouse_id, number=rec.number, status=rec.status,
                      lines_count=_count_lines(db, GoodsReceiptLine, GoodsReceiptLine.goods_receipt_id, rec.id))


# ------------------------------ Выдача ----------------------------------- #


@router.post("/issues", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
def create_issue(
    payload: IssueIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> IssueOut:
    org = _org_of(db, user)
    if payload.project_id is not None:
        _project(db, user, payload.project_id)
    iss = MaterialIssue(
        organization_id=org, project_id=payload.project_id, site_id=payload.site_id,
        warehouse_id=payload.warehouse_id, number=payload.number,
        issue_date=payload.issue_date, issued_to=user.employee_id, status="draft",
        created_by=user.id,
    )
    db.add(iss)
    db.flush()
    for ln in payload.lines:
        db.add(MaterialIssueLine(material_issue_id=iss.id, material_id=ln.material_id,
                                 estimate_position_id=ln.estimate_position_id,
                                 unit_id=ln.unit_id, quantity=ln.quantity))
    db.commit()
    return IssueOut(id=iss.id, warehouse_id=iss.warehouse_id, number=iss.number,
                    status=iss.status, lines_count=len(payload.lines))


@router.post("/issues/{issue_id}/post", response_model=IssueOut)
def post_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> IssueOut:
    iss = db.get(MaterialIssue, issue_id)
    if iss is None or iss.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Выдача не найдена")
    try:
        svc.post_material_issue(db, iss, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return IssueOut(id=iss.id, warehouse_id=iss.warehouse_id, number=iss.number, status=iss.status,
                    lines_count=_count_lines(db, MaterialIssueLine, MaterialIssueLine.material_issue_id, iss.id))


# ------------------------------- Склад ----------------------------------- #


@router.get("/warehouses/{warehouse_id}/balances", response_model=list[BalanceOut])
def list_balances(
    warehouse_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.view")),
) -> list[BalanceOut]:
    # ABAC/тенант-изоляция: склад должен существовать и принадлежать организации
    # пользователя, иначе — 404 (нельзя читать остатки чужого/несуществующего склада).
    org = _org_of(db, user)
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.deleted_at is not None or warehouse.organization_id != org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Склад не найден")
    rows = db.execute(
        select(InventoryBalance).where(InventoryBalance.warehouse_id == warehouse_id)
    ).scalars()
    return [
        BalanceOut(material_id=b.material_id, warehouse_id=b.warehouse_id, quantity=str(b.quantity),
                   reserved_quantity=str(b.reserved_quantity), average_unit_cost=str(b.average_unit_cost))
        for b in rows
    ]


# ------------------- Перемещение, возврат, списание ---------------------- #


@router.post("/transfers", response_model=DocStatusOut, status_code=status.HTTP_201_CREATED)
def create_and_post_transfer(
    payload: TransferIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> DocStatusOut:
    org = _org_of(db, user)
    tr = StockTransfer(organization_id=org, from_warehouse_id=payload.from_warehouse_id,
                       to_warehouse_id=payload.to_warehouse_id, material_id=payload.material_id,
                       quantity=payload.quantity, number=payload.number, status="draft")
    db.add(tr)
    db.flush()
    try:
        svc.post_transfer(db, tr, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return DocStatusOut(id=tr.id, status=tr.status)


@router.post("/returns", response_model=DocStatusOut, status_code=status.HTTP_201_CREATED)
def create_and_post_return(
    payload: ReturnIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> DocStatusOut:
    org = _org_of(db, user)
    ret = MaterialReturn(organization_id=org, warehouse_id=payload.warehouse_id,
                         material_id=payload.material_id, quantity=payload.quantity,
                         return_type=payload.return_type, number=payload.number,
                         reason=payload.reason, status="draft")
    db.add(ret)
    db.flush()
    try:
        svc.post_return(db, ret, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return DocStatusOut(id=ret.id, status=ret.status)


@router.post("/write-offs", response_model=WriteOffOut, status_code=status.HTTP_201_CREATED)
def create_writeoff(
    payload: WriteOffIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> WriteOffOut:
    org = _org_of(db, user)
    wo = WriteOffDocument(organization_id=org, warehouse_id=payload.warehouse_id,
                          material_id=payload.material_id, quantity=payload.quantity,
                          number=payload.number, reason=payload.reason, status="draft",
                          created_by=user.id)
    db.add(wo)
    db.commit()
    return WriteOffOut(id=wo.id, number=wo.number, status=wo.status, risk_level=wo.risk_level, approval_id=wo.approval_id)


@router.post("/write-offs/{wo_id}/request-approval", response_model=WriteOffOut)
def request_writeoff_approval(
    wo_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.manage")),
) -> WriteOffOut:
    wo = db.get(WriteOffDocument, wo_id)
    if wo is None or wo.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Списание не найдено")
    try:
        svc.request_writeoff_approval(db, wo, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return WriteOffOut(id=wo.id, number=wo.number, status=wo.status, risk_level=wo.risk_level, approval_id=wo.approval_id)


@router.post("/write-offs/{wo_id}/decision", response_model=WriteOffOut)
def decide_writeoff(
    wo_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.approve")),
) -> WriteOffOut:
    wo = db.get(WriteOffDocument, wo_id)
    if wo is None or wo.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Списание не найдено")
    mfa_verified = _check_mfa(wo.risk_level, payload, user)
    try:
        svc.decide_writeoff(db, wo, user=user, decision=payload.decision,
                            comment=payload.comment, mfa_verified=mfa_verified)
    except (svc.ProcurementError, svc.ProcurementAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return WriteOffOut(id=wo.id, number=wo.number, status=wo.status, risk_level=wo.risk_level, approval_id=wo.approval_id)


# ---------------------------- Инвентаризация ----------------------------- #


@router.post("/inventory-counts", response_model=CountOut, status_code=status.HTTP_201_CREATED)
def create_count(
    payload: CountIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> CountOut:
    org = _org_of(db, user)
    cnt = InventoryCount(organization_id=org, warehouse_id=payload.warehouse_id,
                         number=payload.number, count_date=payload.count_date,
                         counted_by=user.id, status="counting", created_by=user.id)
    db.add(cnt)
    db.flush()
    for ln in payload.lines:
        db.add(InventoryCountLine(inventory_count_id=cnt.id, material_id=ln.material_id,
                                  expected_quantity=ln.expected_quantity,
                                  counted_quantity=ln.counted_quantity))
    db.commit()
    return CountOut(id=cnt.id, warehouse_id=cnt.warehouse_id, number=cnt.number,
                    status=cnt.status, lines_count=len(payload.lines))


@router.post("/inventory-counts/{count_id}/apply", response_model=CountOut)
def apply_count(
    count_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> CountOut:
    cnt = db.get(InventoryCount, count_id)
    if cnt is None or cnt.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Инвентаризация не найдена")
    try:
        svc.apply_inventory_count(db, cnt, user=user)
    except svc.ProcurementError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return CountOut(id=cnt.id, warehouse_id=cnt.warehouse_id, number=cnt.number, status=cnt.status,
                    lines_count=_count_lines(db, InventoryCountLine, InventoryCountLine.inventory_count_id, cnt.id))


# ------------------------------- Сводка ---------------------------------- #


@router.get("/summary", response_model=ProcurementSummary)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("procurement.view")),
) -> ProcurementSummary:
    org = _org_of(db, user)

    def _cnt(model, *where):
        return int(db.scalar(select(func.count()).select_from(model).where(model.organization_id == org, *where)) or 0)

    return ProcurementSummary(
        requests_open=_cnt(MaterialRequest, MaterialRequest.status.in_(("submitted", "pending_approval", "approved", "reserved", "partially_issued")), MaterialRequest.deleted_at.is_(None)),
        orders_pending=_cnt(PurchaseOrder, PurchaseOrder.status == "pending_approval", PurchaseOrder.deleted_at.is_(None)),
        orders_active=_cnt(PurchaseOrder, PurchaseOrder.status.in_(("approved", "sent", "partially_received")), PurchaseOrder.deleted_at.is_(None)),
        writeoffs_pending=_cnt(WriteOffDocument, WriteOffDocument.status == "pending_approval", WriteOffDocument.deleted_at.is_(None)),
        warehouses=_cnt(Warehouse, Warehouse.deleted_at.is_(None)),
        stock_positions=_cnt(InventoryBalance),
    )
