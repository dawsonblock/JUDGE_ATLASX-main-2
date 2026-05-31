import { Badge } from "@/components/ui/badge";
import type { EvidenceType } from "@/lib/types";
import { cn } from "@/lib/utils";

const TYPE_CONFIG: Record<EvidenceType, { label: string; className: string }> = {
  court_record: { label: "Court Record", className: "bg-blue-100 text-blue-800 border-blue-300" },
  news_report: { label: "News Report", className: "bg-violet-100 text-violet-800 border-violet-300" },
  government_document: { label: "Gov. Document", className: "bg-sky-100 text-sky-800 border-sky-300" },
  witness_statement: { label: "Witness Statement", className: "bg-teal-100 text-teal-800 border-teal-300" },
  police_report: { label: "Police Report", className: "bg-indigo-100 text-indigo-800 border-indigo-300" },
  academic: { label: "Academic", className: "bg-pink-100 text-pink-800 border-pink-300" },
  ngo_report: { label: "NGO Report", className: "bg-lime-100 text-lime-800 border-lime-300" },
  other: { label: "Other", className: "bg-gray-100 text-gray-600 border-gray-300" },
};

interface EvidenceTypeBadgeProps {
  type: EvidenceType;
  className?: string;
}

export function EvidenceTypeBadge({ type, className }: EvidenceTypeBadgeProps) {
  const config = TYPE_CONFIG[type] ?? TYPE_CONFIG.other;
  return (
    <Badge
      variant="outline"
      className={cn("font-medium text-xs", config.className, className)}
    >
      {config.label}
    </Badge>
  );
}
