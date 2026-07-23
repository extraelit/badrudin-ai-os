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

## Адаптеры каналов (PR-3+)

`app/services/channel_adapters.py` — единый контракт `ChannelAdapter.send(...)`:

- **`SandboxAdapter`** — всегда доступен, без внешних вызовов (`sandbox:*`).
- **`EmailAdapter`** (PR-3) — SMTP из окружения; `available()` = True только при
  `SMTP_HOST`+`SMTP_FROM`. Строит письмо с вложениями (из `attachments`).
  Транспорт внедряется (тестируемость), сеть не вызывается без ключей.

`dispatch()` выбирает адаптер по каналу: реальная отправка выполняется **только**
при `COMM_REAL_SEND=true` И готовом адаптере (ключи настроены); иначе — sandbox.
`allow_real_send=True` при недоступном реальном адаптере явно блокируется.

- **`TelegramAdapter`** (PR-4) — официальный Telegram Bot API (`sendMessage`/
  `sendDocument`) с токеном из окружения; http-транспорт внедряется (тесты без
  сети); `available()` = True только при `TELEGRAM_BOT_TOKEN`.

- **`WhatsAppAdapter`** (PR-5) — официальный WhatsApp Business Cloud API (Graph
  API): `text`, `document` (медиа загружается, затем отправляется по id) и
  шаблоны (`send_template` с языком/параметрами). Токен и `phone_number_id` из
  окружения; http-транспорт внедряется; `available()` = True только при
  `WHATSAPP_TOKEN`+`WHATSAPP_PHONE_NUMBER_ID`.

- **`InstagramAdapter`** (PR-6) — официальный Messenger Platform for Instagram
  (Graph API `POST /{ig_id}/messages`, `recipient={id}` + `message={text}`).
  Токен и account id из окружения; http-транспорт внедряется; `available()` =
  True только при `INSTAGRAM_TOKEN`+`INSTAGRAM_ACCOUNT_ID`.
  **Ограничение канала:** байтовые вложения без публичного URL медиа не
  отправляются напрямую — к тексту добавляется пометка о числе вложений (файлы
  доступны в системе). Полноценная отправка медиа требует публичного URL/CDN.

Все каналы (email, telegram, whatsapp, instagram) подключены; реальная отправка —
только при `COMM_REAL_SEND=true` и настроенных ключах.

## Входящие webhooks

- `POST /communications/webhooks/telegram` — Telegram Bot API. Подлинность по
  секрету вебхука (`X-Telegram-Bot-Api-Secret-Token` = `TELEGRAM_WEBHOOK_SECRET`):
  нет секрета → 503; неверный → 403.
- `GET /communications/webhooks/whatsapp` — верификация подписки WhatsApp
  (`hub.mode=subscribe` + `hub.verify_token`==`WHATSAPP_VERIFY_TOKEN` → возвращает
  `hub.challenge`; иначе 403; нет verify-токена → 503).
- `POST /communications/webhooks/whatsapp` — приём входящих. При заданном
  `WHATSAPP_APP_SECRET` проверяется подпись `X-Hub-Signature-256` (HMAC-SHA256);
  иначе — контур verify-токена. Разбирает `entry[].changes[].value.messages[]`.
- `GET /communications/webhooks/instagram` — верификация подписки Instagram
  (`hub.*`, аналогично WhatsApp: challenge/403/503).
- `POST /communications/webhooks/instagram` — приём входящих: разбор
  `entry[].messaging[]` (`sender.id`, `message.text`); подпись при
  `INSTAGRAM_APP_SECRET`, иначе контур verify-токена.

Все webhooks без авторизации пользователя, создают входящее сообщение
(`record_incoming`); организация определяется по коннектору канала.

## Требует решения специалистов ООО «Экстра-Элит»

- Реальные ключи каналов (SMTP/WhatsApp/Instagram/Telegram) — задаются только
  через окружение/secret manager; email-адаптер готов (PR-3), остальные — PR-4…6.
- Выбор политики согласия/стоп-листа и шаблонов WhatsApp — за бизнесом.
- Рассылки (PR-7): группы, планирование, отчёты о доставке.
