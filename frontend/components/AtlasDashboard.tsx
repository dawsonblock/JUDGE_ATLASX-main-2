"use client";

import { Calendar, FileText, Filter, Gavel, MapPin, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { EventItem, apiBase } from "@/lib/api";
import SourcePanel from "@/components/SourcePanel";

type Filters = {
  event_type: string;
  repeat_offender_indicator: string;
  verified_only: boolean;
  source_type: string;
  start: string;
  end: string;
};

const eventTypes = [
  "detention_order",
  "release_order",
  "sentencing",
  "revocation",
  "appeal_reversal",
  "indictment",
  "motion_to_suppress",
  "news_coverage",
];

function buildQuery(filters: Filters) {
  const params = new URLSearchParams();
  if (filters.event_type) params.set("event_type", filters.event_type);
  if (filters.repeat_offender_indicator) params.set("repeat_offender_indicator", filters.repeat_offender_indicator);
  if (filters.verified_only) params.set("verified_only", "true");
  if (filters.source_type) params.set("source_type", filters.source_type);
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  return params.toString();
}


export default function AtlasDashboard() {
  const [filters, setFilters] = useState<Filters>({
    event_type: "",
    repeat_offender_indicator: "",
    verified_only: false,
    source_type: "",
    start: "",
    end: "",
  });
  const [events, setEvents] = useState<EventItem[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const selected = events.find((event) => event.event_id === selectedEventId) || events[0];

  useEffect(() => {
    const query = buildQuery(filters);
    const nextUrl = query ? `/?${query}` : "/";
    window.history.replaceState(null, "", nextUrl);
    async function load() {
      const res = await fetch(`${apiBase(false)}/api/events${query ? `?${query}` : ""}`);
      if (!res.ok) throw new Error(`API error: events=${res.status}`);
      const eventsResponse = (await res.json()) as EventItem[];
      setEvents(eventsResponse);
      setSelectedEventId((current) => {
        if (current && eventsResponse.some((event) => event.event_id === current)) return current;
        return eventsResponse[0]?.event_id || null;
      });
    }
    load().catch((err: unknown) => console.error(err));
  }, [filters]);

  function updateFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <main className="dashboard">
      <aside className="rail">
        <section className="section">
          <h2><Filter size={15} /> Filters</h2>
          <p>Court-event filters map courts, jurisdictions, cases, and verified legal events.</p>
          <div className="filter-grid">
            <div className="field">
              <label htmlFor="event-type">Decision type</label>
              <select id="event-type" value={filters.event_type} onChange={(event) => updateFilter("event_type", event.target.value)}>
                <option value="">All linked legal events</option>
                {eventTypes.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="source-type">Source</label>
              <select id="source-type" value={filters.source_type} onChange={(event) => updateFilter("source_type", event.target.value)}>
                <option value="">All sources</option>
                <option value="court_record">Court record</option>
                <option value="court_order">Court order</option>
                <option value="appeal_decision">Appeal decision</option>
                <option value="official_statement">Official statement</option>
                <option value="news">News secondary context</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="repeat">Repeat-offender indicators</label>
              <select id="repeat" value={filters.repeat_offender_indicator} onChange={(event) => updateFilter("repeat_offender_indicator", event.target.value)}>
                <option value="">Any</option>
                <option value="true">Present</option>
                <option value="false">Not present</option>
              </select>
            </div>
            <label className="toggle-row">
              <input type="checkbox" checked={filters.verified_only} onChange={(event) => updateFilter("verified_only", event.target.checked)} />
              Verified records only
            </label>
            <div className="field">
              <label htmlFor="start">Start</label>
              <input id="start" type="date" value={filters.start} onChange={(event) => updateFilter("start", event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="end">End</label>
              <input id="end" type="date" value={filters.end} onChange={(event) => updateFilter("end", event.target.value)} />
            </div>
          </div>
        </section>
        <section className="section">
          <h3>Recent events</h3>
          <div className="event-list">
            {events.length ? (
              events.slice(0, 8).map((event) => (
                <button className={`event-row ${event.event_id === selected?.event_id ? "active" : ""}`} key={event.event_id} onClick={() => setSelectedEventId(event.event_id)}>
                  <div className="kicker">{event.event_type.replaceAll("_", " ")}</div>
                  <div className="row-title">{event.title}</div>
                  <div className="meta">{event.decision_date || "No decision date"} · {event.defendants.map((d) => d.display_label).join(", ") || "No defendant label linked"}</div>
                </button>
              ))
            ) : (
              <p>No linked legal events match the current filters.</p>
            )}
          </div>
        </section>
      </aside>

      <section className="map-wrap">
        <div className="map-summary-card">
          <div className="map-summary-stat">
            <MapPin size={20} />
            <span>{events.length} court events</span>
          </div>
          <p className="map-summary-hint">
            Showing linked courthouse locations and jurisdictions.
          </p>
          <a href="/map" className="btn-map-link">
            Open Interactive Map →
          </a>
        </div>
      </section>

      <aside className="detail">
        {selected ? (
          <>
            <section className="section">
              <div className="kicker">{selected.event_type.replaceAll("_", " ")}</div>
              <h1 className="detail-title">{selected.title}</h1>
              <div className="badge-line">
                {selected.verified_flag && <span className="badge verified"><ShieldCheck size={13} /> verified outcome source</span>}
                {selected.repeat_offender_indicator && <span className="badge warn">repeat-offender indicator</span>}
                <span className="badge">{selected.review_status.replaceAll("_", " ")}</span>
                <span className="badge"><Calendar size={13} /> {selected.decision_date || "date pending"}</span>
                {!selected.is_mappable && <span className="badge">court location pending</span>}
              </div>
            </section>
            <section className="section">
              <h3>Linked legal event</h3>
              <p className="detail-summary">{selected.summary}</p>
              {selected.source_excerpt && <p>Evidence excerpt: {selected.source_excerpt}</p>}
              {selected.repeat_offender_indicators.length > 0 && <p>Indicator terms: {selected.repeat_offender_indicators.join(", ")}. This is not a verified repeat-offender finding.</p>}
              {selected.verification_status && <p>Verification status: {selected.verification_status.replaceAll("_", " ")}</p>}
              {selected.location_status === "court_location_pending" && <p>This event is listed but not mapped because courthouse coordinates are pending.</p>}
              <p>{selected.outcomes.length ? selected.outcomes.map((outcome) => outcome.summary).join(" ") : selected.outcome_status}</p>
            </section>
            <section className="section">
              <h3><Gavel size={15} /> Court and judge</h3>
              <p>{selected.court?.name}</p>
              <p>{selected.judge?.name || "Judge not linked"}</p>
            </section>
            <section className="section">
              <h3>Defendant labels</h3>
              <div className="badge-line">
                {selected.defendants.map((defendant) => <span className="badge" key={defendant.id}>{defendant.display_label}</span>)}
              </div>
            </section>
            <section className="section">
              <h3><FileText size={15} /> Sources</h3>
              {selected.sources.map((source) => (
                <p key={source.id}><a href={source.url}>{source.title}</a> · {source.source_type} · {source.review_status.replaceAll("_", " ")}</p>
              ))}
              <SourcePanel entityType="event" entityId={selected.event_id} />
            </section>
          </>
        ) : (
          <section className="section"><p>No events match the current filters.</p></section>
        )}
      </aside>
    </main>
  );
}
