# File / Attachment Service — универсальные вложения (PR-1)

Единый механизм прикрепления файлов ко **всем** основным сущностям системы и
единый интерфейсный компонент «Прикрепить файл».

## Что входит

- **Абстракция хранилища** (`app/services/storage_adapter.py`): выбор бэкенда через
  `STORAGE_BACKEND`:
  - `local` — локальная файловая система (разработка/тесты). Реально пишет байты;
    каталог по умолчанию вне репозитория (системный temp), задаётся
    `LOCAL_STORAGE_DIR`. Скачивание идёт через API-эндпоинт (стрим).
  - `s3` — S3-совместимое (MinIO/AWS S3) для staging/production. Скачивание —
    временная подписанная ссылка. Ключи — только через окружение/secret manager.
- **Модель `attachments`** (`app/models/attachment.py`): связь файла (`files`) с
  сущностью. Поля: `entity_type`+`entity_id`, `attachment_type` (тип доказательства),
  `description`, `project_id`, `organization_id`, `uploaded_by`, `version`+
  `replaces_id`+`is_current` (версии), `is_archived`+`archived_at`/`archived_by`/
  `archive_reason` (архив вместо удаления). SHA-256/размер/MIME/блокировка — в `files`.
- **Сервис** (`app/services/attachments.py`): `attach`, `list_for`, `get`,
  `download`, `archive`, версии.
- **API** `/attachments` (`app/api/attachments.py`): `POST /` (прикрепить),
  `GET /?entity_type=&entity_id=` (список), `GET /{id}/download` (скачать),
  `POST /{id}/archive` (в архив).
- **Компонент** `frontend/components/AttachFile.tsx` + клиент
  `frontend/lib/attachmentApi.ts`. Встроен в экран «Процессы» (кнопка «Файлы»).

## Разрешённые сущности (`ATTACHABLE_ENTITIES`)

`workflow_process`, `daily_report`, `message`, `broadcast`, `approval`, `document`,
`document_version`, `quality_control_card`, `quality_control_check`, `audit_finding`,
`incident`, `procurement_request`, `delivery`, `inventory_operation`, `equipment`,
`tool`, `repair`, `inbound_letter`, `outbound_letter`, `task`.

## Гарантии безопасности

- **RBAC**: `attachment.view` (просмотр/скачивание), `attachment.manage`
  (прикрепление/архивирование). Проверка — на сервере.
- **ABAC**: доступ к вложению ограничен доступом к его проекту; tenant isolation по
  организации.
- **Неизменяемый аудит**: `attachment.add`, `attachment.archive` с SHA-256.
- **Запрет удаления утверждённых файлов**: вложение заблокированного (`locked_at`)
  файла нельзя архивировать; физического удаления нет — только архив.
- **Валидация загрузки**: тип (`ALLOWED_UPLOAD_MIME`) и размер (`MAX_UPLOAD_BYTES`).
- **Версии**: новая версия не затирает старую (`is_current=False` у предыдущей).

## Evidence Gate

Гейт процессного ядра засчитывает **реальные вложения** процесса: приложенный файл
типа, совпадающего с обязательным доказательством (актуальный, не архивный),
закрывает требование наравне с `process_evidence`.

## Требует решения специалистов ООО «Экстра-Элит»

- Реальный S3-бакет и ключи (при `STORAGE_BACKEND=s3`) — предоставляет заказчик.
- Антивирусная проверка вложений (`virus_scan_status`) — интеграция вне контура PR-1.
