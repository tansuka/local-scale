import { useMemo, useState } from "react";

import type { Measurement, Profile } from "../lib/types";
import { formatDateTime } from "../lib/dates";

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function extractImpedanceOhm(measurement: Measurement): number | null {
  const raw = measurement.raw_payload_json;
  const topLevel = asNumber(raw?.impedance_ohm);
  if (topLevel !== null) {
    return topLevel;
  }

  const samples = Array.isArray(raw?.samples) ? raw.samples : [];
  for (const sample of samples) {
    if (sample && typeof sample === "object") {
      const sampleImpedance = asNumber((sample as Record<string, unknown>).impedance_ohm);
      if (sampleImpedance !== null) {
        return sampleImpedance;
      }
    }
  }

  const advertisementAnalysis =
    raw?.advertisement_analysis &&
    typeof raw.advertisement_analysis === "object" &&
    !Array.isArray(raw.advertisement_analysis)
      ? (raw.advertisement_analysis as Record<string, unknown>)
      : null;
  const selectedCandidate =
    advertisementAnalysis?.selected_candidate &&
    typeof advertisementAnalysis.selected_candidate === "object" &&
    !Array.isArray(advertisementAnalysis.selected_candidate)
      ? (advertisementAnalysis.selected_candidate as Record<string, unknown>)
      : null;
  const selectedSamples = Array.isArray(selectedCandidate?.samples) ? selectedCandidate.samples : [];
  for (const sample of selectedSamples) {
    if (sample && typeof sample === "object") {
      const sampleImpedance = asNumber((sample as Record<string, unknown>).impedance_ohm);
      if (sampleImpedance !== null) {
        return sampleImpedance;
      }
    }
  }

  return null;
}

type HistoryTableProps = {
  measurements: Measurement[];
  profiles: Profile[];
  selectedProfileId?: number | null;
  onReassign: (measurementId: number, profileId: number) => Promise<void>;
  onDelete: (measurementId: number) => Promise<void>;
};

export function HistoryTable({
  measurements,
  profiles,
  selectedProfileId,
  onReassign,
  onDelete,
}: HistoryTableProps) {
  const [busyMeasurementId, setBusyMeasurementId] = useState<number | null>(null);
  const [targetProfileIds, setTargetProfileIds] = useState<Record<number, number>>({});

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
          <p className="eyebrow">History</p>
          <h2>Recent weigh-ins</h2>
        </div>
      </div>
      <div className="history-table-wrapper">
        <table className="history-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Weight</th>
              <th>Impedance</th>
              <th>Fat</th>
              <th>Water</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {measurements.map((measurement) => {
              const pending = measurement.assignment_state !== "confirmed";
              const impedanceOhm = extractImpedanceOhm(measurement);
              return (
                <tr key={measurement.id}>
                  <td>{formatDateTime(measurement.measured_at)}</td>
                  <td>{measurement.weight_kg} kg</td>
                  <td>{impedanceOhm !== null ? `${impedanceOhm} ohm` : "—"}</td>
                  <td>{measurement.fat_pct ?? "—"}%</td>
                  <td>{measurement.water_pct ?? "—"}%</td>
                  <td>
                    <span className={`status-tag ${pending ? "high" : "healthy"}`}>
                      {pending ? "needs review" : "saved"}
                    </span>
                  </td>
                  <td>
                    <div className="action-row">
                      <select
                        aria-label={`Target profile for measurement ${measurement.id}`}
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
                      <button
                        className="ghost-button"
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
                        type="button"
                      >
                        {pending ? "Confirm / Move" : "Move"}
                      </button>
                      <button
                        className="ghost-button danger-button"
                        disabled={busyMeasurementId === measurement.id}
                        onClick={async () => {
                          setBusyMeasurementId(measurement.id);
                          try {
                            await onDelete(measurement.id);
                          } finally {
                            setBusyMeasurementId(null);
                          }
                        }}
                        type="button"
                      >
                        Delete
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
