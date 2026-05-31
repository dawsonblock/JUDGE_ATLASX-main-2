import Link from "next/link";
import { Map, Scale, FileText, Users, AlertCircle } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { MetricCard, SectionCard } from "@/components/shared/SectionCard";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { fetchJudges, fetchEventsList } from "@/lib/api";

export default async function DashboardPage() {
  const [judges, events] = await Promise.all([
    fetchJudges().catch(() => []),
    fetchEventsList({ limit: "10" }).catch(() => []),
  ]);
  const recent = events.slice(0, 5);

  return (
    <div className="space-y-8">
      <PageHeader
        title="JUDGE Atlas Dashboard"
        subtitle="Judicial accountability — tracking reported incidents across Canada"
        action={
          <Button asChild>
            <Link href="/map">Open Map</Link>
          </Button>
        }
      />

      {/* Metric row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <MetricCard
          label="Judge Profiles"
          value={judges.length}
          icon={<Scale className="h-5 w-5" />}
        />
        <MetricCard
          label="Public Events"
          value={events.length}
          icon={<AlertCircle className="h-5 w-5" />}
        />
        <MetricCard
          label="Cases"
          value={judges.reduce((sum, j) => sum + j.public_event_count, 0)}
          icon={<FileText className="h-5 w-5" />}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent events */}
        <SectionCard
          title="Recent Events"
          action={
            <Button variant="ghost" size="sm" asChild>
              <Link href="/cases">View cases →</Link>
            </Button>
          }
        >
          <div className="divide-y divide-slate-100">
            {recent.length === 0 ? (
              <p className="py-3 text-sm text-muted-foreground">No public events yet.</p>
            ) : (
              recent.map((ev) => (
                <div key={ev.event_id} className="py-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{ev.event_type}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{ev.decision_date ?? "—"}</p>
                  </div>
                  <Badge variant="outline" className="text-xs shrink-0">{ev.review_status}</Badge>
                </div>
              ))
            )}
          </div>
        </SectionCard>

        {/* Judge summary */}
        <SectionCard title="Judges with Most Events">
          <div className="space-y-2">
            {judges
              .sort((a, b) => b.public_event_count - a.public_event_count)
              .slice(0, 5)
              .map((j) => (
                <div key={j.id} className="flex items-center justify-between text-sm py-1.5">
                  <Link href={`/judges/${j.id}`} className="hover:underline text-primary truncate">
                    {j.name}
                  </Link>
                  <span className="font-medium text-slate-900 shrink-0 ml-2">{j.public_event_count} events</span>
                </div>
              ))}
            {judges.length === 0 && (
              <p className="text-sm text-muted-foreground">No judges found.</p>
            )}
          </div>
        </SectionCard>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { href: "/map", label: "Map", icon: Map, desc: "Geographic view" },
          { href: "/judges", label: "Judges", icon: Scale, desc: "Judicial profiles" },
          { href: "/cases", label: "Cases", icon: FileText, desc: "Court cases" },
          { href: "/sources", label: "Sources", icon: Users, desc: "Evidence sources" },
        ].map(({ href, label, icon: Icon, desc }) => (
          <Link
            key={href}
            href={href}
            className="flex flex-col items-center gap-2 p-4 rounded-lg border border-slate-200 bg-white hover:shadow-sm hover:border-slate-300 transition-all text-center"
          >
            <div className="h-10 w-10 rounded-full bg-slate-100 flex items-center justify-center">
              <Icon className="h-5 w-5 text-slate-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-900">{label}</p>
              <p className="text-xs text-slate-400">{desc}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

