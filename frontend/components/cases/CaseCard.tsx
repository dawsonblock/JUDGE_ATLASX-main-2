"use client";

import Link from "next/link";
import { Calendar, FileText } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { CaseItem } from "@/lib/api";

export function CaseCard({ courtCase }: { courtCase: CaseItem }) {
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-slate-900 text-sm leading-snug">
            {courtCase.caption}
          </h3>
          <Badge variant="outline" className="text-xs shrink-0">
            {courtCase.case_type}
          </Badge>
        </div>
        <p className="text-xs text-slate-400 font-mono">{courtCase.docket_number}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <FileText className="h-3 w-3 text-slate-400" />
          <span>Court #{courtCase.court_id}</span>
          <Calendar className="h-3 w-3 text-slate-400 ml-2" />
          <span>
            {courtCase.filed_date
              ? new Date(courtCase.filed_date).toLocaleDateString("en-CA")
              : "—"}
          </span>
          {courtCase.terminated_date && (
            <span className="text-slate-400">
              · closed{" "}
              {new Date(courtCase.terminated_date).toLocaleDateString("en-CA")}
            </span>
          )}
        </div>
        <div className="flex items-center justify-end text-xs">
          <Link href={`/cases/${courtCase.id}`} className="text-blue-600 hover:underline">
            View case →
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

