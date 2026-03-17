import type { Measurement } from "../lib/types";
import { formatDateTime } from "../lib/dates";

type MetricPanelProps = {
  measurement?: Measurement | null;
};

const METRICS: Array<{ key: keyof Measurement; label: string; unit: string }> = [
  { key: "weight_kg", label: "Weight", unit: "kg" },
  { key: "bmi", label: "BMI", unit: "" },
  { key: "fat_pct", label: "Fat", unit: "%" },
  { key: "muscle_pct", label: "Muscle", unit: "%" },
  { key: "water_pct", label: "Water", unit: "%" },
  { key: "visceral_fat", label: "V-Fat", unit: "" },
  { key: "bmr_kcal", label: "Metabolism", unit: "kcal" },
  { key: "body_age", label: "Body Age", unit: "" },
];

export function MetricPanel({ measurement }: MetricPanelProps) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Snapshot</p>
          <h2>Latest measurement at a glance</h2>
        </div>
        {measurement ? (
          <p className="muted">
            {formatDateTime(measurement.measured_at)}
          </p>
        ) : null}
      </div>
      <div className="metric-grid">
        {METRICS.map((metric) => {
          const value = measurement?.[metric.key];
          const numericValue = typeof value === "number" ? value : null;
          const status =
            metric.key in (measurement?.status_by_metric ?? {})
              ? measurement?.status_by_metric[String(metric.key)]
              : null;
          return (
            <article key={String(metric.key)} className="metric-card">
              <span>{metric.label}</span>
              <strong>
                {numericValue !== null ? `${numericValue}${metric.unit}` : "—"}
              </strong>
              {status ? <small className={`status-tag ${status}`}>{status}</small> : <small>derived</small>}
            </article>
          );
        })}
      </div>
    </section>
  );
}
