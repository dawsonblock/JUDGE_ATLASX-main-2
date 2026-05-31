import { RelatedCourtRecord, RelatedIncident } from "@/lib/api";

type CourtProps = { records: RelatedCourtRecord[] | undefined };
type IncidentProps = { incidents: RelatedIncident[] | undefined };

function statusLabel(status: string) {
  switch (status) {
    case "verified_source_link":
      return "Verified source link";
    case "same_location_context":
      return "Same location (context only)";
    case "same_time_context":
      return "Same time period (context only)";
    default:
      return "Unverified context";
  }
}

export function RelatedCourtRecords({ records }: CourtProps) {
  const verified = records?.filter((r) => r.relationship_status === "verified_source_link") ?? [];
  const context = records?.filter((r) => r.relationship_status !== "verified_source_link") ?? [];

  if (!records?.length) return null;

  return (
    <div className="relationship-section">
      {verified.map((r) => (
        <div key={r.event_id} className="relationship-verified">
          <span className="relationship-badge verified">Verified link</span>
          <strong>{r.case_name ?? r.event_id}</strong>
          {r.judge_name ? <span> · Judge {r.judge_name}</span> : null}
          {r.decision_type ? <span> · {r.decision_type.replaceAll("_", " ")}</span> : null}
          {r.date ? <span> · {r.date}</span> : null}
          {r.url ? (
            <a href={r.url} target="_blank" rel="noreferrer" className="relationship-link">
              View record
            </a>
          ) : null}
        </div>
      ))}
      {context.map((r) => (
        <div key={r.event_id} className="relationship-warning">
          <span className="relationship-badge context">{statusLabel(r.relationship_status)}</span>
          <span>{r.case_name ?? r.event_id}</span>
          {r.date ? <span> · {r.date}</span> : null}
          <span className="relationship-note"> — context, not proof of a causal link</span>
        </div>
      ))}
    </div>
  );
}

export function RelatedIncidents({ incidents }: IncidentProps) {
  const verified = incidents?.filter((r) => r.relationship_status === "verified_source_link") ?? [];
  const context = incidents?.filter((r) => r.relationship_status !== "verified_source_link") ?? [];

  if (!incidents?.length) return null;

  return (
    <div className="relationship-section">
      {verified.map((r) => (
        <div key={r.incident_id} className="relationship-verified">
          <span className="relationship-badge verified">Verified link</span>
          <strong>{r.category}</strong>
          {r.city ? <span> · {r.city}</span> : null}
          {r.date ? <span> · {r.date}</span> : null}
        </div>
      ))}
      {context.map((r) => (
        <div key={r.incident_id} className="relationship-warning">
          <span className="relationship-badge context">{statusLabel(r.relationship_status)}</span>
          <span>{r.category}</span>
          {r.city ? <span> · {r.city}</span> : null}
          {r.date ? <span> · {r.date}</span> : null}
          <span className="relationship-note"> — context, not proof of a causal link</span>
        </div>
      ))}
    </div>
  );
}
