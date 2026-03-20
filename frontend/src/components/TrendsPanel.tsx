import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

import type { ChartResponse, Measurement, Profile } from "../lib/types";
import { formatDate } from "../lib/dates";
import { HistoryTable } from "./HistoryTable";

type TrendsPanelProps = {
  charts?: ChartResponse | null;
  measurements: Measurement[];
  profiles: Profile[];
  selectedProfileId?: number | null;
  onReassign: (measurementId: number, profileId: number) => Promise<void>;
  onDelete: (measurementId: number) => Promise<void>;
};

const METRIC_OPTIONS = [
  { key: "weight_kg", label: "Weight", unit: "kg" },
  { key: "fat_pct", label: "Fat %", unit: "%" },
  { key: "water_pct", label: "Water %", unit: "%" },
  { key: "muscle_pct", label: "Muscle %", unit: "%" },
  { key: "skeletal_muscle_pct", label: "Skeletal Muscle %", unit: "%" },
  { key: "visceral_fat", label: "Visceral Fat", unit: "" },
  { key: "bmi", label: "BMI", unit: "" },
  { key: "bmr_kcal", label: "Metabolism", unit: "kcal" },
] as const;

type TrendMetricKey = (typeof METRIC_OPTIONS)[number]["key"];
type RangeKey = "month" | "3m" | "6m" | "12m" | "all";

const RANGE_OPTIONS: Array<{ key: RangeKey; label: string }> = [
  { key: "month", label: "This Month" },
  { key: "3m", label: "3 Months" },
  { key: "6m", label: "6 Months" },
  { key: "12m", label: "12 Months" },
  { key: "all", label: "Full History" },
];

function startOfCurrentMonth(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1);
}

function subtractMonths(date: Date, months: number): Date {
  return new Date(date.getFullYear(), date.getMonth() - months, date.getDate());
}

function cutoffForRange(range: RangeKey): Date | null {
  if (range === "all") {
    return null;
  }
  const now = new Date();
  if (range === "month") {
    return startOfCurrentMonth();
  }
  if (range === "3m") {
    return subtractMonths(now, 3);
  }
  if (range === "6m") {
    return subtractMonths(now, 6);
  }
  return subtractMonths(now, 12);
}

export function TrendsPanel({
  charts,
  measurements,
  profiles,
  selectedProfileId,
  onReassign,
  onDelete,
}: TrendsPanelProps) {
  const [range, setRange] = useState<RangeKey>("month");
  const [metric, setMetric] = useState<TrendMetricKey>("weight_kg");
  const elementRef = useRef<HTMLDivElement | null>(null);

  const filteredCharts = useMemo(() => {
    if (!charts) {
      return null;
    }
    const cutoff = cutoffForRange(range);
    if (cutoff === null) {
      return charts;
    }
    return {
      ...charts,
      series: Object.fromEntries(
        Object.entries(charts.series).map(([seriesKey, points]) => [
          seriesKey,
          points.filter((point) => new Date(point.measured_at) >= cutoff),
        ]),
      ),
    };
  }, [charts, range]);

  const filteredMeasurements = useMemo(() => {
    const cutoff = cutoffForRange(range);
    if (cutoff === null) {
      return measurements;
    }
    return measurements.filter((measurement) => new Date(measurement.measured_at) >= cutoff);
  }, [measurements, range]);

  const selectedMetric = METRIC_OPTIONS.find((option) => option.key === metric) ?? METRIC_OPTIONS[0];
  const seriesPoints = filteredCharts?.series[metric] ?? [];
  const hasSeries = seriesPoints.length > 0;

  useEffect(() => {
    if (!elementRef.current || !hasSeries) {
      return undefined;
    }
    const chart = echarts.init(elementRef.current);
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: number) =>
          `${value}${selectedMetric.unit ? ` ${selectedMetric.unit}` : ""}`,
      },
      grid: {
        left: 24,
        right: 24,
        bottom: 24,
        top: 34,
        containLabel: true,
      },
      xAxis: {
        type: "time",
        axisLabel: {
          color: "#e8dcc7",
          formatter: (value: number) => formatDate(new Date(value)),
        },
        axisLine: { lineStyle: { color: "#6f5f4d" } },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          color: "#e8dcc7",
          formatter: (value: number) =>
            `${value}${selectedMetric.unit ? ` ${selectedMetric.unit}` : ""}`,
        },
        splitLine: { lineStyle: { color: "rgba(232, 220, 199, 0.12)" } },
      },
      series: [
        {
          name: selectedMetric.label,
          type: "line",
          smooth: true,
          showSymbol: false,
          emphasis: { focus: "series" },
          lineStyle: { width: 3 },
          data: seriesPoints.map((point) => [point.measured_at, point.value]),
        },
      ],
    });
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => chart.resize())
        : null;
    observer?.observe(elementRef.current);
    return () => {
      observer?.disconnect();
      chart.dispose();
    };
  }, [hasSeries, selectedMetric.label, selectedMetric.unit, seriesPoints]);

  return (
    <div className="tab-content">
      <section className="panel chart-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Trends</p>
            <h2>{selectedMetric.label} over time</h2>
          </div>
          <div className="range-row">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option.key}
                className={`range-button ${range === option.key ? "active" : ""}`}
                onClick={() => setRange(option.key)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <div className="metric-toggle-row">
          {METRIC_OPTIONS.map((option) => (
            <button
              key={option.key}
              className={`range-button ${metric === option.key ? "active" : ""}`}
              onClick={() => setMetric(option.key)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
        {hasSeries ? (
          <div className="chart-surface" ref={elementRef} />
        ) : (
          <div className="empty-chart">
            No {selectedMetric.label.toLowerCase()} data in this range yet. Try another time window.
          </div>
        )}
      </section>

      <HistoryTable
        measurements={filteredMeasurements}
        profiles={profiles}
        selectedProfileId={selectedProfileId}
        onDelete={onDelete}
        onReassign={onReassign}
        eyebrow="Measurements"
        title={`All weigh-ins in ${range === "all" ? "full history" : "this range"}`}
        emptyMessage="No measurements landed inside this time window."
      />
    </div>
  );
}
