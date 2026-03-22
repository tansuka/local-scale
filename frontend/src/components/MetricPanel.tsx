import { useMemo, useState } from "react";

import type { Measurement, Profile } from "../lib/types";
import { formatDateTime } from "../lib/dates";

type MetricPanelProps = {
  measurement?: Measurement | null;
  profile?: Profile | null;
};

type MetricKey =
  | "weight_kg"
  | "bmi"
  | "fat_pct"
  | "muscle_pct"
  | "water_pct"
  | "visceral_fat"
  | "bmr_kcal"
  | "body_age";

type MetricDefinition = {
  key: MetricKey;
  label: string;
  unit: string;
  description: string;
};

type MetricBand = {
  healthyLow: number;
  healthyHigh: number;
  obeseHigh: number;
};

const METRICS: MetricDefinition[] = [
  {
    key: "weight_kg",
    label: "Weight",
    unit: "kg",
    description:
      "Weight is best read as a trend. Short-term jumps are worth attention, especially when they move with BMI and fat percentage.",
  },
  {
    key: "bmi",
    label: "BMI",
    unit: "",
    description:
      "BMI is a quick weight-to-height screening number. It is useful for trend tracking, but it should be read alongside fat, muscle, and water.",
  },
  {
    key: "fat_pct",
    label: "Fat",
    unit: "%",
    description:
      "Body fat percentage reflects stored energy and overall body composition. Watching the trend matters more than any single reading.",
  },
  {
    key: "muscle_pct",
    label: "Muscle",
    unit: "%",
    description:
      "Muscle percentage helps show how much lean tissue you are carrying. Healthy changes usually move more gradually than weight.",
  },
  {
    key: "water_pct",
    label: "Water",
    unit: "%",
    description:
      "Water percentage can swing with hydration, exercise, and salt intake. Use it as a signal over time rather than a one-off verdict.",
  },
  {
    key: "visceral_fat",
    label: "V-Fat",
    unit: "",
    description:
      "Visceral fat estimates the fat around internal organs. Higher values deserve attention because they often move with long-term metabolic risk.",
  },
  {
    key: "bmr_kcal",
    label: "Metabolism",
    unit: "kcal",
    description:
      "BMR is an estimate of resting calorie burn. It is a derived value, so it is most useful as supporting context instead of a health band score.",
  },
  {
    key: "body_age",
    label: "Body Age",
    unit: "",
    description:
      "Body age is a derived comparison number. It can be motivating, but your actual trend in weight, fat, muscle, and water is more important.",
  },
];

function roundDisplay(value: number): number {
  return Number(value.toFixed(value >= 10 ? 1 : 2));
}

function bandForMetric(metric: MetricKey, profile?: Profile | null): MetricBand | null {
  const isMale = profile?.sex?.toLowerCase().startsWith("m") ?? false;
  switch (metric) {
    case "weight_kg": {
      if (!profile?.height_cm) {
        return null;
      }
      const heightMeters = profile.height_cm / 100;
      const factor = heightMeters * heightMeters;
      return {
        healthyLow: 18.5 * factor,
        healthyHigh: 24.9 * factor,
        obeseHigh: 24.9 * factor * 1.2,
      };
    }
    case "bmi":
      return { healthyLow: 18.5, healthyHigh: 24.9, obeseHigh: 24.9 * 1.2 };
    case "fat_pct":
      return isMale
        ? { healthyLow: 8, healthyHigh: 20, obeseHigh: 24 }
        : { healthyLow: 21, healthyHigh: 33, obeseHigh: 39.6 };
    case "muscle_pct":
      return isMale
        ? { healthyLow: 38, healthyHigh: 50, obeseHigh: 60 }
        : { healthyLow: 28, healthyHigh: 40, obeseHigh: 48 };
    case "water_pct":
      return isMale
        ? { healthyLow: 50, healthyHigh: 65, obeseHigh: 78 }
        : { healthyLow: 45, healthyHigh: 60, obeseHigh: 72 };
    case "visceral_fat":
      return { healthyLow: 1, healthyHigh: 12, obeseHigh: 14.4 };
    default:
      return null;
  }
}

function classifyValue(value: number | null, band: MetricBand | null): string | null {
  if (value === null || band === null) {
    return null;
  }
  if (value < band.healthyLow) {
    return "low";
  }
  if (value <= band.healthyHigh) {
    return "healthy";
  }
  if (value <= band.obeseHigh) {
    return "high";
  }
  return "obese";
}

function markerPosition(value: number | null, band: MetricBand | null): number {
  if (value === null || band === null) {
    return 50;
  }
  if (value < band.healthyLow) {
    const lowProgress = Math.max(0, value) / Math.max(band.healthyLow, 1);
    return lowProgress * 25;
  }
  if (value <= band.healthyHigh) {
    const progress = (value - band.healthyLow) / Math.max(band.healthyHigh - band.healthyLow, 1);
    return 25 + progress * 25;
  }
  if (value <= band.obeseHigh) {
    const progress = (value - band.healthyHigh) / Math.max(band.obeseHigh - band.healthyHigh, 1);
    return 50 + progress * 25;
  }
  const overflow = (value - band.obeseHigh) / Math.max(band.obeseHigh * 0.25, 1);
  return Math.min(100, 75 + overflow * 25);
}

function thresholdLabel(value: number): string {
  return `${roundDisplay(value)}`;
}

export function MetricPanel({ measurement, profile }: MetricPanelProps) {
  const availableMetricKeys = useMemo(
    () =>
      METRICS.filter((metric) => {
        const value = measurement?.[metric.key];
        return typeof value === "number";
      }).map((metric) => metric.key),
    [measurement],
  );

  const [selectedMetricKey, setSelectedMetricKey] = useState<MetricKey>("weight_kg");

  const activeMetricKey = availableMetricKeys.includes(selectedMetricKey)
    ? selectedMetricKey
    : (availableMetricKeys[0] ?? "weight_kg");
  const activeMetric = METRICS.find((metric) => metric.key === activeMetricKey) ?? METRICS[0];
  const activeValueRaw = measurement?.[activeMetric.key];
  const activeValue = typeof activeValueRaw === "number" ? activeValueRaw : null;
  const activeBand = bandForMetric(activeMetric.key, profile);
  const activeStatus = classifyValue(activeValue, activeBand);
  const activeMarkerPosition = markerPosition(activeValue, activeBand);

  return (
    <section className="panel metric-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Snapshot</p>
          <h2>Latest measurement at a glance</h2>
        </div>
        {measurement ? <p className="muted">{formatDateTime(measurement.measured_at)}</p> : null}
      </div>
      <div className="metric-grid">
        {METRICS.map((metric) => {
          const value = measurement?.[metric.key];
          const numericValue = typeof value === "number" ? value : null;
          const band = bandForMetric(metric.key, profile);
          const status = classifyValue(numericValue, band);
          const isActive = metric.key === activeMetricKey;
          return (
            <button
              key={metric.key}
              className={`metric-card metric-button ${isActive ? "active" : ""}`}
              disabled={numericValue === null}
              onClick={() => setSelectedMetricKey(metric.key)}
              type="button"
            >
              <span>{metric.label}</span>
              <strong>{numericValue !== null ? `${numericValue}${metric.unit}` : "—"}</strong>
              {status ? (
                <small className={`status-tag ${status}`}>{status}</small>
              ) : (
                <small>{numericValue !== null ? "derived" : "no data"}</small>
              )}
            </button>
          );
        })}
      </div>
      <div className="metric-detail-card">
        <div className="metric-detail-header">
          <div>
            <p className="eyebrow">Selected Metric</p>
            <h3>{activeMetric.label}</h3>
          </div>
          <div className="metric-detail-value">
            <strong>{activeValue !== null ? `${activeValue}${activeMetric.unit}` : "—"}</strong>
            {activeStatus ? <span className={`status-tag ${activeStatus}`}>{activeStatus}</span> : null}
          </div>
        </div>

        {activeBand && activeValue !== null ? (
          <div className="health-scale-card">
            <div className="health-thresholds">
              <span>{thresholdLabel(activeBand.healthyLow)}</span>
              <span>{thresholdLabel(activeBand.healthyHigh)}</span>
              <span>{thresholdLabel(activeBand.obeseHigh)}</span>
            </div>
            <div className="health-scale">
              <div className="health-segment low" />
              <div className="health-segment healthy" />
              <div className="health-segment high" />
              <div className="health-segment obese" />
              <div className="health-marker" style={{ left: `${activeMarkerPosition}%` }}>
                <span />
              </div>
            </div>
            <div className="health-labels">
              <span>Low</span>
              <span>Healthy</span>
              <span>High</span>
              <span>Obese</span>
            </div>
          </div>
        ) : null}

        <p className="metric-detail-copy">{activeMetric.description}</p>
      </div>
    </section>
  );
}
