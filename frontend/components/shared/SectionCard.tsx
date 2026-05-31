import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface SectionCardProps {
  title?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
}

export function SectionCard({ title, action, children, className, contentClassName }: SectionCardProps) {
  return (
    <Card className={cn("", className)}>
      {(title || action) && (
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
          {title && <CardTitle className="text-base font-semibold">{title}</CardTitle>}
          {action && <div>{action}</div>}
        </CardHeader>
      )}
      <CardContent className={cn("", contentClassName)}>{children}</CardContent>
    </Card>
  );
}

interface MetricCardProps {
  label: string;
  value: string | number;
  delta?: string;
  deltaPositive?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

export function MetricCard({ label, value, delta, deltaPositive, icon, className }: MetricCardProps) {
  return (
    <Card className={cn("", className)}>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500">{label}</p>
            <p className="mt-1 text-3xl font-bold text-slate-900">{value}</p>
            {delta && (
              <p
                className={cn(
                  "mt-1 text-xs",
                  deltaPositive ? "text-emerald-600" : "text-red-500"
                )}
              >
                {delta}
              </p>
            )}
          </div>
          {icon && (
            <div className="rounded-md bg-slate-100 p-2 text-slate-500">{icon}</div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
