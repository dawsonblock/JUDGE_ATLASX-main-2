import { Badge } from "@/components/ui/badge";
import type { LegalStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_CONFIG: Record<
  LegalStatus,
  { label: string; className: string }
> = {
  reported: { label: "Reported", className: "bg-slate-100 text-slate-700 border-slate-300" },
  alleged: { label: "Alleged", className: "bg-amber-100 text-amber-800 border-amber-300" },
  charged: { label: "Charged", className: "bg-orange-100 text-orange-800 border-orange-300" },
  before_court: { label: "Before Court", className: "bg-blue-100 text-blue-800 border-blue-300" },
  convicted: { label: "Convicted", className: "bg-red-100 text-red-800 border-red-300" },
  dismissed: { label: "Dismissed", className: "bg-slate-100 text-slate-600 border-slate-300" },
  withdrawn: { label: "Withdrawn", className: "bg-slate-100 text-slate-600 border-slate-300" },
  acquitted: { label: "Acquitted", className: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  unknown: { label: "Unknown", className: "bg-gray-100 text-gray-600 border-gray-300" },
};

interface StatusBadgeProps {
  status: LegalStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.unknown;
  return (
    <Badge
      variant="outline"
      className={cn("font-medium text-xs", config.className, className)}
    >
      {config.label}
    </Badge>
  );
}
