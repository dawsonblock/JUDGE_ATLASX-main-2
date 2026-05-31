import { PageHeader } from "@/components/layout/PageHeader";
import { SectionCard } from "@/components/shared/SectionCard";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, CheckCircle } from "lucide-react";
import { fetchSources } from "@/lib/api";

export default async function SourcesPage() {
  const sources = await fetchSources().catch(() => []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Evidence Sources"
        subtitle="Tracked publications, court records, and documents supporting event data."
      />
      {sources.length === 0 ? (
        <p className="text-sm text-muted-foreground">No sources found.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sources.map((source) => (
            <SectionCard
              key={source.id}
              title={source.title}
              action={
                source.url ? (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`View source: ${source.title}`}
                    className="text-slate-400 hover:text-blue-500 shrink-0"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                ) : undefined
              }
            >
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5 items-center">
                  <Badge variant="outline" className="text-xs">{source.source_type}</Badge>
                  <Badge variant="secondary" className="text-xs">{source.source_quality}</Badge>
                  {source.verified_flag && (
                    <span className="flex items-center gap-1 text-xs text-green-600">
                      <CheckCircle className="h-3 w-3" /> Verified
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400">{source.review_status}</p>
              </div>
            </SectionCard>
          ))}
        </div>
      )}
    </div>
  );
}
