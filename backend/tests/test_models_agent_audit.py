"""Тесты моделей ИИ-агентов и журнала аудита (T-1.B7)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import AgentRun, AIAgent, AuditEvent, Base, Organization


def test_agent_and_audit() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        org = Organization(legal_name="ООО «Экстра-Элит»")
        s.add(org)
        s.flush()
        agent = AIAgent(organization_id=org.id, code="executive_assistant", name="Ассистент")
        s.add(agent)
        s.flush()
        s.add(AgentRun(agent_id=agent.id, organization_id=org.id, trigger_type="manual"))
        s.add(
            AuditEvent(
                organization_id=org.id,
                actor_type="system",
                action="task.created",
                risk_level="R1",
            )
        )
        s.commit()

        assert agent.requires_human_approval is True  # человек в контуре (D-002)
        assert agent.default_risk_level == "R1"
        run = s.query(AgentRun).one()
        assert run.status == "pending"
        assert run.risk_level == "R0"
        event = s.query(AuditEvent).one()
        assert event.action == "task.created"
        assert event.created_at is not None
