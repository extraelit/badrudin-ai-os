"""Смоук-тест моделей модуля «Проектирование и дизайн»."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models import (
    Counterparty,
    DesignBrief,
    DesignConcept,
    DesignIssue,
    DesignSpecification,
    MarketAvailabilityCheck,
    Material,
    Organization,
    Project,
    ProjectDiscipline,
    ProjectMilestone,
    Supplier,
    SupplierProduct,
)


def test_create_design_entities(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    project = Project(organization_id=org.id, name="Проект")
    db_session.add(project)
    db_session.flush()

    milestone = ProjectMilestone(project_id=project.id, name="Выпуск РД")
    db_session.add(milestone)
    db_session.flush()
    disc = ProjectDiscipline(project_id=project.id, milestone_id=milestone.id,
                             name="Раздел ВК", discipline_type="water_supply")
    db_session.add(disc)

    cp = Counterparty(organization_id=org.id, name="Поставщик")
    material = Material(organization_id=org.id, name="Труба")
    db_session.add_all([cp, material])
    db_session.flush()
    supplier = Supplier(counterparty_id=cp.id)
    db_session.add(supplier)
    db_session.flush()
    db_session.add(SupplierProduct(supplier_id=supplier.id, material_id=material.id,
                                   price=Decimal("100")))

    db_session.add(DesignBrief(organization_id=org.id, project_id=project.id))
    concept = DesignConcept(project_id=project.id, name="Концепция")
    db_session.add(concept)
    db_session.flush()
    spec = DesignSpecification(project_id=project.id, concept_id=concept.id,
                              category="furniture", quantity=Decimal("3"))
    db_session.add(spec)
    db_session.flush()
    db_session.add(MarketAvailabilityCheck(design_specification_id=spec.id,
                                           availability_status="available"))
    db_session.add(DesignIssue(organization_id=org.id, project_id=project.id,
                               title="Замечание"))
    db_session.commit()

    assert db_session.query(ProjectDiscipline).count() == 1
    assert db_session.query(DesignSpecification).count() == 1
    assert db_session.query(MarketAvailabilityCheck).count() == 1
    assert db_session.query(DesignIssue).count() == 1
    assert db_session.query(SupplierProduct).count() == 1
