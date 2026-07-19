/*
 * Презентационные UI-помощники (карточки, KPI, бейджи, прогресс, графики).
 * Только отображение; данные приходят из lib/mock.ts.
 */
import type { CSSProperties, ReactNode } from "react";
import { Icons, type IconName } from "../lib/icons";
import type { RiskLevel } from "../lib/mock";

export function PageHead({
  title,
  desc,
  action,
}: {
  title: string;
  desc?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page-head__title">{title}</h1>
        {desc && <div className="page-head__desc">{desc}</div>}
      </div>
      {action && <div className="row">{action}</div>}
    </div>
  );
}

export function Kpi({
  label,
  value,
  trend,
  up,
  icon,
  tone,
  foot,
}: {
  label: string;
  value: string;
  trend?: string;
  up?: boolean;
  icon: IconName;
  tone: string;
  foot?: string;
}) {
  const Icon = Icons[icon];
  return (
    <div className="kpi">
      <div className="kpi__label">{label}</div>
      <div className="kpi__value">{value}</div>
      <div className="kpi__foot">
        {trend && (
          <span className={`trend trend--${up ? "up" : "down"}`}>
            {up ? "▲" : "▼"} {trend}
          </span>
        )}
        {foot && <span>{foot}</span>}
      </div>
      <div className={`kpi__icon kpi__icon--${tone}`}>
        <Icon width={22} height={22} />
      </div>
    </div>
  );
}

export function Card({
  title,
  more,
  children,
  flush,
  className,
  style,
}: {
  title?: string;
  more?: string;
  children: ReactNode;
  flush?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <section className={`card${className ? " " + className : ""}`} style={style}>
      {title && (
        <div className="card__head">
          <div className="card__title">{title}</div>
          {more && <span className="link-more">{more}</span>}
        </div>
      )}
      <div className={`card__body${flush ? " card__body--flush" : ""}`}>
        {children}
      </div>
    </section>
  );
}

export function Badge({
  tone,
  children,
}: {
  tone: string;
  children: ReactNode;
}) {
  return (
    <span className={`badge badge--${tone}`}>
      <span className="badge__dot" />
      {children}
    </span>
  );
}

export function Risk({ level }: { level: RiskLevel }) {
  return <span className={`risk risk--${level.toLowerCase()}`}>{level}</span>;
}

export function Progress({
  value,
  tone,
}: {
  value: number;
  tone?: "emerald" | "amber" | "red";
}) {
  return (
    <div className="progress-row">
      <div className="progress">
        <div
          className={`progress__bar${tone ? " progress__bar--" + tone : ""}`}
          style={{ width: `${value}%` }}
        />
      </div>
      <span>{value}%</span>
    </div>
  );
}

export function Bars({
  data,
  max,
  height = 160,
}: {
  data: { m: string; v: number }[];
  max?: number;
  height?: number;
}) {
  const top = max ?? Math.max(...data.map((d) => d.v));
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height }}>
      {data.map((d) => (
        <div
          key={d.m}
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "flex-end",
            height: "100%",
          }}
        >
          <div
            title={`${d.m}: ${d.v}`}
            style={{
              width: "62%",
              maxWidth: 40,
              height: `${Math.max((d.v / top) * 100, 3)}%`,
              background: "linear-gradient(180deg, var(--navy-500), var(--navy-700))",
              borderRadius: "6px 6px 0 0",
            }}
          />
          <span className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            {d.m}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Donut({
  value,
  caption,
}: {
  value: number;
  caption: string;
}) {
  return (
    <div className="donut" style={{ ["--val" as string]: value }}>
      <div className="donut__label">
        <div className="donut__val">{value}%</div>
        <div className="donut__cap">{caption}</div>
      </div>
    </div>
  );
}
