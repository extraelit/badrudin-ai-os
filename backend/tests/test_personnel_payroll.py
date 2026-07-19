"""Тесты расчёта начислений и уровня риска выплат (модуль «Персонал объектов»)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.models import Organization, PayrollDraft, PayrollLine, Site
from app.services import personnel as svc


def test_compute_line_precise() -> None:
    accrued, to_pay = svc.compute_line(
        rate="420.00", quantity="122", advance="15000", deduction="0"
    )
    assert accrued == Decimal("51240.00")
    assert to_pay == Decimal("36240.00")


def test_compute_line_piece_rate_rounding() -> None:
    # 1100.00 * 84 = 92400.00; аванс 20000, удержание 2000 → 70400.00
    accrued, to_pay = svc.compute_line(
        rate="1100", quantity="84", advance="20000", deduction="2000"
    )
    assert accrued == Decimal("92400.00")
    assert to_pay == Decimal("70400.00")


def test_payout_risk_level_r3_r4() -> None:
    assert svc.payout_risk_level(Decimal("234660.00"), 5) == "R3"
    assert svc.payout_risk_level(Decimal("1500000.00"), 5) == "R4"
    # массовая выплата → R4 даже при небольшой сумме
    assert svc.payout_risk_level(Decimal("100000.00"), 60) == "R4"


def _org_site(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    site = Site(organization_id=org.id, project_id=uuid.uuid4(), name="Объект")
    db.add(site)
    db.flush()
    return org, site


def test_recalc_draft_totals(db_session) -> None:
    org, site = _org_site(db_session)
    draft = PayrollDraft(
        organization_id=org.id,
        site_id=site.id,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
    )
    db_session.add(draft)
    db_session.flush()
    db_session.add_all(
        [
            PayrollLine(
                payroll_draft_id=draft.id,
                employee_id=uuid.uuid4(),
                scheme="hourly",
                rate=Decimal("420"),
                quantity=Decimal("122"),
                advance=Decimal("15000"),
            ),
            PayrollLine(
                payroll_draft_id=draft.id,
                employee_id=uuid.uuid4(),
                scheme="piece_rate",
                rate=Decimal("1100"),
                quantity=Decimal("84"),
                advance=Decimal("20000"),
                deduction=Decimal("2000"),
            ),
        ]
    )
    db_session.flush()

    svc.recalc_draft(db_session, draft)

    assert draft.total_accrued == Decimal("143640.00")
    assert draft.total_advance == Decimal("35000.00")
    assert draft.total_deduction == Decimal("2000.00")
    assert draft.total_to_pay == Decimal("106640.00")
    assert draft.risk_level == "R3"
