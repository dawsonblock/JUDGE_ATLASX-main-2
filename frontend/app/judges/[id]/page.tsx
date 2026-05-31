import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchJudge, fetchJudgeEvents } from "@/lib/api";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionCard } from "@/components/shared/SectionCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Scale, Activity } from "lucide-react";

export default async function JudgePage({ params }: { params: { id: string } }) {
  const [judge, events] = await Promise.all([
    fetchJudge(params.id).catch(() => null),
    fetchJudgeEvents(params.id).catch(() => []),
  ]);
  if (!judge) notFound();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/judges">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Judges
          </Link>
        </Button>
      </div>

      <PageHeader
        title={judge.name}
        subtitle={`Court #${judge.court_id ?? "—"}`}
        action={
          <Badge variant="outline">
            {judge.public_event_count} public event{judge.public_event_count !== 1 ? "s" : ""}
          </Badge>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <SectionCard title="Court">
          <div className="flex items-center gap-2 text-sm">
            <Scale className="h-4 w-4 text-muted-foreground" />
            <span>{judge.court_id ? `Court #${judge.court_id}` : "Unknown"}</span>
          </div>
        </SectionCard>
        <SectionCard title="Public Events">
          <div className="flex items-center gap-2 text-sm">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <span>{judge.public_event_count} verified events</span>
          </div>
        </SectionCard>
      </div>

      <SectionCard title={`Event Timeline (${events.length})`}>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No public events on record.</p>
        ) : (
          <ul className="space-y-3">
            {events.map((ev) => (
              <li key={ev.event_id} className="text-sm border-l-2 border-slate-200 pl-3">
                <p className="font-medium text-slate-800">{ev.event_type}</p>
                {ev.decision_date && (
                  <p className="text-xs text-slate-500">{ev.decision_date}</p>
                )}
                {ev.summary && (
                  <p className="text-xs text-slate-600 mt-0.5 line-clamp-2">{ev.summary}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

