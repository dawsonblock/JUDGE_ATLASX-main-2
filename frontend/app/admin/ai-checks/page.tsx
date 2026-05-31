"use client";

import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Bot } from "lucide-react";

export default function AdminAiChecksPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Correctness Checks"
        subtitle="Review automated quality assessments for incidents and sources"
      />
      <EmptyState
        icon={<Bot className="h-8 w-8 text-muted-foreground" />}
        title="No AI checks yet"
        description="AI correctness checks will appear here once the pipeline processes new records."
      />
    </div>
  );
}
