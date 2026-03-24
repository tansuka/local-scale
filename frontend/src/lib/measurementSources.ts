import type { Measurement } from "./types";

export const ANTHROPOMETRIC_SOURCE = "anthropometric_estimated";

export function isAnthropometricEstimate(
  measurement: Measurement | null | undefined,
  metric: string,
): boolean {
  return measurement?.source_metric_map?.[metric] === ANTHROPOMETRIC_SOURCE;
}

export function hasAnthropometricEstimate(measurements: Measurement[]): boolean {
  return measurements.some(
    (measurement) =>
      isAnthropometricEstimate(measurement, "fat_pct") ||
      isAnthropometricEstimate(measurement, "water_pct") ||
      isAnthropometricEstimate(measurement, "skeletal_muscle_weight_kg"),
  );
}
