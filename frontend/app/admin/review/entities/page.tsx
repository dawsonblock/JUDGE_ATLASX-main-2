import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionCard } from "@/components/shared/SectionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle, XCircle, MapPin, Building2, User } from "lucide-react";
import { fetchJson } from "@/lib/api";

async function approveEntity(formData: FormData) {
  "use server";
  const entityId = formData.get("entity_id") as string;
  const cookieStore = cookies();
  const accessToken = cookieStore.get("jta_access_token")?.value;
  if (!accessToken) return;
  const base =
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  await fetch(`${base}/api/admin/review-queue/entities/${entityId}/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ decision: "approved" }),
  });
  revalidatePath("/admin/review/entities");
}

async function rejectEntity(formData: FormData) {
  "use server";
  const entityId = formData.get("entity_id") as string;
  const cookieStore = cookies();
  const accessToken = cookieStore.get("jta_access_token")?.value;
  if (!accessToken) return;
  const base =
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  await fetch(`${base}/api/admin/review-queue/entities/${entityId}/decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ decision: "rejected" }),
  });
  revalidatePath("/admin/review/entities");
}

export default async function EntitiesReviewPage() {
  let entities: any[] = [];
  let errorMessage: string | null = null;

  try {
    const cookieStore = cookies();
    const accessToken = cookieStore.get("jta_access_token")?.value ?? "";
    const response = await fetchJson<{ items: any[] }>("/api/admin/review-queue/entities", {
      headers: accessToken ? { authorization: `Bearer ${accessToken}` } : {},
    });
    entities = response.items || [];
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("401") || msg.includes("403")) {
      errorMessage = "Access denied — admin authentication failed.";
    } else if (msg.includes("503")) {
      errorMessage = "Admin authentication failed. Check server auth configuration.";
    } else if (msg.includes("500")) {
      errorMessage = "Backend error (500) — check backend logs.";
    } else {
      errorMessage = `Failed to load entities: ${msg}`;
    }
  }

  const pending = entities.filter((e) => ["pending_review", "pending"].includes(e.review_status));
  const resolved = entities.filter((e) => !["pending_review", "pending"].includes(e.review_status));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Entities Review"
        subtitle={`${pending.length} entities pending review`}
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
          {pending.map((entity) => (
            <SectionCard
              key={entity.id}
              title={entity.name || `Entity #${entity.id}`}
            >
              <div className="space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline" className="text-xs">
                    {entity.entity_type}
                  </Badge>
                  <Badge variant="secondary" className="text-xs">
                    {entity.review_status}
                  </Badge>
                  {entity.entity_class && (
                    <Badge variant="outline" className="text-xs">
                      {entity.entity_class.replace(/_/g, " ")}
                    </Badge>
                  )}
                </div>

                <div className="text-sm space-y-1">
                  <p><strong>Name:</strong> {entity.name || "N/A"}</p>
                  {entity.canonical_id && (
                    <p><strong>Canonical ID:</strong> {entity.canonical_id}</p>
                  )}
                  {entity.jurisdiction && (
                    <p><strong>Jurisdiction:</strong> {entity.jurisdiction}</p>
                  )}
                  {entity.country && (
                    <p className="flex items-center gap-1">
                      <MapPin className="h-3 w-3" />
                      {entity.country}
                      {entity.province_state && `, ${entity.province_state}`}
                      {entity.city && `, ${entity.city}`}
                    </p>
                  )}
                  {entity.claim_count !== undefined && (
                    <p><strong>Claims:</strong> {entity.claim_count}</p>
                  )}
                </div>

                {entity.entity_type === "person" && (
                  <div className="rounded border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
                    <strong className="flex items-center gap-1">
                      <User className="h-3 w-3" />
                      Person Entity
                    </strong>
                    <p className="mt-1">
                      This is a person entity that may require additional privacy review.
                    </p>
                  </div>
                )}

                {entity.entity_type === "organization" && (
                  <div className="rounded border border-purple-200 bg-purple-50 px-3 py-2 text-xs text-purple-800">
                    <strong className="flex items-center gap-1">
                      <Building2 className="h-3 w-3" />
                      Organization Entity
                    </strong>
                    <p className="mt-1">
                      This is an organization entity that may require additional verification.
                    </p>
                  </div>
                )}

                <div className="flex items-center gap-2 pt-1">
                  <form action={approveEntity}>
                    <input type="hidden" name="entity_id" value={String(entity.id)} />
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
                  <form action={rejectEntity}>
                    <input type="hidden" name="entity_id" value={String(entity.id)} />
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
          {resolved.map((entity) => (
            <SectionCard
              key={entity.id}
              title={entity.name || `Entity #${entity.id}`}
            >
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {entity.entity_type}
                  {entity.reviewed_at ? ` · Reviewed at ${entity.reviewed_at}` : ""}
                </p>
                <Badge>{entity.review_status}</Badge>
              </div>
            </SectionCard>
          ))}
        </div>
      )}

      {entities.length === 0 && (
        <p className="text-sm text-muted-foreground">No entities found in review queue.</p>
      )}
    </div>
  );
}
