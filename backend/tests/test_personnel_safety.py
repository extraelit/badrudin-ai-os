"""Тесты охраны труда: гейт допуска работника к работе."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models import Organization, SafetyClearance, WorkPermit
from app.services import personnel as svc


def test_cleared_worker() -> None:
    clearance = SafetyClearance(
        employee_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        intro_briefing_at=date(2025, 1, 1),
        primary_briefing_at=date(2026, 6, 1),
        signed_by_worker=True,
        medical_valid_until=date(2026, 12, 31),
    )
    result = svc.evaluate_clearance(clearance, [], on_date=date(2026, 7, 18))
    assert result.cleared is True
    assert result.reasons == []


def test_not_cleared_missing_briefing_and_medical() -> None:
    clearance = SafetyClearance(
        employee_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        intro_briefing_at=date(2025, 1, 1),
        primary_briefing_at=None,
        signed_by_worker=False,
        medical_valid_until=date(2026, 1, 1),  # просрочен
    )
    result = svc.evaluate_clearance(clearance, [], on_date=date(2026, 7, 18))
    assert result.cleared is False
    assert any("первичного" in r for r in result.reasons)
    assert any("не подписан" in r for r in result.reasons)
    assert any("медосмотр" in r for r in result.reasons)


def test_required_permit_expired() -> None:
    clearance = SafetyClearance(
        id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        intro_briefing_at=date(2025, 1, 1),
        primary_briefing_at=date(2026, 6, 1),
        signed_by_worker=True,
        medical_valid_until=date(2026, 12, 31),
    )
    permit = WorkPermit(
        clearance_id=clearance.id,
        permit_type="welding",
        valid_until=date(2026, 5, 1),  # просрочен
        status="active",
    )
    result = svc.evaluate_clearance(
        clearance, [permit], on_date=date(2026, 7, 18), required_permits=("welding",)
    )
    assert result.cleared is False
    assert any("просрочен допуск" in r for r in result.reasons)


def test_no_clearance_record() -> None:
    result = svc.evaluate_clearance(None, [], on_date=date(2026, 7, 18))
    assert result.cleared is False


def test_assert_gate_blocks(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp_id = uuid.uuid4()
    db_session.add(
        SafetyClearance(
            employee_id=emp_id,
            organization_id=org.id,
            intro_briefing_at=date(2025, 1, 1),
            primary_briefing_at=None,
            signed_by_worker=False,
            medical_valid_until=None,
        )
    )
    db_session.commit()
    with pytest.raises(svc.ClearanceRequiredError):
        svc.assert_can_mark_worked(
            db_session, employee_id=emp_id, on_date=date(2026, 7, 18)
        )


def test_assert_gate_allows_cleared(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    emp_id = uuid.uuid4()
    db_session.add(
        SafetyClearance(
            employee_id=emp_id,
            organization_id=org.id,
            intro_briefing_at=date(2025, 1, 1),
            primary_briefing_at=date(2026, 6, 1),
            signed_by_worker=True,
            medical_valid_until=date(2026, 12, 31),
        )
    )
    db_session.commit()
    # не должно бросать исключение
    svc.assert_can_mark_worked(
        db_session, employee_id=emp_id, on_date=date(2026, 7, 18)
    )
