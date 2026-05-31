import { PageHeader } from "@/components/layout/PageHeader";
import { JudgeCard } from "@/components/judges/JudgeCard";
import { EmptyState } from "@/components/shared/EmptyState";
import { fetchJudges } from "@/lib/api";

export default async function JudgesPage() {
  const judges = await fetchJudges();
  return (
    <div className="space-y-6">
      <PageHeader
        title="Judges"
        subtitle="Judicial profiles with linked cases and legal event timelines."
      />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {judges.map((judge) => (
          <JudgeCard key={judge.id} judge={judge} />
        ))}
      </div>
      {judges.length === 0 && (
        <EmptyState title="No Judges" description="No judge profiles have been added yet." />
      )}
    </div>
  );
}

