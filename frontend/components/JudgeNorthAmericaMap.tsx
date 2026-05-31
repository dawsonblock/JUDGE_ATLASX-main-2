"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { CrimeIncidentFeatureCollection, FeatureCollection, MapDotRecord, RelationshipArcFeatureCollection, apiBase } from "@/lib/api";
import SourcePanel from "@/components/SourcePanel";
import MapRecordDrawer from "@/components/map/MapRecordDrawer";

type JudgeNorthAmericaMapProps = {
  apiBaseUrl?: string;
  eventType?: string;
  judgeId?: number | null;
  courtId?: number | null;
  verifiedOnly?: boolean;
  repeatOffenderOnly?: boolean;
  start?: string | null;
  end?: string | null;
};

function FitNorthAmerica() {
  const map = useMap();

  useEffect(() => {
    map.fitBounds(
      [
        [7, -170],
        [83, -52],
      ],
      { padding: [20, 20] },
    );
  }, [map]);

  return null;
}

function BoundsTracker({ onBoundsChange }: { onBoundsChange: (bbox: string) => void }) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function emitBounds(map: ReturnType<typeof useMap>) {
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
  }

  const map = useMapEvents({
    moveend() { emitBounds(map); },
    zoomend() { emitBounds(map); },
  });

  return null;
}

function getEventColor(eventType: string) {
  switch (eventType) {
    case "release_order":
    case "release_decision":
      return "#225ea8";
    case "bond_modification":
    case "bail_decision":
      return "#9a5b12";
    case "sentencing":
      return "#aa4b36";
    case "revocation":
      return "#6d4aa8";
    case "appeal_reversal":
    case "appeal_affirmance":
    case "appeal_remand":
    case "appeal_decision":
      return "#1f7a6d";
    default:
      return "#34454f";
  }
}

function formatEventType(eventType: string) {
  return eventType.replaceAll("_", " ");
}

function buildQuery(params: JudgeNorthAmericaMapProps) {
  const query = new URLSearchParams();
  if (params.eventType) query.set("event_type", params.eventType);
  if (params.judgeId) query.set("judge_id", String(params.judgeId));
  if (params.courtId) query.set("court_id", String(params.courtId));
  if (params.verifiedOnly) query.set("verified_only", "true");
  if (params.repeatOffenderOnly) query.set("repeat_offender_indicator", "true");
  if (params.start) query.set("start", params.start);
  if (params.end) query.set("end", params.end);
  return query.toString();
}

function buildCrimeQuery(range: string, bbox?: string) {
  const query = new URLSearchParams();
  if (range) query.set("last_hours", range);
  if (bbox) query.set("bbox", bbox);
  return query.toString();
}

export default function JudgeNorthAmericaMap({
  apiBaseUrl,
  eventType,
  judgeId,
  courtId,
  verifiedOnly,
  repeatOffenderOnly,
  start,
  end,
}: JudgeNorthAmericaMapProps) {
  const [data, setData] = useState<FeatureCollection | null>(null);
  const [crimeData, setCrimeData] = useState<CrimeIncidentFeatureCollection | null>(null);
  const [aggregateData, setAggregateData] = useState<CrimeIncidentFeatureCollection | null>(null);
  const [loading, setLoading] = useState(true);
  const [crimeLoading, setCrimeLoading] = useState(true);
  const [aggregateLoading, setAggregateLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [crimeErrorMessage, setCrimeErrorMessage] = useState<string | null>(null);
  const [aggregateErrorMessage, setAggregateErrorMessage] = useState<string | null>(null);
  const [showCourtDecisions, setShowCourtDecisions] = useState(true);
  const [showReportedIncidents, setShowReportedIncidents] = useState(true);
  const [showAggregateStats, setShowAggregateStats] = useState(false);
  const [showRelationshipArcs, setShowRelationshipArcs] = useState(false);
  const [arcData, setArcData] = useState<RelationshipArcFeatureCollection | null>(null);
  const [arcLoading, setArcLoading] = useState(false);
  const [arcErrorMessage, setArcErrorMessage] = useState<string | null>(null);
  const [crimeRange, setCrimeRange] = useState("720");
  const [boundsQuery, setBoundsQuery] = useState<string | undefined>(undefined);
  const [drawerRecord, setDrawerRecord] = useState<MapDotRecord | null>(null);
  const resolvedApiBase = apiBaseUrl ?? apiBase(false);

  function openRecordDetails(dot: MapDotRecord) {
    setDrawerRecord(dot);
  }
  const queryString = useMemo(
    () => {
      const base = buildQuery({ eventType, judgeId, courtId, verifiedOnly, repeatOffenderOnly, start, end });
      const params = new URLSearchParams(base);
      if (boundsQuery) params.set("bbox", boundsQuery);
      return params.toString();
    },
    [eventType, judgeId, courtId, verifiedOnly, repeatOffenderOnly, start, end, boundsQuery],
  );
  const crimeQueryString = useMemo(
    () => buildCrimeQuery(crimeRange, boundsQuery),
    [crimeRange, boundsQuery],
  );
  const aggregateQueryString = useMemo(
    () => buildCrimeQuery(crimeRange, boundsQuery), // Same params, different endpoint
    [crimeRange, boundsQuery],
  );

  useEffect(() => {
    const controller = new AbortController();

    async function loadMapEvents() {
      setLoading(true);
      setErrorMessage(null);
      const url = `${resolvedApiBase}/api/map/events${queryString ? `?${queryString}` : ""}`;
      // bbox is already embedded in queryString via boundsQuery

      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Map request failed with status ${response.status}`);
        }
        setData((await response.json()) as FeatureCollection);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setErrorMessage(error instanceof Error ? error.message : "Map request failed");
      } finally {
        setLoading(false);
      }
    }

    loadMapEvents();
    return () => controller.abort();
  }, [queryString, resolvedApiBase]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadCrimeIncidents() {
      setCrimeLoading(true);
      setCrimeErrorMessage(null);
      // Fetch only individual incidents (exclude aggregates)
      const url = `${resolvedApiBase}/api/map/crime-incidents?exclude_aggregate=true${crimeQueryString ? `&${crimeQueryString}` : ""}`;

      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Crime incident request failed with status ${response.status}`);
        }
        setCrimeData((await response.json()) as CrimeIncidentFeatureCollection);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setCrimeErrorMessage(error instanceof Error ? error.message : "Crime incident request failed");
      } finally {
        setCrimeLoading(false);
      }
    }

    loadCrimeIncidents();
    return () => controller.abort();
  }, [crimeQueryString, resolvedApiBase]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadAggregates() {
      if (!showAggregateStats) return; // Skip fetch if not showing
      setAggregateLoading(true);
      setAggregateErrorMessage(null);
      // Fetch only aggregates from separate endpoint
      const url = `${resolvedApiBase}/api/map/crime-aggregates${aggregateQueryString ? `?${aggregateQueryString}` : ""}`;

      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Aggregate request failed with status ${response.status}`);
        }
        setAggregateData((await response.json()) as CrimeIncidentFeatureCollection);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setAggregateErrorMessage(error instanceof Error ? error.message : "Aggregate request failed");
      } finally {
        setAggregateLoading(false);
      }
    }

    loadAggregates();
    return () => controller.abort();
  }, [aggregateQueryString, resolvedApiBase, showAggregateStats]); // Refetch when toggle changes

  useEffect(() => {
    const controller = new AbortController();

    async function loadRelationshipArcs() {
      if (!showRelationshipArcs) return;
      setArcLoading(true);
      setArcErrorMessage(null);
      const url = `${resolvedApiBase}/api/map/relationship-arcs`;

      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Relationship arc request failed with status ${response.status}`);
        }
        setArcData((await response.json()) as RelationshipArcFeatureCollection);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setArcErrorMessage(error instanceof Error ? error.message : "Relationship arc request failed");
      } finally {
        setArcLoading(false);
      }
    }

    loadRelationshipArcs();
    return () => controller.abort();
  }, [resolvedApiBase, showRelationshipArcs]);

  const featureCount = data?.features.length ?? 0;
  const crimeFeatureCount = crimeData?.features.length ?? 0;
  const aggregateFeatureCount = aggregateData?.features.length ?? 0;
  const arcFeatureCount = arcData?.features.length ?? 0;

  return (
    <section className="north-america-map">
      <div className="map-panel-header">
        <div>
          <h2>North America Public Record Map</h2>
          <p>Court decisions and recent reported crime incidents are separate layers. Private defendant locations are not mapped.</p>
        </div>
        <div className="map-count">
          {loading ? "Loading court decisions..." : `${featureCount} court event${featureCount === 1 ? "" : "s"}`}
          <br />
          {crimeLoading ? "Loading incidents..." : `${crimeFeatureCount} incident${crimeFeatureCount === 1 ? "" : "s"}`}
          {aggregateLoading ? " / Loading aggregates..." : showAggregateStats ? ` / ${aggregateFeatureCount} aggregate${aggregateFeatureCount === 1 ? "" : "s"}` : ""}
          {arcLoading ? " / Loading arcs..." : showRelationshipArcs ? ` / ${arcFeatureCount} arc${arcFeatureCount === 1 ? "" : "s"}` : ""}
        </div>
      </div>
      <div className="map-layer-controls" aria-label="Map layer controls">
        <label className="toggle-row">
          <input type="checkbox" checked={showCourtDecisions} onChange={(event) => setShowCourtDecisions(event.target.checked)} />
          Court Decisions
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={showReportedIncidents} onChange={(event) => setShowReportedIncidents(event.target.checked)} />
          Incident Dots
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={showAggregateStats} onChange={(event) => setShowAggregateStats(event.target.checked)} />
          Aggregate Stats
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={showRelationshipArcs} onChange={(event) => setShowRelationshipArcs(event.target.checked)} />
          Relationship Arcs
        </label>
        <label className="toggle-row muted-toggle" title="Heatmap rendering is planned for a later phase.">
          <input type="checkbox" disabled />
          Heatmap planned
        </label>
        <div className="field compact-field">
          <label htmlFor="crime-range">Reported incidents</label>
          <select id="crime-range" value={crimeRange} onChange={(event) => setCrimeRange(event.target.value)}>
            <option value="24">Last 24 hours</option>
            <option value="168">Last 7 days</option>
            <option value="720">Last 30 days</option>
          </select>
        </div>
      </div>
      {errorMessage ? <div className="map-error">Map failed to load: {errorMessage}</div> : null}
      {crimeErrorMessage ? <div className="map-error">Reported incidents layer failed to load: {crimeErrorMessage}</div> : null}
      {aggregateErrorMessage ? <div className="map-error">Aggregate stats layer failed to load: {aggregateErrorMessage}</div> : null}
      {arcErrorMessage ? <div className="map-error">Relationship arc layer failed to load: {arcErrorMessage}</div> : null}
      <div className="north-america-map-canvas">
        <MapContainer center={[39, -98]} zoom={3} minZoom={2} maxZoom={12} scrollWheelZoom className="map-fill">
          <FitNorthAmerica />
          <BoundsTracker onBoundsChange={setBoundsQuery} />
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          {showCourtDecisions && data?.features.map((feature) => {
            const [longitude, latitude] = feature.geometry.coordinates;
            const p = feature.properties;
            const color = getEventColor(p.event_type);
            return (
              <CircleMarker
                key={p.event_id}
                center={[latitude, longitude]}
                radius={8}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.82,
                  weight: 1,
                }}
              >
                <Popup>
                  <div className="map-popup">
                    <div className="map-popup-title">{p.title}</div>
                    {p.judge_name ? <div><strong>Judge:</strong> {p.judge_name}</div> : null}
                    <div><strong>Event:</strong> {formatEventType(p.event_type)}</div>
                    {p.event_date ? <div><strong>Date:</strong> {p.event_date}</div> : null}
                    {p.court_name ? <div><strong>Court:</strong> {p.court_name}</div> : null}
                    <div><strong>Location:</strong> {p.location_name}</div>
                    {p.case_name ? <div><strong>Case:</strong> {p.case_name}</div> : null}
                    {p.case_number ? <div><strong>Docket:</strong> {p.case_number}</div> : null}
                    <div><strong>Verified:</strong> {p.verified_flag ? "Yes" : "No"}</div>
                    <div><strong>Review:</strong> {p.review_status.replaceAll("_", " ")}</div>
                    {p.repeat_offender_indicator ? (
                      <div className="map-popup-note">Repeat-offender indicator detected. This is not a legal conclusion.</div>
                    ) : null}
                    <button
                      className="map-popup-details-btn"
                      type="button"
                      onClick={() => openRecordDetails({
                        id: p.event_id,
                        record_type: "court_event",
                        latitude,
                        longitude,
                        title: p.title,
                        date: p.event_date,
                        city: p.location_name,
                        source_count: p.source_count ?? 0,
                        has_news: p.has_news ?? false,
                        disclaimer: p.disclaimer ?? "",
                      })}
                    >
                      View details
                    </button>
                    <SourcePanel entityType="event" entityId={p.event_id} compact />
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
          {showReportedIncidents && crimeData?.features.map((feature) => {
            const [longitude, latitude] = feature.geometry.coordinates;
            const p = feature.properties;
            return (
              <CircleMarker
                key={`crime-${p.incident_id}`}
                center={[latitude, longitude]}
                radius={5}
                pathOptions={{
                  color: "#6f4a8e",
                  fillColor: "#6f4a8e",
                  fillOpacity: 0.42,
                  opacity: 0.72,
                  weight: 1,
                }}
              >
                <Popup>
                  <div className="map-popup">
                    <div className="map-popup-title">Reported Incident</div>
                    <div className="map-popup-status">Reported incident, not adjudicated.</div>
                    <div><strong>Type:</strong> {p.incident_type}</div>
                    {p.reported_at ? <div><strong>Reported:</strong> {p.reported_at.slice(0, 10)}</div> : null}
                    <div><strong>Area:</strong> {p.area_label || p.city || "General area"}</div>
                    <div><strong>Source:</strong> {p.source_url ? <a href={p.source_url} target="_blank" rel="noreferrer">{p.source_name}</a> : p.source_name}</div>
                    <div><strong>Precision:</strong> {p.precision_level.replaceAll("_", " ")}</div>
                    <div><strong>Status:</strong> {p.verification_status.replaceAll("_", " ")}</div>
                    <div className="map-popup-note">{p.disclaimer}</div>
                    <button
                      className="map-popup-details-btn"
                      type="button"
                      onClick={() => openRecordDetails({
                        id: p.incident_id,
                        record_type: "reported_incident",
                        latitude,
                        longitude,
                        title: p.incident_type,
                        date: p.occurred_at ? p.occurred_at.slice(0, 10) : (p.reported_at ? p.reported_at.slice(0, 10) : null),
                        city: p.city,
                        state_province: p.province_state,
                        source_count: p.source_count ?? 0,
                        has_news: p.has_news ?? false,
                        disclaimer: p.disclaimer,
                      })}
                    >
                      View details
                    </button>
                    <SourcePanel entityType="crime_incident" entityId={p.incident_id} compact />
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
          {showAggregateStats && aggregateData?.features.map((feature) => {
            const [longitude, latitude] = feature.geometry.coordinates;
            const p = feature.properties;
            return (
              <CircleMarker
                key={`agg-${p.incident_id}`}
                center={[latitude, longitude]}
                radius={14}
                pathOptions={{
                  color: "#888",
                  fillColor: "#b0b8c1",
                  fillOpacity: 0.28,
                  opacity: 0.55,
                  weight: 1,
                  dashArray: "4 3",
                }}
              >
                <Popup>
                  <div className="map-popup">
                    <div className="map-popup-title">Aggregate Statistic</div>
                    <div className="map-popup-status">Regional aggregate — not an individual incident.</div>
                    <div><strong>Category:</strong> {p.incident_type}</div>
                    <div><strong>Area:</strong> {p.area_label || p.province_state || p.country || "Region"}</div>
                    <div><strong>Source:</strong> {p.source_url ? <a href={p.source_url} target="_blank" rel="noreferrer">{p.source_name}</a> : p.source_name}</div>
                    <div className="map-popup-note">{p.disclaimer}</div>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
          {showRelationshipArcs && arcData?.features.map((feature) => {
            const [[lon1, lat1], [lon2, lat2]] = feature.geometry.coordinates;
            const p = feature.properties;
            return (
              <Polyline
                key={`arc-${p.edge_id}`}
                positions={[[lat1, lon1], [lat2, lon2]]}
                pathOptions={{
                  color: "#e06c00",
                  weight: 2,
                  opacity: 0.65,
                  dashArray: "6 4",
                }}
              >
                <Popup>
                  <div className="map-popup">
                    <div className="map-popup-title">Relationship Arc</div>
                    <div><strong>Predicate:</strong> {p.predicate.replaceAll("_", " ")}</div>
                    <div><strong>Subject:</strong> {p.subject_type} #{p.subject_id}</div>
                    <div><strong>Object:</strong> {p.object_type} #{p.object_id}</div>
                    {p.valid_from ? <div><strong>From:</strong> {p.valid_from.slice(0, 10)}</div> : null}
                    {p.valid_until ? <div><strong>Until:</strong> {p.valid_until.slice(0, 10)}</div> : null}
                  </div>
                </Popup>
              </Polyline>
            );
          })}
        </MapContainer>
      </div>
      <div className="map-legend" aria-label="Map legend">
        <span><span className="legend-dot legend-dot-release" />Release order</span>
        <span><span className="legend-dot legend-dot-sentencing" />Sentencing</span>
        <span><span className="legend-dot legend-dot-revocation" />Revocation</span>
        <span><span className="legend-dot legend-dot-appeal" />Appeal</span>
        <span><span className="legend-dot legend-dot-other" />Other court event</span>
        <span><span className="legend-dot legend-dot-incident" />Reported incident</span>
        <span><span className="legend-dot-agg" />Aggregate stat (hidden by default)</span>
        <span><span className="legend-arc" />Relationship arc (hidden by default)</span>
      </div>
      <div className="map-disclaimer">
        Court events use courthouse or jurisdiction locations — never personal addresses. Reported incident locations are generalized public areas. Aggregate statistics are regional counts, not individual incidents. Records may change due to reclassification, correction, or unfounded reports. These layers are not legally linked to each other.
      </div>
      <MapRecordDrawer record={drawerRecord} onClose={() => setDrawerRecord(null)} />
    </section>
  );
}
