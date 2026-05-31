import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionCard } from "@/components/shared/SectionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle, XCircle, Shield, AlertTriangle } from "lucide-react";
import { fetchJson } from "@/lib/api";

async function approveClaim(formData: FormData) {
  "use server";
  const claimId = formData.get("claim_id") as string;
  const cookieStore = cookies();
  const accessToken = cookieStore.get("jta_access_token")?.value;
  if (!accessToken) return;
  const base =
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  await fetch(`${base}/api/admin/review-queue/claims/${claimId}/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ decision: "approved" }),
  });
  revalidatePath("/admin/review/claims");
}

async function rejectClaim(formData: FormData) {
  "use server";
  const claimId = formData.get("claim_id") as string;
  const cookieStore = cookies();
  const accessToken = cookieStore.get("jta_access_token")?.value;
  if (!accessToken) return;
  const base =
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  await fetch(`${base}/api/admin/review-queue/claims/${claimId}/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ decision: "rejected" }),
  });
  revalidatePath("/admin/review/claims");
}

export default async function ClaimsReviewPage() {
  let claims: any[] = [];
  let errorMessage: string | null = null;

  try {
    const cookieStore = cookies();
    const accessToken = cookieStore.get("jta_access_token")?.value ?? "";
    const response = await fetchJson<{ items: any[] }>("/api/admin/review-queue/claims", {
      headers: accessToken ? { authorization: `Bearer ${accessToken}` } : {},
    });
    claims = response.items || [];
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("401") || msg.includes("403")) {
      errorMessage = "Access denied — admin authentication failed.";
    } else if (msg.includes("503")) {
      errorMessage = "Admin authentication failed. Check server auth configuration.";
    } else if (msg.includes("500")) {
      errorMessage = "Backend error (500) — check backend logs.";
    } else {
      errorMessage = `Failed to load claims: ${msg}`;
    }
  }

  const pending = claims.filter((c) => ["pending_review", "pending"].includes(c.review_status));
  const resolved = claims.filter((c) => !["pending_review", "pending"].includes(c.review_status));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Claims Review"
        subtitle={`${pending.length} claims pending review`}
      />

      {errorMessage && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      {pending.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Pending Review
          </h2>
          {pending.map((claim) => (
            <SectionCard
              key={claim.id}
              title={`Claim: ${claim.claim_key || claim.claim_type}`}
            >
              <div className="space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline" className="text-xs">
                    {claim.claim_type}
                  </Badge>
                  <Badge variant="secondary" className="text-xs">
                    {claim.review_status}
                  </Badge>
                  {claim.claim_sensitivity && (
                    <Badge variant="outline" className="text-xs text-amber-600 border-amber-200">
                      <AlertTriangle className="h-3 w-3 mr-1" />
                      {claim.claim_sensitivity.replace(/_/g, " ")}
                    </Badge>
                  )}
                </div>

                <div className="text-sm space-y-1">
                  <p><strong>Entity:</strong> {claim.entity_name || `ID: ${claim.entity_id}`}</p>
                  <p><strong>Predicate:</strong> {claim.predicate || "N/A"}</p>
                  <p><strong>Value:</strong> {claim.claim_value || claim.normalized_value || "N/A"}</p>
                  <p><strong>Confidence:</strong> {claim.confidence ? `${Math.round(claim.confidence * 100)}%` : "N/A"}</p>
                  {claim.jurisdiction && (
                    <p><strong>Jurisdiction:</strong> {claim.jurisdiction}</p>
                  )}
                </div>

                {claim.claim_sensitivity === "criminal_allegation_named_person" && (
                  <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    <strong className="flex items-center gap-1">
                      <Shield className="h-3 w-3" />
                      Requires Elevated Approval
                    </strong>
                    <p className="mt-1">
                      This is a named-person criminal allegation and requires elevated approval before publication.
                    </p>
                  </div>
                )}

                {claim.contradiction_count > 0 && (
                  <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                    <strong className="flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      Contradictions Detected
                    </strong>
                    <p className="mt-1">
                      This claim has {claim.contradiction_count} contradiction(s) that need review.
                    </p>
                  </div>
                )}

                <div className="flex items-center gap-2 pt-1">
                  <form action={approveClaim}>
                    <input type="hidden" name="claim_id" value={String(claim.id)} />
                    <Button
                      type="submit"
                      size="sm"
                      variant="outline"
                      className="text-green-600 border-green-200 hover:bg-green-50"
                    >
                      <CheckCircle className="h-3 w-3 mr-1" />
                      Approve
                    </Button>
                  </form>
                  <form action={rejectClaim}>
                    <input type="hidden" name="claim_id" value={String(claim.id)} />
                    <Button
                      type="submit"
                      size="sm"
                      variant="outline"
                      className="text-red-600 border-red-200 hover:bg-red-50"
                    >
                      <XCircle className="h-3 w-3 mr-1" />
                      Reject
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
          {resolved.map((claim) => (
            <SectionCard
              key={claim.id}
              title={`Claim: ${claim.claim_key || claim.claim_type}`}
            >
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {claim.claim_type}
                  {claim.reviewed_at ? ` · Reviewed at ${claim.reviewed_at}` : ""}
                </p>
                <Badge>{claim.review_status}</Badge>
              </div>
            </SectionCard>
          ))}
        </div>
      )}

      {claims.length === 0 && (
        <p className="text-sm text-muted-foreground">No claims found in review queue.</p>
      )}
    </div>
  );
}
