import type { Measurement } from "./types";

export const ANTHROPOMETRIC_SOURCE = "anthropometric_estimated";
export const VAI_SOURCE = "vai_estimated";

export function isAnthropometricEstimate(
  measurement: Measurement | null | undefined,
  metric: string,
): boolean {
  return measurement?.source_metric_map?.[metric] === ANTHROPOMETRIC_SOURCE;
}

export function isVaiEstimate(
  measurement: Measurement | null | undefined,
  metric: string,
): boolean {
  return measurement?.source_metric_map?.[metric] === VAI_SOURCE;
}

export function isEstimatedMetric(
  measurement: Measurement | null | undefined,
  metric: string,
): boolean {
  return isAnthropometricEstimate(measurement, metric) || isVaiEstimate(measurement, metric);
}

export function hasAnthropometricEstimate(measurements: Measurement[]): boolean {
  return measurements.some(
    (measurement) =>
      isAnthropometricEstimate(measurement, "fat_pct") ||
      isAnthropometricEstimate(measurement, "water_pct") ||
      isAnthropometricEstimate(measurement, "skeletal_muscle_weight_kg"),
  );
}

export function hasVaiEstimate(measurements: Measurement[]): boolean {
  return measurements.some((measurement) =>
    isVaiEstimate(measurement, "visceral_adiposity_index"),
  );
}
