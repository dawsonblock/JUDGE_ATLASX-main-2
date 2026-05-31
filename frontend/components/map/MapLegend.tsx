import { cn } from "@/lib/utils";

const LEGEND_ITEMS = [
  { color: "#94a3b8", label: "Reported / Alleged" },
  { color: "#f97316", label: "Charged" },
  { color: "#3b82f6", label: "Before Court" },
  { color: "#ef4444", label: "Convicted" },
  { color: "#22c55e", label: "Acquitted" },
  { color: "#64748b", label: "Dismissed / Withdrawn" },
];

interface MapLegendProps {
  className?: string;
}

export function MapLegend({ className }: MapLegendProps) {
  return (
    <div
      className={cn(
        "absolute bottom-4 left-4 z-[1000] rounded-md border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur-sm",
        className
      )}
    >
      <p className="mb-2 text-xs font-semibold text-slate-700">Legal Status</p>
      <ul className="space-y-1.5">
        {LEGEND_ITEMS.map((item) => (
          <li key={item.label} className="flex items-center gap-2">
            <span
              className="inline-block h-3 w-3 rounded-full border border-white/50 shadow-sm"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-xs text-slate-600">{item.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
