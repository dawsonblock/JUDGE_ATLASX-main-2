import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionCard } from "@/components/shared/SectionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle, XCircle } from "lucide-react";
import { fetchJson, AdminReviewQueue } from "@/lib/api";

const PENDING = ["pending_review", "pending", "needs_info"];

async function decideAction(formData: FormData) {
  "use server";
  const entityType = formData.get("entity_type") as string;
  const entityId = formData.get("entity_id") as string;
  const decision = formData.get("decision") as string;
  const cookieStore = cookies();
  const accessToken = cookieStore.get("jta_access_token")?.value;
  if (!accessToken) return;
  const base =
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  await fetch(
    `${base}/api/admin/review-queue/${entityType}/${entityId}/decision`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ decision }),
    },
  );
  revalidatePath("/admin/review");
}

export default async function AdminReviewPage() {
  let queue: AdminReviewQueue = { items: [], total_count: 0 };
  let errorMessage: string | null = null;

  try {
    const cookieStore = cookies();
    const accessToken = cookieStore.get("jta_access_token")?.value ?? "";
    queue = await fetchJson<AdminReviewQueue>("/api/admin/review-queue", {
      headers: accessToken ? { authorization: `Bearer ${accessToken}` } : {},
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("401") || msg.includes("403")) {
      errorMessage = "Access denied — admin authentication failed.";
    } else if (msg.includes("503")) {
      errorMessage = "Admin authentication failed. Check server auth configuration.";
    } else if (msg.includes("500")) {
      errorMessage = "Backend error (500) — check backend logs.";
    } else {
      errorMessage = `Failed to load review queue: ${msg}`;
    }
  }

  const items = queue.items;
  const pending = items.filter((i) => PENDING.includes(i.review_status));
  const resolved = items.filter((i) => !PENDING.includes(i.review_status));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Review Queue"
        subtitle={`${pending.length} items pending review`}
      />

      {errorMessage && (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      {pending.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Pending
          </h2>
          {pending.map((item) => (
            <SectionCard
              key={`${item.entity_type}-${item.entity_id}`}
              title={item.title ?? item.entity_type}
            >
              <div className="space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm text-muted-foreground">
                    {item.entity_type}
                    {item.source_type ? ` · ${item.source_type}` : ""}
                  </span>
                  <Badge variant="outline" className="text-xs">
                    {item.review_status}
                  </Badge>
                </div>
                {item.review_notes && (
                  <p className="text-sm text-muted-foreground">{item.review_notes}</p>
                )}
                <div className="flex items-center gap-2 pt-1">
                  <form action={decideAction}>
                    <input type="hidden" name="entity_type" value={item.entity_type} />
                    <input type="hidden" name="entity_id" value={String(item.entity_id)} />
                    <input type="hidden" name="decision" value="approve" />
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
                  <form action={decideAction}>
                    <input type="hidden" name="entity_type" value={item.entity_type} />
                    <input type="hidden" name="entity_id" value={String(item.entity_id)} />
                    <input type="hidden" name="decision" value="rejected" />
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
          {resolved.map((item) => (
            <SectionCard
              key={`${item.entity_type}-${item.entity_id}`}
              title={item.title ?? item.entity_type}
            >
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {item.entity_type}
                  {item.reviewed_at ? ` · ${item.reviewed_at}` : ""}
                </p>
                <Badge>{item.review_status}</Badge>
              </div>
            </SectionCard>
          ))}
        </div>
      )}

      {items.length === 0 && (
        <p className="text-sm text-muted-foreground">No review items found.</p>
      )}
    </div>
  );
}
