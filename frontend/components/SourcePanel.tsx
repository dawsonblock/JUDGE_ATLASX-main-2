"use client";

import { useState } from "react";
import { SourcePanelData, apiBase } from "@/lib/api";

type SourcePanelProps = {
  entityType: "event" | "crime_incident" | "source";
  entityId: string | number;
  compact?: boolean;
};

function formatStatus(status: string | null | undefined) {
  return status ? status.replaceAll("_", " ") : "status pending";
}

export default function SourcePanel({ entityType, entityId, compact = false }: SourcePanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [data, setData] = useState<SourcePanelData | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function loadPanel() {
    if (data || loading) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const response = await fetch(`${apiBase(false)}/api/evidence/source-panel/${entityType}/${entityId}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Source panel unavailable (${response.status})`);
      }
      setData((await response.json()) as SourcePanelData);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Source panel unavailable");
    } finally {
      setLoading(false);
    }
  }

  function toggleOpen() {
    const nextOpen = !isOpen;
    setIsOpen(nextOpen);
    if (nextOpen) void loadPanel();
  }

  return (
    <div className={`source-panel ${compact ? "compact-source-panel" : ""}`}>
      <button className="source-panel-toggle" type="button" onClick={toggleOpen} aria-expanded={isOpen}>
        {isOpen ? "Hide source panel" : "Show source panel"}
      </button>
      {isOpen ? (
        <div className="source-panel-body">
          {loading ? <p>Loading evidence sources...</p> : null}
          {errorMessage ? <p className="source-panel-error">{errorMessage}</p> : null}
          {data ? (
            <>
              <div className="source-panel-status">Review status: {formatStatus(data.review_status)}</div>
              {data.sources.length ? (
                data.sources.map((source, index) => (
                  <article className="source-panel-item" key={`${source.source_url || source.source_name}-${index}`}>
                    <div className="source-panel-title">{source.source_name}</div>
                    <div className="source-panel-meta">
                      {formatStatus(source.source_type)} · {formatStatus(source.verification_status)}
                    </div>
                    {source.source_url ? (
                      <a className="source-panel-link" href={source.source_url} target="_blank" rel="noreferrer">
                        Open source
                      </a>
                    ) : null}
                    {source.quoted_excerpt ? <p>Evidence excerpt: {source.quoted_excerpt}</p> : null}
                    <p>{source.trust_reason}</p>
                    <p>
                      Retrieved: {source.retrieved_at ? source.retrieved_at.slice(0, 10) : "date pending"} · Published:{" "}
                      {source.published_at ? source.published_at.slice(0, 10) : "date pending"}
                    </p>
                    <p>
                      Reviewed by {source.reviewed_by || "review pending"} · {source.reviewed_at ? source.reviewed_at.slice(0, 10) : "not reviewed"}
                    </p>
                  </article>
                ))
              ) : (
                <p>No public source links are available for this record yet.</p>
              )}
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
