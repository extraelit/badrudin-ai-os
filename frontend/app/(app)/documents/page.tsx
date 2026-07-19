/* Экран 7. Документы. */
import { PageHead, Card, Badge } from "../../../components/ui";
import { Icons, type IconName } from "../../../lib/icons";
import { documents, docCategories } from "../../../lib/mock";

export default function DocumentsPage() {
  return (
    <>
      <PageHead
        title="Документы"
        desc="База знаний компании: договоры, исполнительная документация, сметы, фото и видео"
        action={
          <button className="btn btn--primary btn--sm">
            <Icons.plus width={16} height={16} /> Загрузить документ
          </button>
        }
      />

      <div className="grid grid--kpi" style={{ marginBottom: 18 }}>
        {docCategories.map((c) => {
          const Icon = Icons[c.icon as IconName];
          return (
            <div key={c.name} className="kpi">
              <div className="kpi__label">{c.name}</div>
              <div className="kpi__value">{c.count}</div>
              <div className="kpi__icon kpi__icon--navy">
                <Icon width={22} height={22} />
              </div>
            </div>
          );
        })}
      </div>

      <div className="chips" style={{ marginBottom: 18 }}>
        <span className="chip chip--active">Все документы</span>
        <span className="chip">Договоры</span>
        <span className="chip">Исполнительная</span>
        <span className="chip">Сметы</span>
        <span className="chip">Фото и видео</span>
      </div>

      <Card title="Реестр документов" more="Расширенный поиск" flush className="span-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Название</th>
                <th>Тип</th>
                <th>Объект</th>
                <th>Автор</th>
                <th>Версия</th>
                <th>Дата</th>
                <th>Доступ</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div className="row" style={{ gap: 10 }}>
                      <span className="list__icon" style={{ width: 32, height: 32 }}>
                        <Icons.documents width={16} height={16} />
                      </span>
                      <div>
                        <div className="table__strong">{d.name}</div>
                        <div className="table__muted">{d.id}</div>
                      </div>
                    </div>
                  </td>
                  <td>{d.type}</td>
                  <td>{d.site}</td>
                  <td>{d.author}</td>
                  <td><span className="badge badge--gray">{d.version}</span></td>
                  <td>{d.date}</td>
                  <td><Badge tone={d.accessTone}>{d.access}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
