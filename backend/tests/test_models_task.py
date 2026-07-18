"""Тесты моделей задач и согласований (T-1.B5)."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    Base,
    Employee,
    Organization,
    Task,
    TaskAssignment,
)


def test_task_defaults_and_assignment() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        org = Organization(legal_name="ООО «Экстра-Элит»")
        s.add(org)
        s.flush()
        emp = Employee(organization_id=org.id, full_name="Исполнитель")
        task = Task(organization_id=org.id, title="Поручение")
        s.add_all([emp, task])
        s.flush()
        s.add(
            TaskAssignment(
                task_id=task.id, employee_id=emp.id, assignment_role="responsible"
            )
        )
        s.commit()

        loaded = s.scalar(select(Task))
        assert loaded.status == "draft"
        assert loaded.risk_level == "R0"  # шкала R0–R4 (D-001)
        assert loaded.approval_required is False
        assert s.query(TaskAssignment).count() == 1


def test_approval_with_steps() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        org = Organization(legal_name="ООО «Экстра-Элит»")
        s.add(org)
        s.flush()
        appr = Approval(
            organization_id=org.id,
            entity_type="task",
            entity_id=org.id,  # произвольный uuid для теста
            approval_type="manager",
        )
        s.add(appr)
        s.flush()
        s.add(ApprovalStep(approval_id=appr.id, step_number=1))
        s.commit()
        assert appr.status == "pending"
        assert s.query(ApprovalStep).count() == 1
