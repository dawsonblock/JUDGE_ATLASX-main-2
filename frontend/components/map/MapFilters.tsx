"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SectionCard } from "@/components/shared";
import type { MapFilterState, PublicIncidentCategory, LegalStatus } from "@/lib/types";

const CATEGORIES: { value: PublicIncidentCategory; label: string }[] = [
  { value: "fraud", label: "Fraud" },
  { value: "assault", label: "Assault" },
  { value: "homicide", label: "Homicide" },
  { value: "property", label: "Property Crime" },
  { value: "drug", label: "Drug Offence" },
  { value: "organized_crime", label: "Organized Crime" },
  { value: "other", label: "Other" },
];

const STATUSES: { value: LegalStatus; label: string }[] = [
  { value: "reported", label: "Reported" },
  { value: "alleged", label: "Alleged" },
  { value: "charged", label: "Charged" },
  { value: "before_court", label: "Before Court" },
  { value: "convicted", label: "Convicted" },
  { value: "dismissed", label: "Dismissed" },
  { value: "withdrawn", label: "Withdrawn" },
  { value: "acquitted", label: "Acquitted" },
];

const PROVINCES = [
  "Alberta", "British Columbia", "Manitoba", "New Brunswick",
  "Newfoundland and Labrador", "Northwest Territories", "Nova Scotia",
  "Nunavut", "Ontario", "Prince Edward Island", "Québec",
  "Saskatchewan", "Yukon",
];

interface MapFiltersProps {
  filters: MapFilterState;
  onChange: (filters: MapFilterState) => void;
  resultCount?: number;
}

export function MapFilters({ filters, onChange, resultCount }: MapFiltersProps) {
  function set<K extends keyof MapFilterState>(key: K, value: MapFilterState[K]) {
    onChange({ ...filters, [key]: value });
  }

  function reset() {
    onChange({
      search: "",
      category: "",
      status: "",
      confidence: "",
      province: "",
      courtLinkedOnly: false,
      verifiedOnly: false,
      hideSensitive: false,
    });
  }

  return (
    <SectionCard
      title="Filters"
      action={
        <Button variant="ghost" size="sm" onClick={reset} className="h-7 text-xs text-slate-500">
          Reset
        </Button>
      }
      className="h-full rounded-none border-t-0 border-l-0 border-b-0"
      contentClassName="space-y-4 pb-6"
    >
      {resultCount !== undefined && (
        <p className="text-xs text-slate-500">{resultCount} result{resultCount !== 1 ? "s" : ""}</p>
      )}

      <div className="space-y-1.5">
        <Label className="text-xs">Search</Label>
        <Input
          placeholder="Title, city, tag…"
          value={filters.search}
          onChange={(e) => set("search", e.target.value)}
          className="h-8 text-sm"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Category</Label>
        <Select value={filters.category || "all"} onValueChange={(v) => set("category", v === "all" ? "" : (v as PublicIncidentCategory))}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {CATEGORIES.map((c) => (
              <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Legal Status</Label>
        <Select value={filters.status || "all"} onValueChange={(v) => set("status", v === "all" ? "" : (v as LegalStatus))}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Province / Territory</Label>
        <Select value={filters.province || "all"} onValueChange={(v) => set("province", v === "all" ? "" : v)}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue placeholder="All provinces" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All provinces</SelectItem>
            {PROVINCES.map((p) => (
              <SelectItem key={p} value={p}>{p}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Date from</Label>
        <Input
          type="date"
          value={filters.dateFrom ?? ""}
          onChange={(e) => set("dateFrom", e.target.value || undefined)}
          className="h-8 text-sm"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Date to</Label>
        <Input
          type="date"
          value={filters.dateTo ?? ""}
          onChange={(e) => set("dateTo", e.target.value || undefined)}
          className="h-8 text-sm"
        />
      </div>

      <Separator />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label className="text-xs">Court-linked only</Label>
          <Switch
            checked={filters.courtLinkedOnly}
            onCheckedChange={(v) => set("courtLinkedOnly", v)}
          />
        </div>
        <div className="flex items-center justify-between">
          <Label className="text-xs">Verified sources only</Label>
          <Switch
            checked={filters.verifiedOnly}
            onCheckedChange={(v) => set("verifiedOnly", v)}
          />
        </div>
        <div className="flex items-center justify-between">
          <Label className="text-xs">Hide sensitive</Label>
          <Switch
            checked={filters.hideSensitive}
            onCheckedChange={(v) => set("hideSensitive", v)}
          />
        </div>
      </div>
    </SectionCard>
  );
}
