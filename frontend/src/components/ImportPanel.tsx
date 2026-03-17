import { useState } from "react";

import type { ImportCommitResponse, ImportPreviewResponse, Profile } from "../lib/types";
import { formatDateTime } from "../lib/dates";

type ImportPanelProps = {
  selectedProfile?: Profile;
  onPreview: (file: File) => Promise<ImportPreviewResponse>;
  onCommit: (file: File) => Promise<ImportCommitResponse>;
};

export function ImportPanel({ selectedProfile, onPreview, onCommit }: ImportPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [commitResult, setCommitResult] = useState<ImportCommitResponse | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <section className="panel import-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Import</p>
          <h2>Bring older history into the selected profile</h2>
        </div>
        {selectedProfile ? (
          <p className="muted">Current target: {selectedProfile.name}</p>
        ) : null}
      </div>
      <div className="import-controls">
        <input
          accept=".csv,text/csv"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setPreview(null);
            setCommitResult(null);
          }}
          type="file"
        />
        <button
          className="ghost-button"
          disabled={!file || busy}
          onClick={async () => {
            if (!file) {
              return;
            }
            setBusy(true);
            try {
              setPreview(await onPreview(file));
            } finally {
              setBusy(false);
            }
          }}
          type="button"
        >
          Preview
        </button>
        <button
          className="primary-button"
          disabled={!file || busy}
          onClick={async () => {
            if (!file) {
              return;
            }
            setBusy(true);
            try {
              setCommitResult(await onCommit(file));
            } finally {
              setBusy(false);
            }
          }}
          type="button"
        >
          Import into Existing Profile
        </button>
      </div>
      {preview ? (
        <div className="import-preview">
          <p className="muted">
            Previewing {preview.rows.length} rows from {preview.source_name}
          </p>
          {preview.warnings.map((warning) => (
            <div className="alert-card" key={warning}>
              {warning}
            </div>
          ))}
          <div className="history-table-wrapper">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Measured At</th>
                  <th>Weight</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.row_number}>
                    <td>{row.row_number}</td>
                    <td>{row.measured_at ? formatDateTime(row.measured_at) : "—"}</td>
                    <td>{row.weight_kg ?? "—"}</td>
                    <td>{row.notes.join(", ") || "ready"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {commitResult ? (
        <div className="import-summary">
          <strong>Import complete</strong>
          <p>
            Imported {commitResult.imported} rows, skipped {commitResult.skipped}.
          </p>
        </div>
      ) : null}
    </section>
  );
}
