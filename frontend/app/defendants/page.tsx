import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";

export default function DefendantsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Defendants"
        subtitle="Individuals linked to tracked incidents and court proceedings."
      />
      <EmptyState
        title="Coming Soon"
        description="Defendant profiles will be available in a future update. Individual privacy protections apply."
      />
    </div>
  );
}
