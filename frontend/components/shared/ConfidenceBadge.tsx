import { Badge } from "@/components/ui/badge";
import type { SourceConfidence } from "@/lib/types";
import { cn } from "@/lib/utils";

const CONFIDENCE_CONFIG: Record<
  SourceConfidence,
  { label: string; className: string }
> = {
  high: { label: "High Confidence", className: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  medium: { label: "Medium Confidence", className: "bg-amber-100 text-amber-800 border-amber-300" },
  low: { label: "Low Confidence", className: "bg-red-100 text-red-800 border-red-300" },
  pending: { label: "Pending Review", className: "bg-slate-100 text-slate-600 border-slate-300" },
  conflicting: { label: "Conflicting", className: "bg-orange-100 text-orange-800 border-orange-300" },
  unverified: { label: "Unverified", className: "bg-gray-100 text-gray-600 border-gray-300" },
};

interface ConfidenceBadgeProps {
  confidence: SourceConfidence;
  className?: string;
}

export function ConfidenceBadge({ confidence, className }: ConfidenceBadgeProps) {
  const config = CONFIDENCE_CONFIG[confidence] ?? CONFIDENCE_CONFIG.unverified;
  return (
    <Badge
      variant="outline"
      className={cn("font-medium text-xs", config.className, className)}
    >
      {config.label}
    </Badge>
  );
}
