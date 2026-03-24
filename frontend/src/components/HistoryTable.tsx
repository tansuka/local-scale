import { useMemo, useState, type ReactNode } from "react";

import {
  hasAnthropometricEstimate,
  isAnthropometricEstimate,
} from "../lib/measurementSources";
import type { Measurement, Profile } from "../lib/types";
import { formatDateTime } from "../lib/dates";

type HistoryTableProps = {
  measurements: Measurement[];
  profiles: Profile[];
  selectedProfileId?: number | null;
  onReassign: (measurementId: number, profileId: number) => Promise<void>;
  onDelete: (measurementId: number) => Promise<void>;
  eyebrow?: string;
  title?: string;
  emptyMessage?: string;
};

function ActionIcon({ children }: { children: ReactNode }) {
  return <span className="action-icon" aria-hidden="true">{children}</span>;
}

function renderPercentValue(
  value: number | null | undefined,
  estimated: boolean,
) {
  if (value === null || value === undefined) {
    return "—";
  }
  return (
    <span className="metric-value-with-source">
      <span>{value}%</span>
      {estimated ? <span className="status-tag compact estimated">Est.</span> : null}
    </span>
  );
}

export function HistoryTable({
  measurements,
  profiles,
  selectedProfileId,
  onReassign,
  onDelete,
  eyebrow = "History",
  title = "Recent weigh-ins",
  emptyMessage = "No measurements found for this range yet.",
}: HistoryTableProps) {
  const [busyMeasurementId, setBusyMeasurementId] = useState<number | null>(null);
  const [targetProfileIds, setTargetProfileIds] = useState<Record<number, number>>({});
  const showEstimateNote = hasAnthropometricEstimate(measurements);

  const defaultTargets = useMemo(() => {
    const mapping: Record<number, number> = {};
    measurements.forEach((measurement) => {
      mapping[measurement.id] = selectedProfileId ?? measurement.profile_id;
    });
    return mapping;
  }, [measurements, selectedProfileId]);

  const resolvedTargetProfileIds = { ...defaultTargets, ...targetProfileIds };

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      {showEstimateNote ? (
        <p className="compact-copy muted history-source-note">
          Estimated fat, water, and skeletal muscle values are inferred from sex, age, height, and
          weight when the scale does not provide them.
        </p>
      ) : null}
      <div className="history-table-wrapper">
        <table className="history-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Weight</th>
              <th>Fat</th>
              <th>Water</th>
              <th>SMM</th>
              <th>V-Fat</th>
              <th>BMI</th>
              <th>Status</th>
              <th>Profile</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {measurements.length === 0 ? (
              <tr>
                <td className="history-empty" colSpan={10}>
                  {emptyMessage}
                </td>
              </tr>
            ) : null}
            {measurements.map((measurement) => {
              const pending = measurement.assignment_state !== "confirmed";
              return (
                <tr key={measurement.id}>
                  <td>{formatDateTime(measurement.measured_at)}</td>
                  <td>{measurement.weight_kg} kg</td>
                  <td>
                    {renderPercentValue(
                      measurement.fat_pct,
                      isAnthropometricEstimate(measurement, "fat_pct"),
                    )}
                  </td>
                  <td>
                    {renderPercentValue(
                      measurement.water_pct,
                      isAnthropometricEstimate(measurement, "water_pct"),
                    )}
                  </td>
                  <td>
                    {measurement.skeletal_muscle_weight_kg !== null &&
                    measurement.skeletal_muscle_weight_kg !== undefined ? (
                      <span className="metric-value-with-source">
                        <span>{measurement.skeletal_muscle_weight_kg} kg</span>
                        {isAnthropometricEstimate(measurement, "skeletal_muscle_weight_kg") ? (
                          <span className="status-tag compact estimated">Est.</span>
                        ) : null}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{measurement.visceral_fat ?? "—"}</td>
                  <td>{measurement.bmi ?? "—"}</td>
                  <td>
                    <span className={`status-tag compact ${pending ? "high" : "healthy"}`}>
                      {pending ? "review" : "saved"}
                    </span>
                  </td>
                  <td>
                    <select
                      aria-label={`Target profile for measurement ${measurement.id}`}
                      className="table-profile-select"
                      disabled={busyMeasurementId === measurement.id}
                      value={resolvedTargetProfileIds[measurement.id]}
                      onChange={(event) =>
                        setTargetProfileIds((current) => ({
                          ...current,
                          [measurement.id]: Number(event.target.value),
                        }))
                      }
                    >
                      {profiles.map((profile) => (
                        <option key={profile.id} value={profile.id}>
                          {profile.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <div className="action-row compact">
                      <button
                        aria-label={
                          pending
                            ? `Confirm selected profile for measurement ${measurement.id}`
                            : `Move measurement ${measurement.id}`
                        }
                        className="ghost-button icon-button"
                        disabled={busyMeasurementId === measurement.id}
                        onClick={async () => {
                          setBusyMeasurementId(measurement.id);
                          try {
                            await onReassign(
                              measurement.id,
                              resolvedTargetProfileIds[measurement.id],
                            );
                          } finally {
                            setBusyMeasurementId(null);
                          }
                        }}
                        title={pending ? "Confirm / Move" : "Move"}
                        type="button"
                      >
                        <ActionIcon>
                          <svg viewBox="0 0 16 16">
                            <path
                              d="M6.4 11.2 3.2 8l1.1-1.1 2.1 2.1 5.3-5.3L12.8 4z"
                              fill="currentColor"
                            />
                          </svg>
                        </ActionIcon>
                      </button>
                      <button
                        aria-label={`Delete measurement ${measurement.id}`}
                        className="ghost-button danger-button icon-button"
                        disabled={busyMeasurementId === measurement.id}
                        onClick={async () => {
                          setBusyMeasurementId(measurement.id);
                          try {
                            await onDelete(measurement.id);
                          } finally {
                            setBusyMeasurementId(null);
                          }
                        }}
                        title="Delete"
                        type="button"
                      >
                        <ActionIcon>
                          <svg viewBox="0 0 16 16">
                            <path
                              d="M5.5 2.5h5l.5 1.5H14v1H2V4h3.5zm-.4 3h1v6h-1zm2.4 0h1v6h-1zm2.4 0h1v6h-1zM4 5.5h8l-.5 8h-7z"
                              fill="currentColor"
                            />
                          </svg>
                        </ActionIcon>
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
