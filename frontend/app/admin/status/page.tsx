import { PageHeader } from "@/components/layout/PageHeader";
import { AlphaReadinessPanel } from "@/components/status/AlphaReadinessPanel";
import { fetchAlphaReadinessStatus } from "@/lib/api/status";

function messageFromError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  if (raw.includes("401") || raw.includes("403")) {
    return "Access denied — admin authentication failed.";
  }
  return `Failed to load alpha readiness status: ${raw}`;
}

export default async function AdminStatusPage() {
  let error: string | null = null;
  let status = null;

  try {
    status = await fetchAlphaReadinessStatus();
  } catch (err) {
    error = messageFromError(err);
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Alpha Status" subtitle="Operator readiness and safety posture" />

      {error ? (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {status ? <AlphaReadinessPanel status={status} /> : null}
    </div>
  );
}
