import type { HealthAnalysis, Profile } from "../lib/types";
import { formatDateTime } from "../lib/dates";

type ProfileHealthSummaryProps = {
  analysis?: HealthAnalysis | null;
  pendingCount: number;
  profile?: Profile | null;
};

function concernLabel(level: HealthAnalysis["concern_level"]): string | null {
  if (!level) {
    return null;
  }
  if (level === "low") {
    return "Low concern";
  }
  if (level === "moderate") {
    return "Moderate concern";
  }
  return "High concern";
}

function concernClass(level: HealthAnalysis["concern_level"]): string {
  if (level === "high") {
    return "high";
  }
  if (level === "moderate") {
    return "moderate";
  }
  return "low";
}

function secondaryMeta(profile: Profile, pendingCount: number): string {
  const reviewCopy =
    pendingCount > 0
      ? `${pendingCount} weigh-in${pendingCount > 1 ? "s" : ""} need review.`
      : "Everything is saved cleanly.";
  return `${profile.sex}, ${profile.height_cm} cm. ${reviewCopy}`;
}

export function ProfileHealthSummary({
  analysis,
  pendingCount,
  profile,
}: ProfileHealthSummaryProps) {
  if (!profile) {
    return <p className="muted">Choose a profile to see a personal dashboard.</p>;
  }

  const renderedAnalysis = analysis ?? {
    status: "not_configured" as const,
    highlights: [],
    measurement_count: 0,
    is_stale: false,
  };

  return (
    <div className="analysis-block">
      {renderedAnalysis.status === "ready" && renderedAnalysis.summary ? (
        <>
          <div className="analysis-heading">
            {renderedAnalysis.concern_level ? (
              <span className={`analysis-concern-pill ${concernClass(renderedAnalysis.concern_level)}`}>
                {concernLabel(renderedAnalysis.concern_level)}
              </span>
            ) : null}
            <span className="analysis-window-copy">
              Based on the latest {renderedAnalysis.measurement_count} measurement
              {renderedAnalysis.measurement_count === 1 ? "" : "s"}
            </span>
          </div>
          <p className="analysis-summary">{renderedAnalysis.summary}</p>
          {renderedAnalysis.highlights.length > 0 ? (
            <ul className="analysis-highlights">
              {renderedAnalysis.highlights.map((highlight, index) => (
                <li key={`${highlight}-${index}`}>{highlight}</li>
              ))}
            </ul>
          ) : null}
          <p className="analysis-note muted">
            {renderedAnalysis.generated_at
              ? `Updated ${formatDateTime(renderedAnalysis.generated_at)}`
              : "Analysis generated from recent measurements."}
            {renderedAnalysis.is_stale && renderedAnalysis.error_message
              ? ` Showing the last good result because refresh failed: ${renderedAnalysis.error_message}`
              : ""}
          </p>
        </>
      ) : renderedAnalysis.status === "no_data" ? (
        <p className="analysis-summary muted">No measurements yet, so there is nothing to analyze.</p>
      ) : renderedAnalysis.status === "error" ? (
        <>
          <p className="analysis-summary muted">Analysis is unavailable right now.</p>
          {renderedAnalysis.error_message ? (
            <p className="analysis-note muted">{renderedAnalysis.error_message}</p>
          ) : null}
        </>
      ) : (
        <p className="analysis-summary muted">
          Connect an LLM in the admin panel to show an overall health take for this profile.
        </p>
      )}
      <p className="analysis-meta muted">{secondaryMeta(profile, pendingCount)}</p>
    </div>
  );
}
