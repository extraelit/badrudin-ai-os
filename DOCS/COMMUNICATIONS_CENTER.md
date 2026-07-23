# Центр коммуникаций (PR-2)

Единый контур внешних и внутренних коммуникаций компании: сообщения, контакты,
шаблоны, каналы и журнал доставки. Раздел «Коммуникации» с вкладками: Входящие,
Исходящие, Черновики, Рассылки, Шаблоны, Контакты, Каналы, Журнал доставки.

## Модель данных (миграция 0043)

- **`communication_messages`** — сообщение: `direction` (in/out), `channel`,
  `subject`, `body_text`, проект, ответственный, автор, `scheduled_at`,
  `status`, `external_id`, `error_reason`, `attempts`, поля согласования,
  `sent_at`, `broadcast_id` (задел под PR-7), привязка к деловой сущности.
- **`message_recipients`** — получатели: адрес, контакт, `kind` (to/cc),
  статус, внешний ID, причина ошибки, `delivered_at`/`read_at`.
- **`message_delivery_events`** — журнал доставки (история попыток и статусов).
- **`communication_contacts`** — контакты: имя, email/телефон/telegram/whatsapp/
  instagram, согласие (`consent`), стоп-лист (`stop_listed`), проект.
- **`message_templates`** — шаблоны: код, название, канал, тема, текст,
  утверждение (для WhatsApp — обязательное требование канала).
- **Каналы** = существующие `integration_connectors` (переиспользуем): email,
  WhatsApp Business Cloud, Instagram Messaging, Telegram Bot, внутренние.
- **Вложения** = универсальные `attachments` (`entity_type="message"`, PR-1).

## Статусы сообщения

`draft → pending_approval → approved → scheduled → sending → sent → delivered →
read`; ветви `failed` и `cancelled`. Внешние каналы требуют согласования; для
`internal` согласование не требуется.

## Безопасность (CLAUDE.md §14)

- **Реальная отправка по умолчанию выключена.** До подключения ключей работает
  безопасный **sandbox** (`app/services/communications.py::dispatch`): состояния и
  события доставки фиксируются, но **внешних вызовов нет**; `external_id`
  помечается как `sandbox:*`. Попытка реальной отправки (`allow_real_send=True`)
  явно блокируется до появления адаптеров каналов (PR-3…6).
- **Согласование внешних сообщений** обязательно; SoD: согласующий ≠ автор.
- **Стоп-лист и отсутствие согласия** исключают получателя из отправки.
- **RBAC**: `communication.view` (чтение), `communication.manage` (черновики/
  контакты/шаблоны), `communication.approve` (согласование), `communication.send`
  (отправка/повтор). **ABAC** — по проекту; tenant isolation — по организации.
- **Неизменяемый аудит** всех действий и журнал доставки; повтор — только
  неуспешным получателям (защита от дублей).
- Никаких неофициальных ботов/эмуляции: адаптеры каналов (PR-3…6) используют
  только официальные API.

## API `/communications`

Вкладки: `GET /inbox|/outbox|/drafts|/channels|/templates|/contacts`. Сообщение:
`GET /messages/{id}`, `GET /messages/{id}/delivery-log`, `POST /messages`,
`POST /messages/{id}/recipients|submit-approval|approve|cancel|send|retry`.
Контакты/шаблоны: `POST /contacts`, `POST /contacts/{id}/stop-list`,
`POST /templates`, `POST /templates/{id}/approve`.

## Требует решения специалистов ООО «Экстра-Элит»

- Реальные ключи каналов (SMTP/WhatsApp/Instagram/Telegram) — задаются только
  через окружение/secret manager; подключаются в PR-3…6.
- Выбор политики согласия/стоп-листа и шаблонов WhatsApp — за бизнесом.
- Рассылки (PR-7): группы, планирование, отчёты о доставке.
