"""Тесты моделей отчётов, документов и файлов (T-1.B6)."""

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import (
    Base,
    DailyReport,
    Document,
    DocumentVersion,
    File,
    Organization,
    Project,
)


def test_file_document_version_and_report() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        org = Organization(legal_name="ООО «Экстра-Элит»")
        s.add(org)
        s.flush()
        project = Project(organization_id=org.id, name="Объект")
        f = File(
            organization_id=org.id,
            storage_key="files/2026/receipt.jpg",
            original_name="receipt.jpg",
            metadata_json={"source": "mobile"},
        )
        s.add_all([project, f])
        s.flush()
        doc = Document(organization_id=org.id, title="Договор")
        s.add(doc)
        s.flush()
        s.add(DocumentVersion(document_id=doc.id, version_number=1, file_id=f.id))
        s.add(
            DailyReport(
                project_id=project.id, report_date=date(2026, 7, 18), workers_count=5
            )
        )
        s.commit()

        assert s.query(File).count() == 1
        assert s.query(DocumentVersion).count() == 1
        assert s.query(DailyReport).one().workers_count == 5
        assert s.query(File).one().metadata_json["source"] == "mobile"
