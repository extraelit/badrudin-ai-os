"""Смоук-тест моделей модуля «Персонал объектов»: создание и чтение строк."""

from __future__ import annotations

import uuid
from datetime import date

from app.models import (
    DailyReport,
    DailyReportHeadcount,
    DailyReportIssue,
    ForemanJournal,
    Organization,
    PayrollDraft,
    PayrollLine,
    SafetyClearance,
    Site,
    SiteWorkerAssignment,
    WorkPermit,
    WorkShift,
)


def test_create_module_entities(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    site = Site(organization_id=org.id, project_id=uuid.uuid4(), name="Объект")
    db_session.add(site)
    db_session.flush()
    emp_id = uuid.uuid4()

    assignment = SiteWorkerAssignment(
        organization_id=org.id, site_id=site.id, employee_id=emp_id,
        brigade="Бригада №1", profession="Монтажник",
    )
    shift = WorkShift(
        organization_id=org.id, site_id=site.id, employee_id=emp_id,
        work_date=date(2026, 7, 18), hours_worked=8, status="confirmed",
    )
    clearance = SafetyClearance(
        organization_id=org.id, employee_id=emp_id, site_id=site.id,
    )
    db_session.add_all([assignment, shift, clearance])
    db_session.flush()
    db_session.add(WorkPermit(clearance_id=clearance.id, permit_type="height"))

    draft = PayrollDraft(
        organization_id=org.id, site_id=site.id,
        period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
    )
    db_session.add(draft)
    db_session.flush()
    db_session.add(
        PayrollLine(payroll_draft_id=draft.id, employee_id=emp_id, scheme="hourly")
    )
    db_session.add(
        ForemanJournal(
            organization_id=org.id, site_id=site.id, journal_type="general_works"
        )
    )
    report = DailyReport(project_id=uuid.uuid4(), site_id=site.id, report_date=date(2026, 7, 18))
    db_session.add(report)
    db_session.flush()
    db_session.add(
        DailyReportHeadcount(daily_report_id=report.id, profession="Монтажники", count=8)
    )
    db_session.add(
        DailyReportIssue(
            daily_report_id=report.id, issue_type="idle", description="простой"
        )
    )
    db_session.commit()

    assert db_session.query(SiteWorkerAssignment).count() == 1
    assert db_session.query(WorkShift).count() == 1
    assert db_session.query(WorkPermit).count() == 1
    assert db_session.query(ForemanJournal).count() == 1
    assert db_session.query(DailyReportHeadcount).count() == 1
    assert db_session.query(DailyReportIssue).count() == 1
