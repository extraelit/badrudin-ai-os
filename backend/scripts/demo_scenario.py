"""Сквозной демонстрационный сценарий процессного ядра Badrudin AI OS.

Проверяет полный управленческий цикл на чистой БД (SQLite) через сервисный слой,
с реальными инвариантами разделения обязанностей (SoD), Evidence Gate и честного
ИИ-контура (ИИ формирует черновик-предложение, утверждает человек):

    директор ставит процесс
      → РП назначает инженера
      → инженер принимает в работу и стартует
      → инженер грузит документ/фото (доказательства)
      → ИИ-черновик ежедневного отчёта (предложение, не утверждение)
      → ответственный подтверждает черновик
      → инженер отправляет на проверку (Evidence Gate пройден)
      → проверяющий возвращает на доработку
      → инженер повторно отправляет
      → независимый проверяющий закрывает процесс

Запуск (из каталога backend):
    python -m scripts.demo_scenario

Скрипт ничего не отправляет наружу и не пишет в промышленную БД: он поднимает
временную SQLite в памяти, наполняет минимальный демо-набор и печатает шаги.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.models import (
    Base,
    DailyReport,
    DailyReportFile,
    Employee,
    File,
    Organization,
    Project,
    User,
)
from app.services import daily_report_ai as ai
from app.services import evidence as ev
from app.services import workflow as wf

OK = "  ✓"


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _user(db: Session, org: Organization, name: str, email: str) -> User:
    emp = Employee(organization_id=org.id, full_name=name)
    db.add(emp)
    db.flush()
    user = User(
        email=email,
        password_hash=hash_password("BadrudinDemo!2026"),
        status="active",
        employee_id=emp.id,
    )
    db.add(user)
    db.flush()
    return user


def _file(db: Session, org: Organization, name: str) -> File:
    f = File(
        organization_id=org.id,
        storage_key=f"demo/{uuid.uuid4().hex}",
        original_name=name,
        checksum_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
    )
    db.add(f)
    db.flush()
    return f


def main() -> None:
    db = _session()

    org = Organization(legal_name="ООО «Экстра-Элит»")
    db.add(org)
    db.flush()

    director = _user(db, org, "Генеральный директор", "director@extra-elit.demo")
    manager = _user(db, org, "Руководитель проекта", "pm@extra-elit.demo")
    engineer = _user(db, org, "Инженер-исполнитель", "engineer@extra-elit.demo")
    reviewer = _user(db, org, "Независимый проверяющий", "control@extra-elit.demo")

    project = Project(organization_id=org.id, name="Объект №1", status="active")
    db.add(project)
    db.flush()
    db.commit()

    print("Демонстрационный сценарий процессного ядра Badrudin AI OS")
    print("=" * 62)

    # 1. Директор ставит процесс (строительный контроль, R3 по умолчанию).
    proc = wf.create_process(
        db, org.id,
        process_kind="construction_control",
        title="Контроль устройства монолитной плиты",
        author_user_id=director.id,
        project_id=project.id,
        due_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db.commit()
    print(f"1. Директор поставил процесс: «{proc.title}»")
    print(f"{OK} вид={proc.process_kind} риск={proc.risk_level} статус={proc.status}")

    # R3 требует согласования до назначения; согласующий ≠ автор.
    wf.submit_for_approval(db, proc, actor_user_id=director.id)
    wf.approve(db, proc, approver_user_id=manager.id)
    db.commit()
    print(f"2. Согласование R3 (согласующий ≠ автор): статус={proc.status}")

    # 2. РП назначает инженера (постановщик ≠ исполнитель).
    wf.assign(
        db, proc,
        initiator_user_id=manager.id,
        executor_id=engineer.id,
        responsible_manager_id=manager.id,
    )
    db.commit()
    print(f"3. РП назначил инженера исполнителем: статус={proc.status}")

    # 3. Инженер принимает в работу и стартует (только назначенный исполнитель).
    wf.accept(db, proc, actor_user_id=engineer.id)
    wf.start(db, proc, actor_user_id=engineer.id)
    db.commit()
    print(f"4. Инженер принял и начал работу: статус={proc.status}")

    # Проверка SoD: посторонний не может принять/закрыть.
    try:
        wf.accept(db, proc, actor_user_id=reviewer.id)
        raise SystemExit("ОШИБКА: посторонний принял процесс")
    except wf.WorkflowError:
        print(f"{OK} посторонний не может принять чужой процесс (SoD)")

    # 4. Evidence Gate: делаем документ/фото обязательными и прикладываем их.
    ev.set_requirement(
        db, org.id,
        process_kind="construction_control",
        evidence_type="photo",
        phase="during",
        actor_user_id=director.id,
    )
    ev.set_requirement(
        db, org.id,
        process_kind="construction_control",
        evidence_type="act",
        phase="after",
        actor_user_id=director.id,
    )
    db.commit()
    print("5. Заданы обязательные доказательства: фото + акт (документ)")

    # Гейт должен блокировать отправку без доказательств.
    try:
        wf.submit_for_review(db, proc, actor_user_id=engineer.id)
        raise SystemExit("ОШИБКА: гейт пропустил без доказательств")
    except ev.EvidenceGateError:
        missing = ev.missing_required(db, proc)
        print(f"{OK} Evidence Gate заблокировал отправку; недостаёт: {missing}")

    photo = _file(db, org, "плита_фото.jpg")
    doc = _file(db, org, "акт_осв_работ.pdf")
    ev.add_evidence(db, proc, evidence_type="photo", file_id=photo.id,
                    captured_phase="during", actor_user_id=engineer.id)
    ev.add_evidence(db, proc, evidence_type="act", file_id=doc.id,
                    captured_phase="after", actor_user_id=engineer.id)
    db.commit()
    print("6. Инженер приложил фото и документ (файл обязателен, аудит записан)")

    # 5. ИИ-черновик ежедневного отчёта (предложение, не утверждение).
    report = DailyReport(project_id=project.id, report_date=date.today(),
                         status="draft", workers_count=8)
    db.add(report)
    db.flush()
    db.add(DailyReportFile(daily_report_id=report.id, file_id=photo.id, kind="photo"))
    db.commit()
    proposal = ai.generate_ai_draft(db, report, actor_user_id=engineer.id)
    db.commit()
    print(f"7. ИИ сформировал черновик отчёта (status={proposal.status}, не утверждён)")
    print(f"{OK} текст: {proposal.summary}")
    assert proposal.status == "pending", "ИИ не должен утверждать сам"

    # 6. Ответственный подтверждает черновик (человек в контуре).
    ai.confirm_ai_draft(db, proposal, actor_user_id=manager.id)
    db.commit()
    print(f"8. Ответственный подтвердил черновик: status={proposal.status}")

    # 7. Инженер отправляет на проверку — теперь гейт пройден.
    wf.submit_for_review(db, proc, actor_user_id=engineer.id,
                         executor_comment="Работы выполнены, документы приложены")
    db.commit()
    print(f"9. Инженер отправил на проверку: статус={proc.status}")

    # Исполнитель не может проверить сам себя (независимость R2–R4).
    try:
        wf.review(db, proc, reviewer_user_id=engineer.id, decision="completed")
        raise SystemExit("ОШИБКА: исполнитель закрыл сам себя")
    except wf.WorkflowError:
        print(f"{OK} исполнитель не может закрыть свой процесс (независимая проверка)")

    # 8. Проверяющий возвращает на доработку.
    wf.review(db, proc, reviewer_user_id=reviewer.id, decision="revision_required",
              comment="Уточнить геометрию по осям 3–4")
    db.commit()
    print(f"10. Проверяющий вернул на доработку: статус={proc.status}")

    # Инженер дорабатывает и повторно отправляет.
    wf.start(db, proc, actor_user_id=engineer.id)
    wf.submit_for_review(db, proc, actor_user_id=engineer.id,
                         executor_comment="Геометрия уточнена")
    db.commit()
    print(f"11. Инженер доработал и повторно отправил: статус={proc.status}")

    # 9. Независимый проверяющий закрывает процесс.
    wf.review(db, proc, reviewer_user_id=reviewer.id, decision="completed",
              comment="Принято")
    db.commit()
    print(f"12. Проверяющий закрыл процесс: статус={proc.status}")
    assert proc.status == "completed"
    assert proc.completed_at is not None

    print("=" * 62)
    print("Сценарий пройден полностью. Все инварианты соблюдены:")
    print("  • согласование R3 независимым руководителем;")
    print("  • разделение обязанностей (постановщик ≠ исполнитель ≠ проверяющий);")
    print("  • Evidence Gate: без обязательных фото/документа отправка запрещена;")
    print("  • ИИ формирует черновик-предложение, утверждает человек;")
    print("  • закрытие процесса — только независимым проверяющим.")


if __name__ == "__main__":
    main()
