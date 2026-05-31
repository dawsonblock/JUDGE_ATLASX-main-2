"use client";

import { useEffect, useState } from "react";
import { MapDotRecord, RecordDetail, apiBase } from "@/lib/api";
import SourceLinks from "@/components/map/SourceLinks";
import { RelatedCourtRecords, RelatedIncidents } from "@/components/map/RelationshipWarnings";
import RecordAuditBadge from "@/components/map/RecordAuditBadge";
import { EvidenceChatPanel } from "@/components/crime-map/EvidenceChatPanel";
import { getDisclaimer } from "@/lib/disclaimerService";

type Tab = "overview" | "sources" | "related" | "news" | "audit" | "evidence";

type Props = {
  record: MapDotRecord | null;
  onClose: () => void;
};

function formatType(s: string | undefined) {
  return s ? s.replaceAll("_", " ") : "";
}

function SourceTierBadge({ tier }: { tier: string | undefined }) {
  if (!tier) return null;
  const tierColors: Record<string, string> = {
    court_record: "badge-court",
    official_police_open_data: "badge-official",
    official_government_statistics: "badge-official",
    verified_news_context: "badge-news",
    news_only_context: "badge-news",
  };
  return <span className={`source-tier-badge ${tierColors[tier] || "badge-default"}`}>{formatType(tier)}</span>;
}

function ReviewStatusBadge({ status }: { status: string | undefined }) {
  if (!status) return null;
  const statusColors: Record<string, string> = {
    verified_court_record: "status-verified",
    official_police_open_data_report: "status-verified",
    corrected: "status-verified",
    pending_review: "status-pending",
    disputed: "status-disputed",
    rejected: "status-rejected",
    removed_from_public: "status-rejected",
  };
  return <span className={`review-status-badge ${statusColors[status] || "status-pending"}`}>{formatType(status)}</span>;
}

function ConfidenceBadge({ confidence }: { confidence: number | undefined }) {
  if (confidence === undefined || confidence === null) return null;
  const level = confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low";
  return (
    <span className={`confidence-badge confidence-${level}`} title={`Confidence: ${(confidence * 100).toFixed(0)}%`}>
      {level === "high" ? "High" : level === "medium" ? "Medium" : "Low"} confidence
    </span>
  );
}

export default function MapRecordDrawer({ record, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [detail, setDetail] = useState<RecordDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const neutralDisclaimer = getDisclaimer("record_detail").text;
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!record) {
      setDetail(null);
      setError(null);
      return;
    }
    setDetail(null);
    setError(null);
    setLoading(true);
    setActiveTab("overview");
    const controller = new AbortController();
    fetch(
      `${apiBase(false)}/api/map/record/${record.record_type}/${record.id}`,
      { signal: controller.signal, headers: { Accept: "application/json" } },
    )
      .then((res) => {
        if (!res.ok) throw new Error(`Detail request failed (${res.status})`);
        return res.json() as Promise<RecordDetail>;
      })
      .then((data) => {
        setDetail(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Failed to load record details");
        setLoading(false);
      });
    return () => controller.abort();
  }, [record]);

  if (!record) return null;

  const isIncident = record.record_type === "reported_incident";
  const hasRelated = isIncident
    ? (detail?.related_court_records?.length ?? 0) > 0
    : (detail?.related_reported_incidents?.length ?? 0) > 0;

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "sources", label: "Sources" },
    ...(hasRelated ? [{ id: "related" as Tab, label: "Related Records" }] : []),
    ...(detail?.news_articles?.length ? [{ id: "news" as Tab, label: "News" }] : []),
    ...(isIncident ? [{ id: "evidence" as Tab, label: "Evidence" }] : []),
    { id: "audit", label: "Audit" },
  ];

  return (
    <div className="map-drawer" role="dialog" aria-label="Record details">
      <div className="map-drawer-header">
        <button className="map-drawer-close" onClick={onClose} aria-label="Close details panel" type="button">
          ✕
        </button>
        <div className="map-drawer-type">{isIncident ? "Reported Incident" : "Court Decision"}</div>
        <div className="map-drawer-title">
          {detail?.title ?? (isIncident ? formatType(detail?.incident_type) : "Loading…")}
        </div>
        {record.city ? (
          <div className="map-drawer-location">
            {record.city}
            {record.state_province ? `, ${record.state_province}` : ""}
          </div>
        ) : null}
        {record.date ? <div className="map-drawer-date">{record.date}</div> : null}
      </div>

      <nav className="map-drawer-tabs" aria-label="Record detail tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`map-drawer-tab${activeTab === t.id ? " active" : ""}`}
            onClick={() => setActiveTab(t.id)}
            type="button"
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="map-drawer-body">
        {loading ? (
          <p className="map-drawer-loading">Loading record details…</p>
        ) : error ? (
          <p className="map-drawer-error">{error}</p>
        ) : detail ? (
          <>
            {activeTab === "overview" && (
              <div className="map-drawer-section">
                {/* Source and Review Badges */}
                <div className="map-drawer-badges">
                  <SourceTierBadge tier={detail.source_tier ?? detail.source_quality} />
                  <ReviewStatusBadge status={detail.review_status ?? detail.audit?.review_status} />
                  <ConfidenceBadge confidence={detail.confidence} />
                </div>

                {/* Warnings Section */}
                {detail.warnings && detail.warnings.length > 0 && (
                  <div className="map-drawer-warnings">
                    <h4 className="warnings-title">Warnings</h4>
                    <ul className="warnings-list">
                      {detail.warnings.map((warning: string, idx: number) => (
                        <li key={idx} className="warning-item">{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {isIncident ? (
                  <>
                    <div className="map-drawer-field">
                      <span className="field-label">Type</span>
                      <span>{formatType(detail.incident_type)}</span>
                    </div>
                    <div className="map-drawer-field">
                      <span className="field-label">Category</span>
                      <span>{formatType(detail.category)}</span>
                    </div>
                    {detail.city ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Location</span>
                        <span>
                          {detail.city}
                          {detail.state_province ? `, ${detail.state_province}` : ""}
                          {detail.country ? `, ${detail.country}` : ""}
                        </span>
                      </div>
                    ) : null}
                    {detail.area_label ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Area</span>
                        <span>{detail.area_label}</span>
                      </div>
                    ) : null}
                    {detail.precision_level ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Precision</span>
                        <span>{formatType(detail.precision_level)}</span>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <>
                    {detail.event_type ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Decision type</span>
                        <span>{formatType(detail.event_type)}</span>
                      </div>
                    ) : null}
                    {detail.judge_name ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Judge</span>
                        <span>{detail.judge_name}</span>
                      </div>
                    ) : null}
                    {detail.court_name ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Court</span>
                        <span>{detail.court_name}</span>
                      </div>
                    ) : null}
                    {detail.court_location ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Location</span>
                        <span>{detail.court_location}</span>
                      </div>
                    ) : null}
                    {detail.case_name ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Case</span>
                        <span>{detail.case_name}</span>
                      </div>
                    ) : null}
                    {detail.docket_number ? (
                      <div className="map-drawer-field">
                        <span className="field-label">Docket</span>
                        <span>{detail.docket_number}</span>
                      </div>
                    ) : null}
                  </>
                )}
                {detail.date ? (
                  <div className="map-drawer-field">
                    <span className="field-label">Date</span>
                    <span>{detail.date}</span>
                  </div>
                ) : null}
                {detail.summary ? (
                  <div className="map-drawer-summary">{detail.summary}</div>
                ) : null}

                {/* Safety Disclaimer */}
                <div className="map-drawer-safety-disclaimer">
                  <p className="safety-text">
                    <strong>Source-linked record:</strong> {neutralDisclaimer}
                  </p>
                </div>

                <div className="map-drawer-disclaimer">{neutralDisclaimer}</div>
              </div>
            )}

            {activeTab === "sources" && (
              <div className="map-drawer-section">
                <h3 className="map-drawer-section-title">Official Sources</h3>
                <SourceLinks links={detail.source_links} />
                {detail.source_links.length === 0 && detail.news_articles.length > 0 ? (
                  <p className="map-drawer-note">{detail.news_context_note}</p>
                ) : null}
              </div>
            )}

            {activeTab === "related" && (
              <div className="map-drawer-section">
                <h3 className="map-drawer-section-title">Related Records</h3>
                {isIncident ? (
                  <RelatedCourtRecords records={detail.related_court_records} />
                ) : (
                  <RelatedIncidents incidents={detail.related_reported_incidents} />
                )}
                <p className="map-drawer-note">
                  Only verified source links represent actual relationships. Other entries are contextual only.
                </p>
              </div>
            )}

            {activeTab === "news" && (
              <div className="map-drawer-section">
                <h3 className="map-drawer-section-title">News Articles</h3>
                <SourceLinks links={detail.news_articles} />
                <p className="map-drawer-note">{detail.news_context_note}</p>
              </div>
            )}

            {activeTab === "audit" && (
              <div className="map-drawer-section">
                <h3 className="map-drawer-section-title">Publication Status</h3>
                <RecordAuditBadge audit={detail.audit} />
                <div className="map-drawer-disclaimer">{neutralDisclaimer}</div>
              </div>
            )}

            {activeTab === "evidence" && isIncident && (
              <div className="map-drawer-section">
                <EvidenceChatPanel incidentId={Number(record.id)} />
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
