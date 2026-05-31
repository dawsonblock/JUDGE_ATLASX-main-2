/**
 * Live Feed Panel component.
 *
 * This component displays a live feed of legal events with filtering,
 * admin actions, and map integration. It adapts the useful part of the
 * Shadowbroker NewsFeed pattern but narrows it for the legal domain.
 */

"use client";

import { useState, useEffect } from "react";
import { useLiveMapPolling, GeoLegalEvent } from "@/hooks/useLiveMapPolling";
import { format } from "date-fns";

interface LiveFeedPanelProps {
  adminMode?: boolean;
  onEventSelect?: (event: GeoLegalEvent) => void;
  onOpenEvidence?: (event: GeoLegalEvent) => void;
  onApprove?: (eventId: string) => void;
  onReject?: (eventId: string) => void;
  onSendToReview?: (eventId: string) => void;
  onMarkDuplicate?: (eventId: string) => void;
  onMarkContradiction?: (eventId: string) => void;
  onOpenSourceSnapshot?: (event: GeoLegalEvent) => void;
}

export function LiveFeedPanel({
  adminMode = false,
  onEventSelect,
  onOpenEvidence,
  onApprove,
  onReject,
  onSendToReview,
  onMarkDuplicate,
  onMarkContradiction,
  onOpenSourceSnapshot,
}: LiveFeedPanelProps) {
  const [filter, setFilter] = useState({
    eventType: "all",
    minConfidence: 0.0,
    jurisdiction: "all",
  });
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  const {
    events,
    feedStatus,
    isLoading,
    error,
    lastUpdate,
    isStale,
    refresh,
    pause,
    resume,
  } = useLiveMapPolling({
    enabled: true,
    interval: 45000, // 45 seconds
    adminMode,
  });

  // Filter events
  const filteredEvents = events.filter((event) => {
    if (filter.eventType !== "all" && event.event_type !== filter.eventType) {
      return false;
    }
    if (event.confidence < filter.minConfidence) {
      return false;
    }
    if (filter.jurisdiction !== "all" && event.jurisdiction !== filter.jurisdiction) {
      return false;
    }
    return true;
  });

  // Sort by occurred_at descending
  const sortedEvents = [...filteredEvents].sort((a, b) => {
    if (!a.occurred_at) return 1;
    if (!b.occurred_at) return -1;
    return new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime();
  });

  // Show only top 50 events
  const displayEvents = sortedEvents.slice(0, 50);

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return "text-green-600";
    if (confidence >= 0.5) return "text-yellow-600";
    return "text-red-600";
  };

  const getReviewStatusColor = (status: string) => {
    switch (status) {
      case "approved":
        return "bg-green-100 text-green-800";
      case "needs_review":
        return "bg-yellow-100 text-yellow-800";
      case "rejected":
        return "bg-red-100 text-red-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  const getEventTypeLabel = (eventType: string) => {
    const labels: Record<string, string> = {
      court_event: "Court",
      judge_event: "Judge",
      crime_event: "Crime",
      police_release: "Police",
      news_event: "News",
      legislation_event: "Legislation",
      statistical_event: "Statistics",
      correction_event: "Correction",
      contradiction_event: "Contradiction",
    };
    return labels[eventType] || eventType;
  };

  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200">
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Live Feed</h2>
          <div className="flex items-center gap-2">
            {isStale && (
              <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">
                Stale Data
              </span>
            )}
            <button
              onClick={refresh}
              disabled={isLoading}
              className="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
            >
              {isLoading ? "Loading..." : "Refresh"}
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-2 mb-2">
          <select
            value={filter.eventType}
            onChange={(e) => setFilter({ ...filter, eventType: e.target.value })}
            className="px-2 py-1 text-sm border border-gray-300 rounded"
          >
            <option value="all">All Types</option>
            <option value="court_event">Court Events</option>
            <option value="crime_event">Crime Events</option>
            <option value="news_event">News Events</option>
            <option value="legislation_event">Legislation</option>
            <option value="contradiction_event">Contradictions</option>
          </select>

          <select
            value={filter.minConfidence.toString()}
            onChange={(e) =>
              setFilter({ ...filter, minConfidence: parseFloat(e.target.value) })
            }
            className="px-2 py-1 text-sm border border-gray-300 rounded"
          >
            <option value="0">All Confidence</option>
            <option value="0.8">High (≥80%)</option>
            <option value="0.5">Medium (≥50%)</option>
          </select>
        </div>

        {/* Stats */}
        {feedStatus && (
          <div className="text-xs text-gray-600">
            {feedStatus.total_events} total events • {feedStatus.public_events} public •{" "}
            {feedStatus.needs_review} need review
          </div>
        )}

        {!adminMode && (
          <div className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
            Live feed polling is available in admin mode only.
          </div>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 bg-red-50 border-b border-red-200">
          <p className="text-sm text-red-600">Error: {error.message}</p>
        </div>
      )}

      {/* Feed content */}
      <div className="flex-1 overflow-y-auto">
        {displayEvents.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            <p>No events match your filters</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {displayEvents.map((event) => (
              <div
                key={event.id}
                className={`p-3 hover:bg-gray-50 cursor-pointer ${
                  expandedEventId === event.id ? "bg-blue-50" : ""
                }`}
                onClick={() => {
                  setExpandedEventId(
                    expandedEventId === event.id ? null : event.id
                  );
                  onEventSelect?.(event);
                }}
              >
                {/* Event row */}
                <div className="flex items-start gap-3">
                  {/* Timestamp */}
                  <div className="text-xs text-gray-500 w-24 flex-shrink-0">
                    {event.occurred_at
                      ? format(new Date(event.occurred_at), "MMM d, HH:mm")
                      : "Unknown"}
                  </div>

                  {/* Event type badge */}
                  <div className="flex-shrink-0">
                    <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-800 rounded">
                      {getEventTypeLabel(event.event_type)}
                    </span>
                  </div>

                  {/* Event details */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">
                      {event.title}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`text-xs ${getConfidenceColor(
                          event.confidence
                        )}`}
                      >
                        {Math.round(event.confidence * 100)}% confidence
                      </span>
                      <span
                        className={`px-1.5 py-0.5 text-xs rounded ${getReviewStatusColor(
                          event.review_status
                        )}`}
                      >
                        {event.review_status}
                      </span>
                      {event.location_name && (
                        <span className="text-xs text-gray-600">
                          {event.location_name}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-1 flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onEventSelect?.(event);
                      }}
                      className="p-1 text-gray-500 hover:text-blue-600"
                      title="Open on map"
                    >
                      📍
                    </button>
                    {adminMode && (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenEvidence?.(event);
                          }}
                          className="p-1 text-gray-500 hover:text-blue-600"
                          title="View evidence"
                        >
                          📄
                        </button>
                        {event.review_status === "needs_review" && (
                          <>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onApprove?.(event.id);
                              }}
                              className="p-1 text-gray-500 hover:text-green-600"
                              title="Approve"
                            >
                              ✓
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onReject?.(event.id);
                              }}
                              className="p-1 text-gray-500 hover:text-red-600"
                              title="Reject"
                            >
                              ✗
                            </button>
                          </>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {/* Expanded details */}
                {expandedEventId === event.id && (
                  <div className="mt-3 pt-3 border-t border-gray-200">
                    <div className="text-sm text-gray-700 mb-2">
                      {event.description}
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="text-gray-600">
                        {event.source_ids.length} source(s)
                      </span>
                      <span className="text-gray-600">
                        {event.evidence_ids.length} evidence item(s)
                      </span>
                      <span className="text-gray-600">
                        {event.claim_ids.length} claim(s)
                      </span>
                      {event.tags.length > 0 && (
                        <span className="text-gray-600">
                          Tags: {event.tags.join(", ")}
                        </span>
                      )}
                    </div>
                    {adminMode && (
                      <div className="flex gap-2 mt-3">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSendToReview?.(event.id);
                          }}
                          className="px-2 py-1 text-xs bg-yellow-500 text-white rounded hover:bg-yellow-600"
                        >
                          Send to Review
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onMarkDuplicate?.(event.id);
                          }}
                          className="px-2 py-1 text-xs bg-gray-500 text-white rounded hover:bg-gray-600"
                        >
                          Mark Duplicate
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onMarkContradiction?.(event.id);
                          }}
                          className="px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600"
                        >
                          Mark Contradiction
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenSourceSnapshot?.(event);
                          }}
                          className="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600"
                        >
                          Open Source Snapshot
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-2 border-t border-gray-200 text-xs text-gray-500">
        {lastUpdate ? (
          <span>Last updated: {format(lastUpdate, "HH:mm:ss")}</span>
        ) : (
          <span>Waiting for update...</span>
        )}
      </div>
    </div>
  );
}
