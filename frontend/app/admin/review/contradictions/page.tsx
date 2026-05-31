import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionCard } from "@/components/shared/SectionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle, XCircle, AlertTriangle, GitMerge } from "lucide-react";
import { fetchJson } from "@/lib/api";

async function resolveContradiction(formData: FormData) {
  "use server";
  const contradictionId = formData.get("contradiction_id") as string;
  const decision = formData.get("decision") as string;
  const cookieStore = cookies();
  const accessToken = cookieStore.get("jta_access_token")?.value;
  if (!accessToken) return;
  const base =
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  await fetch(`${base}/api/admin/review-queue/contradictions/${contradictionId}/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ decision }),
  });
  revalidatePath("/admin/review/contradictions");
}

export default async function ContradictionsReviewPage() {
  let contradictions: any[] = [];
  let errorMessage: string | null = null;

  try {
    const cookieStore = cookies();
    const accessToken = cookieStore.get("jta_access_token")?.value ?? "";
    const response = await fetchJson<{ items: any[] }>("/api/admin/review-queue/contradictions", {
      headers: accessToken ? { authorization: `Bearer ${accessToken}` } : {},
    });
    contradictions = response.items || [];
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("401") || msg.includes("403")) {
      errorMessage = "Access denied — admin authentication failed.";
    } else if (msg.includes("503")) {
      errorMessage = "Admin authentication failed. Check server auth configuration.";
    } else if (msg.includes("500")) {
      errorMessage = "Backend error (500) — check backend logs.";
    } else {
      errorMessage = `Failed to load contradictions: ${msg}`;
    }
  }

  const pending = contradictions.filter((c) => c.status === "open");
  const resolved = contradictions.filter((c) => c.status !== "open");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Contradictions Review"
        subtitle={`${pending.length} contradictions pending resolution`}
      />

      {errorMessage && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      {pending.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Pending Resolution
          </h2>
          {pending.map((contradiction) => (
            <SectionCard
              key={contradiction.id}
              title={`Contradiction #${contradiction.id}`}
            >
              <div className="space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline" className="text-xs">
                    {contradiction.conflict_type.replace(/_/g, " ")}
                  </Badge>
                  <Badge variant={contradiction.severity === "critical" ? "destructive" : "secondary"} className="text-xs">
                    {contradiction.severity}
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {contradiction.status}
                  </Badge>
                </div>

                <div className="text-sm space-y-1">
                  <p><strong>Claim A:</strong> {contradiction.claim_a_key || `ID: ${contradiction.claim_a_id}`}</p>
                  <p><strong>Claim B:</strong> {contradiction.claim_b_key || `ID: ${contradiction.claim_b_id}`}</p>
                  <p><strong>Predicate:</strong> {contradiction.predicate || "N/A"}</p>
                  {contradiction.source_authority_weight && (
                    <p><strong>Source Authority Weight:</strong> {contradiction.source_authority_weight.toFixed(2)}</p>
                  )}
                  <p><strong>Detected:</strong> {contradiction.detected_at ? new Date(contradiction.detected_at).toLocaleString() : "N/A"}</p>
                </div>

                {contradiction.severity === "critical" && (
                  <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                    <strong className="flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      Critical Severity
                    </strong>
                    <p className="mt-1">
                      This is a high-severity contradiction that requires immediate attention.
                    </p>
                  </div>
                )}

                <div className="flex items-center gap-2 pt-1">
                  <form action={resolveContradiction}>
                    <input type="hidden" name="contradiction_id" value={String(contradiction.id)} />
                    <input type="hidden" name="decision" value="supersede_a" />
                    <Button
                      type="submit"
                      size="sm"
                      variant="outline"
                      className="text-xs"
                      title="Supersede Claim A (lower authority)"
                    >
                      <GitMerge className="h-3 w-3 mr-1" />
                      Supersede A
                    </Button>
                  </form>
                  <form action={resolveContradiction}>
                    <input type="hidden" name="contradiction_id" value={String(contradiction.id)} />
                    <input type="hidden" name="decision" value="supersede_b" />
                    <Button
                      type="submit"
                      size="sm"
                      variant="outline"
                      className="text-xs"
                      title="Supersede Claim B (lower authority)"
                    >
                      <GitMerge className="h-3 w-3 mr-1" />
                      Supersede B
                    </Button>
                  </form>
                  <form action={resolveContradiction}>
                    <input type="hidden" name="contradiction_id" value={String(contradiction.id)} />
                    <input type="hidden" name="decision" value="retain_both" />
                    <Button
                      type="submit"
                      size="sm"
                      variant="outline"
                      className="text-xs"
                      title="Retain both claims"
                    >
                      <CheckCircle className="h-3 w-3 mr-1" />
                      Retain Both
                    </Button>
                  </form>
                </div>
              </div>
            </SectionCard>
          ))}
        </div>
      )}

      {resolved.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Resolved
          </h2>
          {resolved.map((contradiction) => (
            <SectionCard
              key={contradiction.id}
              title={`Contradiction #${contradiction.id}`}
            >
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {contradiction.conflict_type.replace(/_/g, " ")}
                  {contradiction.resolved_at ? ` · Resolved at ${contradiction.resolved_at}` : ""}
                </p>
                <Badge>{contradiction.status}</Badge>
              </div>
              {contradiction.resolution_note && (
                <p className="text-xs text-muted-foreground mt-1">{contradiction.resolution_note}</p>
              )}
            </SectionCard>
          ))}
        </div>
      )}

      {contradictions.length === 0 && (
        <p className="text-sm text-muted-foreground">No contradictions found in review queue.</p>
      )}
    </div>
  );
}
