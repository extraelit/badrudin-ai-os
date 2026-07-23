"""Сквозной production-путь как воспроизводимый тест (PR-10).

БЕЗ реальных внешних вызовов (sandbox/эхо-режим). Покрывает production-цепочку:
процесс → назначение → вложение (universal attachments) → Evidence Gate засчитывает
файл → ИИ-черновик через AI Provider Layer в эхо-режиме → отправка на проверку →
закрытие проверяющим; коммуникации (email в sandbox) и рассылка с отчётом доставки.
"""

from __future__ import annotations

import uuid

from app.models import AIAgent, AgentAIAssignment, AIProvider, Organization
from app.services import ai_provider as ai
from app.services import attachments as att
from app.services import broadcasts as bsvc
from app.services import communications as comm
from app.services import evidence as ev
from app.services import workflow as wf

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _org(db) -> Organization:
    org = Organization(legal_name="ООО «Экстра-Элит»")
    db.add(org)
    db.flush()
    return org


def test_production_path_end_to_end(db_session) -> None:
    db = db_session
    org = _org(db)
    director, manager, engineer, reviewer = (uuid.uuid4() for _ in range(4))

    # 1. Директор ставит процесс (строительный контроль, R3) и согласует.
    proc = wf.create_process(db, org.id, process_kind="construction_control",
                             title="Контроль плиты", author_user_id=director)
    wf.submit_for_approval(db, proc, actor_user_id=director)
    wf.approve(db, proc, approver_user_id=manager)  # согласующий ≠ автор
    assert proc.status == "approved"

    # 2. РП назначает инженера; инженер принимает и стартует.
    wf.assign(db, proc, initiator_user_id=manager, executor_id=engineer,
              responsible_manager_id=manager)
    wf.accept(db, proc, actor_user_id=engineer)
    wf.start(db, proc, actor_user_id=engineer)
    assert proc.status == "in_progress"

    # 3. Evidence Gate: обязательное фото; инженер прикладывает файл через
    #    универсальные вложения (entity=workflow_process) — гейт засчитывает.
    ev.set_requirement(db, org.id, process_kind="construction_control",
                       evidence_type="photo", phase="during", actor_user_id=director)
    assert ev.missing_required(db, proc) == ["photo"]
    att.attach(db, organization_id=org.id, entity_type="workflow_process",
               entity_id=proc.id, original_name="плита.png", content=PNG,
               mime_type="image/png", attachment_type="photo", uploaded_by=engineer)
    assert ev.missing_required(db, proc) == []  # реальный файл закрыл гейт

    # 4. ИИ Provider Layer: назначаем агенту провайдера, черновик в эхо-режиме.
    agent = AIAgent(organization_id=org.id, code="report_drafter", name="Черновик отчёта")
    db.add(agent)
    db.flush()
    provider = AIProvider(organization_id=org.id, code="openai", name="OpenAI", enabled=True,
                          default_model="gpt")
    db.add(provider)
    db.flush()
    db.add(AgentAIAssignment(organization_id=org.id, agent_id=agent.id,
                             primary_provider_id=provider.id, primary_model="gpt"))
    db.flush()
    res = ai.run_for_agent(db, organization_id=org.id, agent_id=agent.id,
                           prompt="Сформируй черновик отчёта по контролю плиты")
    assert res.ok and res.mode == "echo"  # реальные вызовы выключены

    # 5. Отправка на проверку (гейт пройден) → возврат → повтор → закрытие.
    wf.submit_for_review(db, proc, actor_user_id=engineer)
    wf.review(db, proc, reviewer_user_id=reviewer, decision="revision_required",
              comment="уточнить оси")
    wf.start(db, proc, actor_user_id=engineer)
    wf.submit_for_review(db, proc, actor_user_id=engineer)
    wf.review(db, proc, reviewer_user_id=reviewer, decision="completed", comment="принято")
    assert proc.status == "completed" and proc.completed_at is not None

    # 6. Коммуникации: контакт с согласием, email в sandbox.
    contact = comm.create_contact(db, org.id, display_name="Заказчик",
                                  email="client@example.test", consent=True)
    msg = comm.create_draft(db, org.id, channel="email", subject="Готово",
                            body_text="Работы приняты", author_user_id=manager)
    comm.add_recipient(db, msg, address="client@example.test", contact_id=contact.id)
    comm.submit_for_approval(db, msg, actor_user_id=manager)
    comm.approve(db, msg, approver_user_id=director)  # согласующий ≠ автор
    comm.dispatch(db, msg, actor_user_id=director)
    assert msg.status == "sent" and msg.external_id.startswith("sandbox:")

    # 7. Рассылка (sandbox) + отчёт о доставке.
    b = bsvc.create_broadcast(db, org.id, channel="email", title="Уведомление",
                              body_text="Итоги недели", author_user_id=manager)
    bsvc.add_targets(db, b, contact_ids=[contact.id])
    bsvc.submit_for_approval(db, b, actor_user_id=manager)
    bsvc.approve(db, b, approver_user_id=director)
    bsvc.dispatch_broadcast(db, b, actor_user_id=director)
    report = bsvc.delivery_report(db, b)
    assert b.status == "sent" and report["sent"] == 1
