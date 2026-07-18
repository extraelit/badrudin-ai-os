"""Тесты моделей проектов и объектов (T-1.B4, канон D-009)."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    Base,
    Employee,
    Organization,
    Project,
    ProjectLocation,
    ProjectMember,
    Site,
)


def test_project_site_location_chain() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        org = Organization(legal_name="ООО «Экстра-Элит»")
        s.add(org)
        s.flush()
        project = Project(organization_id=org.id, name="Объект №1")
        s.add(project)
        s.flush()
        site = Site(organization_id=org.id, project_id=project.id, name="Площадка А")
        s.add(site)
        s.flush()
        loc = ProjectLocation(
            project_id=project.id,
            site_id=site.id,
            location_type="zone",
            name="Захватка 1",
        )
        emp = Employee(organization_id=org.id, full_name="Прораб")
        s.add_all([loc, emp])
        s.flush()
        s.add(
            ProjectMember(
                project_id=project.id, employee_id=emp.id, project_role="foreman"
            )
        )
        s.commit()

        got_site = s.scalar(select(Site).where(Site.project_id == project.id))
        assert got_site is not None
        assert got_site.name == "Площадка А"
        got_loc = s.scalar(select(ProjectLocation))
        assert got_loc.site_id == site.id
