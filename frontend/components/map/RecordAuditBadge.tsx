import { RecordAudit } from "@/lib/api";

type Props = { audit: RecordAudit | undefined };

function statusLabel(status: string) {
  return status.replaceAll("_", " ");
}

export default function RecordAuditBadge({ audit }: Props) {
  if (!audit) return null;
  return (
    <div className="audit-badge">
      <span className="audit-status">{statusLabel(audit.review_status)}</span>
      {audit.reviewed_by ? (
        <span className="audit-meta"> · Reviewed by {audit.reviewed_by}</span>
      ) : null}
      {audit.reviewed_at ? (
        <span className="audit-meta"> · {audit.reviewed_at.slice(0, 10)}</span>
      ) : null}
      {audit.last_updated && audit.last_updated !== audit.reviewed_at ? (
        <span className="audit-meta"> · Updated {audit.last_updated.slice(0, 10)}</span>
      ) : null}
    </div>
  );
}
