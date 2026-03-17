import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

import type { ChartResponse } from "../lib/types";
import { formatDate } from "../lib/dates";

type ChartPanelProps = {
  charts?: ChartResponse | null;
};

const METRIC_OPTIONS = [
  { key: "weight_kg", label: "Weight" },
  { key: "bmi", label: "BMI" },
  { key: "fat_pct", label: "Fat %" },
  { key: "muscle_pct", label: "Muscle %" },
  { key: "water_pct", label: "Water %" },
  { key: "visceral_fat", label: "Visceral Fat" },
  { key: "bmr_kcal", label: "Metabolism" },
];

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

export function ChartPanel({ charts }: ChartPanelProps) {
  const [range, setRange] = useState<RangeKey>("month");
  const elementRef = useRef<HTMLDivElement | null>(null);

  const filteredCharts = useMemo(() => {
    if (!charts) {
      return null;
    }
    if (range === "all") {
      return charts;
    }

    const now = new Date();
    const cutoff =
      range === "month"
        ? startOfCurrentMonth()
        : range === "3m"
          ? subtractMonths(now, 3)
          : range === "6m"
            ? subtractMonths(now, 6)
            : subtractMonths(now, 12);

    return {
      ...charts,
      series: Object.fromEntries(
        Object.entries(charts.series).map(([metric, points]) => [
          metric,
          points.filter((point) => new Date(point.measured_at) >= cutoff),
        ]),
      ),
    };
  }, [charts, range]);

  const hasSeries = Boolean(
    filteredCharts &&
      Object.values(filteredCharts.series).some(
        (points) => Array.isArray(points) && points.length > 0,
      ),
  );

  useEffect(() => {
    if (!elementRef.current || !filteredCharts || !hasSeries) {
      return undefined;
    }
    const chart = echarts.init(elementRef.current);
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      legend: {
        top: 0,
        textStyle: { color: "#f4efe7" },
      },
      grid: {
        left: 24,
        right: 24,
        bottom: 24,
        top: 56,
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
        axisLabel: { color: "#e8dcc7" },
        splitLine: { lineStyle: { color: "rgba(232, 220, 199, 0.12)" } },
      },
      series: METRIC_OPTIONS.map((metric) => ({
        name: metric.label,
        type: "line",
        smooth: true,
        showSymbol: false,
        emphasis: { focus: "series" },
        lineStyle: { width: 3 },
        data: (filteredCharts.series[metric.key] ?? []).map((point) => [
          point.measured_at,
          point.value,
        ]),
      })),
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
  }, [filteredCharts, hasSeries]);

  return (
    <section className="panel chart-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Charts</p>
          <h2>How things change over time</h2>
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
      {hasSeries ? (
        <div className="chart-surface" ref={elementRef} />
      ) : (
        <div className="empty-chart">
          No data in this range yet. Try another time window or add more measurements.
        </div>
      )}
    </section>
  );
}
