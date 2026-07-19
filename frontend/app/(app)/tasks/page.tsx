"use client";

/* Экран 3. Задачи, сроки и просрочки (с интерактивным фильтром). */
import { useState } from "react";
import { PageHead, Card, Badge } from "../../../components/ui";
import { Icons } from "../../../lib/icons";
import { tasks, taskStats } from "../../../lib/mock";

const FILTERS = ["Все", "Просрочены", "Выполняется", "Ожидают проверки", "Выполнены"] as const;

export default function TasksPage() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("Все");

  const visible = tasks.filter((t) => {
    if (filter === "Все") return true;
    if (filter === "Просрочены") return t.overdue;
    return t.status === filter;
  });

  return (
    <>
      <PageHead
        title="Задачи, сроки и просрочки"
        desc="Контролёр исполнения сопровождает каждое поручение до закрытия"
        action={
          <button className="btn btn--primary btn--sm">
            <Icons.plus width={16} height={16} /> Новая задача
          </button>
        }
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {taskStats.map((s, i) => (
          <div key={s.label} className="kpi">
            <div className="kpi__label">{s.label}</div>
            <div className="kpi__value" style={i === 3 ? { color: "var(--red-600)" } : undefined}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      <Card
        title="Список поручений"
        flush
        className="span-2"
      >
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)" }}>
          <div className="tabs">
            {FILTERS.map((f) => (
              <button
                key={f}
                className={`tab${filter === f ? " tab--active" : ""}`}
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Задача</th>
                <th>Объект</th>
                <th>Исполнитель</th>
                <th>Срок</th>
                <th>Приоритет</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((t) => (
                <tr key={t.id}>
                  <td>
                    <div className="table__strong">{t.title}</div>
                    <div className="table__muted">{t.id}</div>
                  </td>
                  <td>{t.site}</td>
                  <td>{t.assignee}</td>
                  <td className={t.overdue ? "" : undefined} style={t.overdue ? { color: "var(--red-600)", fontWeight: 600 } : undefined}>
                    {t.due}
                  </td>
                  <td>
                    <Badge tone={t.priority === "Высокий" ? "red" : t.priority === "Средний" ? "amber" : "gray"}>
                      {t.priority}
                    </Badge>
                  </td>
                  <td><Badge tone={t.statusTone}>{t.status}</Badge></td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted" style={{ textAlign: "center", padding: 28 }}>
                    Нет задач в выбранном фильтре.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
