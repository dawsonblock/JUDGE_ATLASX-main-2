"use client";

/**
 * MapWorkspace — client component that owns fetch state and wires all
 * MapLibre components together for the canonical /map route.
 *
 * Isolation guarantee: this file and all imports under components/maplibre/
 * are the only map runtime code paths.
 *
 * Language note: all user-visible copy in this component describes factual
 * public data only. No language implies guilt, culpability, or misconduct.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { useJudgeMap } from "@/components/maplibre/JudgeMap";
import { fetchCrimeIncidents, fetchJson } from "@/lib/api";
import type {
  CrimeIncidentFeatureCollection,
  FeatureCollection,
} from "@/lib/api";
import JudgeMapClient from "@/components/maplibre/JudgeMapClient";
import JudgeClusterLayer from "@/components/maplibre/JudgeClusterLayer";
import JudgeMapControls from "@/components/maplibre/JudgeMapControls";
import JudgeMapLegend from "@/components/maplibre/JudgeMapLegend";
import JudgeMapPopup from "@/components/maplibre/JudgeMapPopup";
import JudgeRelationshipArcs from "@/components/maplibre/JudgeRelationshipArcs";
import JudgeMapDrawerBridge from "@/components/maplibre/JudgeMapDrawerBridge";
import type { JudgeMapRecord } from "@/components/maplibre/types";
import { getDisclaimer } from "@/lib/disclaimerService";

type LoadState = "idle" | "loading" | "error";

type IncidentFilterInputs = {
  bbox: string | null;
  incidentType: "individual" | "aggregate" | "all";
  jurisdiction: string;
  sourceName: string;
  dateFrom: string;
  dateTo: string;
  category: string;
};

export function buildIncidentParams(inputs: IncidentFilterInputs): Record<string, string> {
  const params: Record<string, string> = {
    is_public: "true",
    reviewed_only: "true",
  };

  if (inputs.incidentType === "individual") params.exclude_aggregate = "true";
  else if (inputs.incidentType === "aggregate") params.aggregate_only = "true";

  if (inputs.bbox) params.bbox = inputs.bbox;
  if (inputs.jurisdiction) params.jurisdiction = inputs.jurisdiction;
  if (inputs.sourceName) params.source_name = inputs.sourceName;
  if (inputs.dateFrom) params.start_date = inputs.dateFrom;
  if (inputs.dateTo) params.end_date = inputs.dateTo;
  if (inputs.category) params.incident_category = inputs.category;

  return params;
}

/**
 * Attaches moveend/zoomend listeners to the MapLibre instance (via context)
 * and calls onBoundsChange with a debounced "west,south,east,north" bbox string.
 * Must be rendered inside a JudgeMap tree to access MapLibreContext.
 */
function BoundsTracker({
  onBoundsChange,
}: {
  onBoundsChange: (bbox: string) => void;
}) {
  const map = useJudgeMap();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!map) return;
    const update = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        const b = map.getBounds();
        const bbox = [
          b.getWest().toFixed(4),
          b.getSouth().toFixed(4),
          b.getEast().toFixed(4),
          b.getNorth().toFixed(4),
        ].join(",");
        onBoundsChange(bbox);
      }, 300);
    };
    map.on("moveend", update);
    map.on("zoomend", update);
    return () => {
      map.off("moveend", update);
      map.off("zoomend", update);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [map, onBoundsChange]);

  return null;
}

/**
 * Fit map to first loaded data window so users immediately see records,
 * even when fixture points are far from default map center.
 */
function AutoFitToRecords({
  incidents,
  events,
}: {
  incidents: CrimeIncidentFeatureCollection | null;
  events: FeatureCollection | null;
}) {
  const map = useJudgeMap();
  const fittedRef = useRef(false);

  useEffect(() => {
    if (!map || fittedRef.current) return;

    const coords: Array<[number, number]> = [];
    incidents?.features.forEach((f) => {
      const [lng, lat] = f.geometry.coordinates;
      if (Number.isFinite(lng) && Number.isFinite(lat)) coords.push([lng, lat]);
    });
    events?.features.forEach((f) => {
      const [lng, lat] = f.geometry.coordinates;
      if (Number.isFinite(lng) && Number.isFinite(lat)) coords.push([lng, lat]);
    });

    if (!coords.length) return;

    const bounds = coords.reduce(
      (acc, [lng, lat]) => acc.extend([lng, lat]),
      new maplibregl.LngLatBounds(coords[0], coords[0]),
    );

    map.fitBounds(bounds, {
      padding: 48,
      maxZoom: 11,
      duration: 0,
    });
    fittedRef.current = true;
  }, [map, incidents, events]);

  return null;
}

export default function MapWorkspace() {
  const [incidents, setIncidents] =
    useState<CrimeIncidentFeatureCollection | null>(null);
  const [events, setEvents] = useState<FeatureCollection | null>(null);
  const [jurisdiction, setJurisdiction] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [showEvents, setShowEvents] = useState(true);
  const [officialOnly, setOfficialOnly] = useState<boolean | null>(null);
  const [sourceType, setSourceType] = useState("");
  const [category, setCategory] = useState("");
  const [incidentType, setIncidentType] = useState<
    "individual" | "aggregate" | "all"
  >("individual");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [selectedRecord, setSelectedRecord] = useState<JudgeMapRecord | null>(
    null,
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [bbox, setBbox] = useState<string | null>(null);

  useEffect(() => {
    setLoadState("loading");
    const incidentParams = buildIncidentParams({
      bbox,
      incidentType,
      jurisdiction,
      sourceName,
      dateFrom,
      dateTo,
      category,
    });

    const eventParams = new URLSearchParams();
    if (bbox) eventParams.set("bbox", bbox);
    if (sourceType) eventParams.set("source_type", sourceType);
    if (officialOnly !== null)
      eventParams.set("official_only", String(officialOnly));
    const eventsUrl = `/api/map/events${eventParams.toString() ? `?${eventParams.toString()}` : ""}`;

    Promise.all([
      fetchCrimeIncidents(incidentParams),
      showEvents
        ? fetchJson<FeatureCollection>(eventsUrl)
        : Promise.resolve({
            type: "FeatureCollection" as const,
            features: [],
            returned_count: 0,
            truncated: false,
            filters_applied: {},
            disclaimer: "",
          }),
    ])
      .then(([inc, evt]) => {
        setIncidents(inc);
        setEvents(evt);
        setLoadState("idle");
      })
      .catch(() => setLoadState("error"));
  }, [
    bbox,
    category,
    dateFrom,
    dateTo,
    jurisdiction,
    showEvents,
    sourceName,
    officialOnly,
    sourceType,
    incidentType,
  ]);

  const handleReset = useCallback(() => {
    setJurisdiction("");
    setSourceName("");
    setDateFrom("");
    setDateTo("");
    setCategory("");
    setSourceType("");
    setOfficialOnly(null);
    setIncidentType("individual");
    setShowEvents(true);
  }, []);

  const handleSelect = useCallback((record: JudgeMapRecord) => {
    setSelectedRecord(record);
    setDrawerOpen(false); // show popup first; user clicks "View full record"
  }, []);

  const handleOpenDrawer = useCallback(() => {
    setDrawerOpen(true);
  }, []);

  const handleClosePopup = useCallback(() => {
    setSelectedRecord(null);
    setDrawerOpen(false);
  }, []);

  const handleCloseDrawer = useCallback(() => {
    setDrawerOpen(false);
  }, []);

  const totalRecords =
    (incidents?.returned_count ?? 0) + (events?.features.length ?? 0);

  return (
    <div className="flex flex-col h-[calc(100dvh-4rem)] min-h-0">
      {/* Route header */}
      <div className="shrink-0 flex flex-wrap items-start justify-between gap-2 px-3 py-2 md:px-4 border-b border-gray-200 bg-white">
        <div className="min-w-0">
          <h1 className="text-sm font-semibold text-gray-800">
            Public Records Map{" "}
            <span className="ml-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-100 text-indigo-600 align-middle">
              v2 · MapLibre
            </span>
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Showing publicly reviewed court events and reported incidents
          </p>
        </div>
        {loadState === "loading" && (
          <span className="text-xs text-gray-400 animate-pulse">
            Loading records…
          </span>
        )}
        {loadState === "error" && (
          <span className="text-xs text-red-500">
            Failed to load records — check API
          </span>
        )}
        {loadState === "idle" && (incidents || events) && (
          <span className="text-xs text-gray-500">
            {(incidents?.returned_count ?? 0) + (events?.features.length ?? 0)}{" "}
            records
          </span>
        )}
        <div className="w-full grid grid-cols-1 md:grid-cols-5 gap-2 mt-2">
          <input
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            placeholder="Jurisdiction (e.g. ON)"
            className="h-8 px-2 text-xs border border-gray-300 rounded"
          />
          <input
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
            placeholder="Source name"
            className="h-8 px-2 text-xs border border-gray-300 rounded"
          />
          <input
            type="date"
            title="Date from"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="h-8 px-2 text-xs border border-gray-300 rounded"
          />
          <input
            type="date"
            title="Date to"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="h-8 px-2 text-xs border border-gray-300 rounded"
          />
          <label className="h-8 px-2 text-xs border border-gray-300 rounded inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={showEvents}
              onChange={(e) => setShowEvents(e.target.checked)}
            />
            Show court events
          </label>
        </div>
        {/* Second filter row: source type, official-only, incident type, category, reviewed state, reset */}
        <div className="w-full flex flex-wrap items-center gap-2 mt-1">
          <input
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
            placeholder="Source type (e.g. court_records)"
            className="h-8 px-2 text-xs border border-gray-300 rounded"
          />
          <select
            title="Official sources filter"
            value={officialOnly === null ? "" : String(officialOnly)}
            onChange={(e) =>
              setOfficialOnly(
                e.target.value === "" ? null : e.target.value === "true",
              )
            }
            className="h-8 px-2 text-xs border border-gray-300 rounded bg-white"
          >
            <option value="">Official sources: any</option>
            <option value="true">Official only</option>
            <option value="false">Non-official only</option>
          </select>
          <select
            title="Incident type filter"
            value={incidentType}
            onChange={(e) =>
              setIncidentType(
                e.target.value as "individual" | "aggregate" | "all",
              )
            }
            className="h-8 px-2 text-xs border border-gray-300 rounded bg-white"
          >
            <option value="individual">Individual incidents</option>
            <option value="aggregate">Aggregate stats only</option>
            <option value="all">All incident types</option>
          </select>
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Category (e.g. violent)"
            className="h-8 px-2 text-xs border border-gray-300 rounded"
          />
          <span className="text-xs text-gray-500 bg-green-50 border border-green-200 rounded px-2 py-1">
            ✓ Reviewed records only
          </span>
          <button
            type="button"
            onClick={handleReset}
            className="h-8 px-3 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 text-gray-600 ml-auto"
          >
            Reset filters
          </button>
        </div>
        {/* Disclaimer footer */}
        {(() => {
          const { text, className } = getDisclaimer("map_legend");
          return <p className={`${className} w-full mt-1.5`}>{text}</p>;
        })()}
      </div>

      {/* Map + sidebar */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Map */}
        <div className="relative flex-1 min-h-0">
          <JudgeMapClient className="w-full h-full">
            <BoundsTracker onBoundsChange={setBbox} />
            <AutoFitToRecords incidents={incidents} events={events} />
            <JudgeClusterLayer
              incidents={incidents}
              events={events}
              onSelectRecord={handleSelect}
            />
            <JudgeMapControls />
            <JudgeMapLegend />
            <JudgeRelationshipArcs />
            {selectedRecord && !drawerOpen && (
              <JudgeMapPopup
                record={selectedRecord}
                onOpenDrawer={handleOpenDrawer}
                onClose={handleClosePopup}
              />
            )}
          </JudgeMapClient>
          {totalRecords === 1 && (
            <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center">
              <div className="relative">
                <div className="h-8 w-8 rounded-full border-4 border-white bg-blue-500 shadow-lg" />
                <div className="absolute left-1/2 top-1/2 h-14 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-blue-400/70" />
              </div>
            </div>
          )}
        </div>

        {/* Detail drawer sidebar */}
        {drawerOpen && selectedRecord && (
          <>
            <div className="hidden md:block w-96 shrink-0 overflow-y-auto border-l border-gray-200 bg-white">
              <JudgeMapDrawerBridge
                record={selectedRecord}
                onClose={handleCloseDrawer}
              />
            </div>
            <div className="md:hidden absolute inset-x-0 bottom-0 z-30 max-h-[72dvh] overflow-y-auto border-t border-gray-200 bg-white shadow-2xl rounded-t-xl">
              <JudgeMapDrawerBridge
                record={selectedRecord}
                onClose={handleCloseDrawer}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
