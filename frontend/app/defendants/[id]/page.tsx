import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchDefendant, fetchDefendantTimeline } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionCard } from "@/components/shared/SectionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft, AlertTriangle } from "lucide-react";

export default async function DefendantPage({ params }: { params: { id: string } }) {
  const [defendant, events] = await Promise.all([
    fetchDefendant(params.id).catch(() => null),
    fetchDefendantTimeline(params.id).catch(() => []),
  ]);
  if (!defendant) notFound();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/defendants">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Defendants
          </Link>
        </Button>
      </div>

      <PageHeader
        title={defendant.display_label}
        subtitle="Defendant — privacy-redacted identifier"
      />

      {defendant.warning && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <p>{defendant.warning}</p>
        </div>
      )}

      <SectionCard title={`Event Timeline (${events.length})`}>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No public events on record.</p>
        ) : (
          <ul className="space-y-3">
            {events.map((ev) => (
              <li key={ev.event_id} className="text-sm border-l-2 border-slate-200 pl-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-slate-800">{ev.event_type}</p>
                    {ev.decision_date && (
                      <p className="text-xs text-slate-500">{ev.decision_date}</p>
                    )}
                    {ev.summary && (
                      <p className="text-xs text-slate-600 mt-0.5 line-clamp-2">{ev.summary}</p>
                    )}
                  </div>
                  <Badge variant="outline" className="text-xs shrink-0">{ev.review_status}</Badge>
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

