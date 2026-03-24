import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";

import type { ChartResponse } from "../lib/types";
import { formatDate } from "../lib/dates";

type ChartPanelProps = {
  charts?: ChartResponse | null;
  theme?: "light" | "dark";
};

const METRIC_OPTIONS = [
  { key: "weight_kg", label: "Weight" },
  { key: "waist_cm", label: "Waist" },
  { key: "bmi", label: "BMI" },
  { key: "fat_pct", label: "Fat %" },
  { key: "skeletal_muscle_weight_kg", label: "Skeletal Muscle" },
  { key: "water_pct", label: "Water %" },
  { key: "visceral_adiposity_index", label: "Visceral Index" },
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

function readChartTheme() {
  const styles = getComputedStyle(document.documentElement);
  return {
    axisColor: styles.getPropertyValue("--chart-axis-color").trim() || "#64748b",
    gridColor: styles.getPropertyValue("--chart-grid-color").trim() || "rgba(148, 163, 184, 0.18)",
    legendColor: styles.getPropertyValue("--chart-legend-color").trim() || "#334155",
    tooltipBackground:
      styles.getPropertyValue("--chart-tooltip-background").trim() || "rgba(15, 23, 42, 0.92)",
    tooltipText: styles.getPropertyValue("--chart-tooltip-text").trim() || "#f8fafc",
  };
}

export function ChartPanel({ charts, theme = "light" }: ChartPanelProps) {
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
    const chartTheme = readChartTheme();
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: chartTheme.tooltipBackground,
        borderColor: "transparent",
        textStyle: { color: chartTheme.tooltipText },
      },
      legend: {
        top: 0,
        textStyle: { color: chartTheme.legendColor },
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
          color: chartTheme.axisColor,
          formatter: (value: number) => formatDate(new Date(value)),
        },
        axisLine: { lineStyle: { color: chartTheme.gridColor } },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: chartTheme.axisColor },
        splitLine: { lineStyle: { color: chartTheme.gridColor } },
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
  }, [filteredCharts, hasSeries, theme]);

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
