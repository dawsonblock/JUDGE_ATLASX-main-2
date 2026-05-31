"use client";

import Link from "next/link";
import { Activity, Scale } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { JudgeSummary } from "@/lib/api";

export function JudgeCard({ judge }: { judge: JudgeSummary }) {
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-slate-900">{judge.name}</h3>
          <Badge variant="outline" className="text-xs shrink-0">
            <Scale className="h-3 w-3 mr-1" />
            Court #{judge.court_id ?? "—"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-1.5 text-xs text-slate-600">
          <Activity className="h-3 w-3 text-slate-400" />
          <span>
            {judge.public_event_count} public event
            {judge.public_event_count !== 1 ? "s" : ""}
          </span>
        </div>
        <Link
          href={`/judges/${judge.id}`}
          className="block text-xs text-blue-600 hover:underline mt-1"
        >
          View full profile →
        </Link>
      </CardContent>
    </Card>
  );
}

