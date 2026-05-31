"use client";

import { useState, useMemo, useEffect } from "react";
import type { CrimeIncident, MapFilterState } from "@/lib/types";
import { fetchCrimeIncidents } from "@/lib/api";
import type { CrimeIncidentFeature } from "@/lib/api";
import { MapFilters } from "@/components/map/MapFilters";
import { MapCanvasClient } from "@/components/map/MapCanvasClient";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionCard } from "@/components/shared/SectionCard";

function _mapVerificationStatus(vs: string): CrimeIncident["status"] {
  if (
    vs === "verified" ||
    vs === "official_police_open_data_report" ||
    vs === "verified_court_record" ||
    vs === "official_court_record" ||
    vs === "official_open_data"
  ) {
    return "verified" as CrimeIncident["status"];
  }
  if (vs === "pending_review") return "pending" as CrimeIncident["status"];
  return "pending" as CrimeIncident["status"];
}

function _mapConfidence(vs: string): CrimeIncident["confidence"] {
  if (
    vs === "verified" ||
    vs === "official_police_open_data_report" ||
    vs === "verified_court_record" ||
    vs === "official_court_record" ||
    vs === "official_open_data"
  ) {
    return "verified" as CrimeIncident["confidence"];
  }
  if (vs === "pending_review") return "pending" as CrimeIncident["confidence"];
  return "unverified" as CrimeIncident["confidence"];
}

function _mapFeatureToCrimeIncident(f: CrimeIncidentFeature): CrimeIncident {
  const p = f.properties;
  const [lng, lat] = f.geometry.coordinates;
  return {
    id: String(p.incident_id),
    title: [p.area_label ?? p.city, p.incident_type].filter(Boolean).join(" – ") || "Incident",
    summary: p.disclaimer ?? "",
    category: (p.incident_category as CrimeIncident["category"]) ?? "other",
    status: _mapVerificationStatus(p.verification_status),
    confidence: _mapConfidence(p.verification_status),
    date: p.occurred_at ?? p.reported_at ?? "",
    location: {
      lat,
      lng,
      precision: (p.precision_level as CrimeIncident["location"]["precision"]) ?? "city",
      city: p.city ?? "",
      province: p.province_state ?? "",
      country: p.country ?? "CA",
    },
    sourceCount: p.source_count,
    evidenceCount: p.source_count,
    linkedCases: p.has_court_links ? ["__linked__"] : [],
    linkedJudges: [],
    linkedDefendants: [],
    tags: [],
    sensitive: false,
  } as unknown as CrimeIncident;
}

const DEFAULT_FILTERS: MapFilterState = {
  search: "",
  category: "",
  status: "",
  confidence: "",
  province: "",
  courtLinkedOnly: false,
  verifiedOnly: false,
  hideSensitive: false,
};

function applyFilters(incidents: CrimeIncident[], filters: MapFilterState): CrimeIncident[] {
  return incidents.filter((inc) => {
    if (filters.search) {
      const q = filters.search.toLowerCase();
      if (
        !inc.title.toLowerCase().includes(q) &&
        !inc.location.city.toLowerCase().includes(q) &&
        !inc.location.province.toLowerCase().includes(q)
      ) return false;
    }
    if (filters.category !== "" && inc.category !== filters.category) return false;
    if (filters.status !== "" && inc.status !== filters.status) return false;
    if (filters.province !== "" && inc.location.province !== filters.province) return false;
    if (filters.courtLinkedOnly && inc.linkedCases.length === 0) return false;
    if (filters.verifiedOnly && (inc.confidence === "unverified" || inc.confidence === "pending")) return false;
    if (filters.hideSensitive && inc.sensitive) return false;
    return true;
  });
}

export function CrimeMapWorkspace() {
  const [filters, setFilters] = useState<MapFilterState>(DEFAULT_FILTERS);
  const [selectedIncident, setSelectedIncident] = useState<CrimeIncident | null>(null);
  const [incidents, setIncidents] = useState<CrimeIncident[]>([]);

  useEffect(() => {
    fetchCrimeIncidents()
      .then((fc) => setIncidents(fc.features.map(_mapFeatureToCrimeIncident)))
      .catch(() => {});
  }, []);

  const filtered = useMemo(() => applyFilters(incidents, filters), [incidents, filters]);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)]">
      <div className="shrink-0 px-4 pt-4">
        <PageHeader title="Crime Map" subtitle="Interactive map of tracked incidents across Canada" />
      </div>
      <div className="flex flex-1 min-h-0 gap-0">
        {/* Filter sidebar */}
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
          <MapFilters filters={filters} onChange={setFilters} resultCount={filtered.length} />
        </aside>

        {/* Map area */}
        <div className="flex-1 relative">
          <MapCanvasClient
            incidents={filtered}
            selectedId={selectedIncident?.id}
            onSelect={setSelectedIncident}
          />
        </div>

        {/* Detail panel */}
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-slate-200 bg-white">
          {selectedIncident ? (
            <div className="p-4 space-y-4">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold text-slate-900 text-sm leading-snug">
                  {selectedIncident.title}
                </h2>
                <button
                  onClick={() => setSelectedIncident(null)}
                  className="text-slate-400 hover:text-slate-600 text-xs shrink-0"
                >
                  ✕
                </button>
              </div>
              <StatusBadge status={selectedIncident.status} />
              <SectionCard title="Location">
                <p className="text-sm text-slate-600">
                  {selectedIncident.location.city}, {selectedIncident.location.province}
                </p>
              </SectionCard>
              <SectionCard title="Description">
                <p className="text-sm text-slate-600">{selectedIncident.summary}</p>
              </SectionCard>
              <SectionCard title="Details">
                <dl className="text-sm space-y-1">
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Category</dt>
                    <dd className="text-slate-900 capitalize">{selectedIncident.category.replace(/_/g, " ")}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Confidence</dt>
                    <dd className="text-slate-900 capitalize">{selectedIncident.confidence}</dd>
                  </div>
                  {selectedIncident.date && (
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Date</dt>
                      <dd className="text-slate-900">{new Date(selectedIncident.date).toLocaleDateString()}</dd>
                    </div>
                  )}
                </dl>
              </SectionCard>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center p-8 text-center">
              <p className="text-slate-400 text-sm">Select an incident on the map to view details</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
