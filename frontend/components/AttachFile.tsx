"use client";

/* «Прикрепить файл» — универсальный компонент вложений для любой сущности.
 * Список вложений, загрузка (файл + тип доказательства + описание), скачивание
 * (через fetch с JWT) и архивирование. Права проверяются на сервере; действия
 * скрываются флагом canManage. Реальные данные из backend /attachments. */
import { useCallback, useEffect, useState } from "react";
import { getToken } from "../lib/authApi";
import {
  attachmentApi,
  fileToBase64,
  type AttachmentItem,
} from "../lib/attachmentApi";

const TYPES = [
  "document", "photo", "video", "scan", "pdf", "act",
  "delivery_note", "invoice", "certificate", "other",
];

export function AttachFile({
  entityType,
  entityId,
  projectId,
  canManage = true,
  title = "Файлы",
}: {
  entityType: string;
  entityId: string;
  projectId?: string | null;
  canManage?: boolean;
  title?: string;
}) {
  const [items, setItems] = useState<AttachmentItem[]>([]);
  const [type, setType] = useState("document");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(() => {
    attachmentApi.list(entityType, entityId).then(setItems).catch(() => undefined);
  }, [entityType, entityId]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setErr(null);
    setBusy(true);
    try {
      const content_base64 = await fileToBase64(file);
      await attachmentApi.attach({
        entity_type: entityType,
        entity_id: entityId,
        original_name: file.name,
        content_base64,
        mime_type: file.type || undefined,
        attachment_type: type,
        description: desc || undefined,
        project_id: projectId || undefined,
      });
      setDesc("");
      reload();
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function download(a: AttachmentItem) {
    const res = await fetch(attachmentApi.downloadUrl(a.id), {
      headers: { Authorization: `Bearer ${getToken() || ""}` },
    });
    if (!res.ok) {
      setErr(`Ошибка скачивания (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = a.original_name;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function archive(a: AttachmentItem) {
    const reason = window.prompt("Причина архивирования вложения:");
    if (!reason) return;
    try {
      await attachmentApi.archive(a.id, reason);
      reload();
    } catch (e2) {
      setErr((e2 as Error).message);
    }
  }

  return (
    <div className="attach">
      <div className="attach__head" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <strong style={{ fontSize: 13 }}>{title} — {items.length}</strong>
      </div>

      {err && (
        <div className="muted" style={{ color: "#b91c1c", fontSize: 12, marginBottom: 6 }}>{err}</div>
      )}

      {canManage && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
          <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input className="input" placeholder="Описание (необязательно)" value={desc}
                 onChange={(e) => setDesc(e.target.value)} style={{ minWidth: 180 }} />
          <label className="btn btn--sm" style={{ cursor: "pointer" }}>
            {busy ? "Загрузка…" : "Прикрепить файл"}
            <input type="file" hidden onChange={onPick} disabled={busy} />
          </label>
        </div>
      )}

      {items.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>Вложений пока нет.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          {items.map((a) => (
            <li key={a.id} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
              <span className="badge" style={{ fontSize: 10 }}>{a.attachment_type}</span>
              <button className="linklike" onClick={() => download(a)} style={{ background: "none", border: "none", color: "#1d4ed8", cursor: "pointer", padding: 0 }}>
                {a.original_name}
              </button>
              {a.version > 1 && <span className="muted">v{a.version}</span>}
              {a.description && <span className="muted">— {a.description}</span>}
              {canManage && (
                <button className="btn btn--sm" onClick={() => archive(a)} style={{ marginLeft: "auto" }}>В архив</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
