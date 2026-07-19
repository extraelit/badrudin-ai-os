"""Тесты расчётов и правил модуля «Сметы и ценообразование»."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models import (
    DailyReportWorkItem,
    Estimate,
    EstimatePosition,
    Organization,
    PricingSettings,
    Project,
    UnitOfMeasure,
    User,
)
from app.services import estimates as svc


def _base(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Проект")
    db.add(project)
    db.flush()
    unit = UnitOfMeasure(code="м3", name="куб. метр", category="volume")
    db.add(unit)
    db.flush()
    user = User(email=f"u{uuid.uuid4().hex[:6]}@ex.com", password_hash=hash_password("x"))
    db.add(user)
    db.flush()
    return org, project, unit, user


def _estimate(db, org, project, *, number="СМ-1", vat="20", index="1"):
    est = Estimate(
        organization_id=org.id, project_id=project.id, name="Локальная смета",
        number=number, vat_rate=Decimal(vat), base_index=Decimal(index),
    )
    db.add(est)
    db.flush()
    return est


def _pos(db, est, unit, **kw):
    defaults = dict(
        name="Работа", unit_id=unit.id, quantity=Decimal("10"),
        material_unit_cost=Decimal("100"), labor_unit_cost=Decimal("50"),
        machine_unit_cost=Decimal("20"), coefficient=Decimal("1"),
        overhead_percent=Decimal("15"), profit_percent=Decimal("8"),
    )
    defaults.update(kw)
    p = EstimatePosition(estimate_id=est.id, **defaults)
    db.add(p)
    db.flush()
    return p


def test_recalc_totals_with_index_and_vat(db_session) -> None:
    org, project, unit, _ = _base(db_session)
    est = _estimate(db_session, org, project)
    _pos(db_session, est, unit)
    db_session.commit()

    svc.recalc_estimate(db_session, est)

    assert est.material_total == Decimal("1000.00")
    assert est.labor_total == Decimal("500.00")
    assert est.machine_total == Decimal("200.00")
    assert est.direct_total == Decimal("1700.00")
    assert est.overhead_total == Decimal("255.00")
    assert est.profit_total == Decimal("156.40")
    assert est.subtotal == Decimal("2111.40")
    assert est.vat_total == Decimal("422.28")
    assert est.grand_total == Decimal("2533.68")


def test_validate_empty_estimate(db_session) -> None:
    org, project, _, _ = _base(db_session)
    est = _estimate(db_session, org, project)
    db_session.commit()
    with pytest.raises(svc.EstimateValidationError):
        svc.validate_for_approval(db_session, est)


def test_validate_position_without_unit(db_session) -> None:
    org, project, unit, _ = _base(db_session)
    est = _estimate(db_session, org, project)
    _pos(db_session, est, unit, unit_id=None)
    svc.recalc_estimate(db_session, est)
    db_session.commit()
    with pytest.raises(svc.EstimateValidationError):
        svc.validate_for_approval(db_session, est)


def test_approve_and_supersede(db_session) -> None:
    org, project, unit, user = _base(db_session)
    est = _estimate(db_session, org, project)
    _pos(db_session, est, unit)
    db_session.commit()

    svc.approve_estimate(db_session, est, user=user)
    assert est.status == "approved"
    assert est.approval_id is not None

    v2 = svc.create_new_version(db_session, est, user=user, reason="изменение объёмов")
    assert v2.version == 2
    assert v2.status == "draft"
    svc.approve_estimate(db_session, v2, user=user)
    db_session.refresh(est)
    assert est.status == "superseded"
    assert v2.status == "approved"


def test_forbid_edit_approved(db_session) -> None:
    org, project, unit, user = _base(db_session)
    est = _estimate(db_session, org, project)
    _pos(db_session, est, unit)
    db_session.commit()
    svc.approve_estimate(db_session, est, user=user)
    with pytest.raises(svc.EstimateStateError):
        svc.assert_editable(est)


def test_offer_risk_from_org_settings(db_session) -> None:
    org, project, unit, user = _base(db_session)
    # порог организации — низкий, чтобы КП стало R4
    db_session.add(
        PricingSettings(organization_id=org.id, offer_r4_amount_threshold=Decimal("1000"))
    )
    est = _estimate(db_session, org, project)
    _pos(db_session, est, unit)
    db_session.commit()
    svc.approve_estimate(db_session, est, user=user)

    offer = svc.create_offer(db_session, est, user=user, markup_percent=Decimal("10"))
    assert offer.risk_level == "R4"  # 2533.68*1.1 > 1000 → R4 по порогу организации
    assert offer.base_amount == est.grand_total


def test_offer_risk_default_threshold(db_session) -> None:
    org, project, unit, user = _base(db_session)
    est = _estimate(db_session, org, project)
    _pos(db_session, est, unit)
    db_session.commit()
    svc.approve_estimate(db_session, est, user=user)
    offer = svc.create_offer(db_session, est, user=user, markup_percent=Decimal("10"))
    assert offer.risk_level == "R3"  # маленькая сумма, порог по умолчанию 1 млн


def test_plan_fact(db_session) -> None:
    org, project, unit, user = _base(db_session)
    est = _estimate(db_session, org, project)
    pos = _pos(db_session, est, unit)  # qty 10, total 2111.40
    db_session.commit()
    svc.recalc_estimate(db_session, est)
    db_session.commit()
    db_session.add(
        DailyReportWorkItem(
            estimate_position_id=pos.id, project_id=project.id,
            work_date=date(2026, 7, 18), actual_quantity=Decimal("6"),
            verification_status="verified",
        )
    )
    db_session.commit()

    rows = svc.plan_fact(db_session, est)
    assert len(rows) == 1
    r = rows[0]
    assert r.planned_quantity == Decimal("10")
    assert r.actual_quantity == Decimal("6")
    # факт по позиции: 2111.40/10*6 = 1266.84; отклонение отрицательное
    assert r.actual_total == Decimal("1266.84")
    assert r.deviation == Decimal("-844.56")
