"""Смоук-тест моделей модуля «Сметы и ценообразование»."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.models import (
    CommercialOffer,
    DailyReportWorkItem,
    Estimate,
    EstimateChange,
    EstimatePosition,
    Organization,
    PricingSettings,
    Project,
    QuoteComparison,
    RateItem,
    UnitOfMeasure,
)


def test_create_estimate_entities(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    project = Project(organization_id=org.id, name="Проект")
    db_session.add(project)
    db_session.flush()

    unit = UnitOfMeasure(code="шт", name="штука", category="piece")
    db_session.add(unit)
    db_session.flush()
    db_session.add(RateItem(organization_id=org.id, code="Р-1", name="Расценка", unit_id=unit.id))
    db_session.add(PricingSettings(organization_id=org.id))
    db_session.add(QuoteComparison(organization_id=org.id, project_id=project.id))

    est = Estimate(organization_id=org.id, project_id=project.id, name="Смета", number="СМ-1")
    db_session.add(est)
    db_session.flush()
    pos = EstimatePosition(estimate_id=est.id, name="Позиция", unit_id=unit.id,
                           quantity=Decimal("5"))
    db_session.add(pos)
    db_session.flush()
    db_session.add(EstimateChange(estimate_id=est.id, change_type="scope", reason="старт"))
    db_session.add(CommercialOffer(organization_id=org.id, project_id=project.id, estimate_id=est.id))
    db_session.add(DailyReportWorkItem(estimate_position_id=pos.id, project_id=project.id,
                                       work_date=date(2026, 7, 18), actual_quantity=Decimal("2")))
    db_session.commit()

    assert db_session.query(Estimate).count() == 1
    assert db_session.query(EstimatePosition).count() == 1
    assert db_session.query(CommercialOffer).count() == 1
    assert db_session.query(DailyReportWorkItem).count() == 1
    assert db_session.query(QuoteComparison).count() == 1
    assert db_session.query(RateItem).count() == 1
