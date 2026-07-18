#!/usr/bin/env bash
# Резервное копирование PostgreSQL и MinIO (T-1.H2).
# Конфигурация — через переменные окружения (секреты не хранятся в скрипте, D-008).
# Копии шифруются при наличии BACKUP_GPG_RECIPIENT, хранятся несколькими
# поколениями и отдельно от рабочего сервера (DATABASE.md раздел 25).
#
# Требуемые переменные окружения:
#   DATABASE_URL              строка подключения PostgreSQL
#   BACKUP_DIR                каталог для копий (по умолчанию ./backups)
#   BACKUP_KEEP               число хранимых поколений (по умолчанию 7)
#   BACKUP_GPG_RECIPIENT      (опционально) получатель для шифрования gpg
#   MINIO_ALIAS               (опционально) алиас mc для зеркалирования MinIO
#   MINIO_BUCKET              (опционально) бакет для зеркалирования
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP_DIR}"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL не задан" >&2
  exit 1
fi

DUMP_FILE="${BACKUP_DIR}/pg_${STAMP}.dump"
echo "Создаю дамп PostgreSQL: ${DUMP_FILE}"
pg_dump --format=custom --no-owner --dbname="${DATABASE_URL}" --file="${DUMP_FILE}"

# Шифрование при наличии получателя
if [ -n "${BACKUP_GPG_RECIPIENT:-}" ]; then
  echo "Шифрую копию для ${BACKUP_GPG_RECIPIENT}"
  gpg --yes --encrypt --recipient "${BACKUP_GPG_RECIPIENT}" "${DUMP_FILE}"
  rm -f "${DUMP_FILE}"
fi

# Зеркалирование объектного хранилища (если настроен mc)
if [ -n "${MINIO_ALIAS:-}" ] && [ -n "${MINIO_BUCKET:-}" ]; then
  echo "Зеркалирую MinIO ${MINIO_ALIAS}/${MINIO_BUCKET}"
  mc mirror --overwrite "${MINIO_ALIAS}/${MINIO_BUCKET}" "${BACKUP_DIR}/minio_${STAMP}"
fi

# Ротация поколений
echo "Оставляю последние ${BACKUP_KEEP} поколений"
ls -1t "${BACKUP_DIR}"/pg_* 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" | xargs -r rm -f

echo "Готово: резервная копия ${STAMP}"
