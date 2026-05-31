"use client";

import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MapPin, Calendar } from "lucide-react";
import type { CrimeIncident } from "@/lib/types";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { ConfidenceBadge } from "@/components/shared/ConfidenceBadge";
import { SectionCard } from "@/components/shared/SectionCard";
import { EmptyState } from "@/components/shared/EmptyState";
import Link from "next/link";

interface IncidentDrawerProps {
  incident: CrimeIncident | null;
  open: boolean;
  onClose: () => void;
}

function DetailsTab({ incident }: { incident: CrimeIncident }) {
  return (
    <div className="space-y-4">
      <SectionCard title="Description">
        <p className="text-sm text-slate-700 leading-relaxed">{incident.summary}</p>
      </SectionCard>

      <SectionCard title="Location">
        <div className="flex items-start gap-2 text-sm text-slate-700">
          <MapPin className="h-4 w-4 mt-0.5 text-slate-400 shrink-0" />
          <span>
            {incident.location.address ? `${incident.location.address}, ` : ""}
            {incident.location.city}, {incident.location.province}
          </span>
        </div>
      </SectionCard>

      <SectionCard title="Classification">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-slate-500">Category</dt>
          <dd className="text-slate-900 capitalize">{incident.category.replace(/_/g, " ")}</dd>
          <dt className="text-slate-500">Status</dt>
          <dd><StatusBadge status={incident.status} /></dd>
          {incident.date && (
            <>
              <dt className="text-slate-500">Date</dt>
              <dd className="text-slate-900 flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {new Date(incident.date).toLocaleDateString("en-CA")}
              </dd>
            </>
          )}
          <dt className="text-slate-500">Confidence</dt>
          <dd><ConfidenceBadge confidence={incident.confidence} /></dd>
        </dl>
      </SectionCard>

      {incident.tags.length > 0 && (
        <SectionCard title="Tags">
          <div className="flex flex-wrap gap-1.5">
            {incident.tags.map((tag) => (
              <Badge key={tag} variant="secondary" className="text-xs">
                {tag}
              </Badge>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}

function AiTab({ incident }: { incident: CrimeIncident }) {
  return (
    <div className="space-y-4">
      <EmptyState
        title="No AI Analysis"
        description="AI analysis has not been generated for this incident yet."
      />
      <SectionCard title="Confidence">
        <div className="flex items-center gap-2">
          <ConfidenceBadge confidence={incident.confidence} />
          <span className="text-xs text-slate-500 capitalize">{incident.confidence}</span>
        </div>
      </SectionCard>
    </div>
  );
}

function EvidenceTab({ incident }: { incident: CrimeIncident }) {
  return (
    <EmptyState
      title="No Evidence Sources"
      description={`This incident references ${incident.sourceCount} source(s). Source details are loaded from the backend.`}
    />
  );
}

function RelatedTab({ incident }: { incident: CrimeIncident }) {
  const hasRelated =
    incident.linkedCases.length > 0 ||
    incident.linkedJudges.length > 0 ||
    incident.linkedDefendants.length > 0;

  if (!hasRelated) {
    return (
      <EmptyState title="No Related Records" description="No court cases, judges, or defendants are linked to this incident." />
    );
  }

  return (
    <div className="space-y-3">
      {incident.linkedCases.length > 0 && (
        <div className="border border-slate-200 rounded-lg p-3">
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Court Cases</p>
          <ul className="space-y-1">
            {incident.linkedCases.map((id) => (
              <li key={id}>
                <Button variant="link" className="p-0 h-auto text-xs text-blue-600" asChild>
                  <Link href={`/cases/${id}`}>{id} →</Link>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {incident.linkedJudges.length > 0 && (
        <div className="border border-slate-200 rounded-lg p-3">
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Judges</p>
          <ul className="space-y-1">
            {incident.linkedJudges.map((id) => (
              <li key={id}>
                <Button variant="link" className="p-0 h-auto text-xs text-blue-600" asChild>
                  <Link href={`/judges/${id}`}>{id} →</Link>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {incident.linkedDefendants.length > 0 && (
        <div className="border border-slate-200 rounded-lg p-3">
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Defendants</p>
          <ul className="space-y-1">
            {incident.linkedDefendants.map((id) => (
              <li key={id}>
                <Button variant="link" className="p-0 h-auto text-xs text-blue-600" asChild>
                  <Link href={`/defendants/${id}`}>{id} →</Link>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function IncidentDrawer({ incident, open, onClose }: IncidentDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg flex flex-col p-0">
        {incident && (
          <>
            <SheetHeader className="px-6 pt-6 pb-4 border-b border-slate-200">
              <SheetTitle className="text-base leading-snug">{incident.title}</SheetTitle>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={incident.status} />
                <span className="text-xs text-slate-400">
                  {incident.location.city}, {incident.location.province}
                </span>
              </div>
            </SheetHeader>
            <ScrollArea className="flex-1">
              <div className="px-6 py-4">
                <Tabs defaultValue="details">
                  <TabsList className="w-full mb-4">
                    <TabsTrigger value="details" className="flex-1">Details</TabsTrigger>
                    <TabsTrigger value="ai" className="flex-1">AI Analysis</TabsTrigger>
                    <TabsTrigger value="evidence" className="flex-1">Evidence</TabsTrigger>
                    <TabsTrigger value="related" className="flex-1">Related</TabsTrigger>
                  </TabsList>
                  <TabsContent value="details">
                    <DetailsTab incident={incident} />
                  </TabsContent>
                  <TabsContent value="ai">
                    <AiTab incident={incident} />
                  </TabsContent>
                  <TabsContent value="evidence">
                    <EvidenceTab incident={incident} />
                  </TabsContent>
                  <TabsContent value="related">
                    <RelatedTab incident={incident} />
                  </TabsContent>
                </Tabs>
              </div>
            </ScrollArea>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
