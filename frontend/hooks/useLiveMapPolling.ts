/**
 * Live polling hook for admin live-map data.
 *
 * This hook polls admin live-map events only. Public live-map routes were
 * intentionally unmounted during boundary hardening.
 */

import { useState, useEffect, useCallback, useRef } from "react";

export interface LiveMapEventsResponse {
  returned_count: number;
  truncated: boolean;
  filters_applied: Record<string, any>;
  disclaimer: string;
  events: GeoLegalEvent[];
}

export interface GeoLegalEvent {
  id: string;
  event_type: string;
  title: string;
  description: string | null;
  lat: number | null;
  lng: number | null;
  location_name: string | null;
  occurred_at: string | null;
  published_at: string | null;
  jurisdiction: string;
  province: string | null;
  country: string;
  source_ids: string[];
  evidence_ids: string[];
  claim_ids: string[];
  confidence: number;
  confidence_label: string;
  review_status: string;
  publish_status: string;
  tags: string[];
  metadata: Record<string, any>;
}

export interface FeedStatusResponse {
  feed_status: string;
  total_events: number;
  public_events: number;
  approved_events: number;
  needs_review: number;
  contradicted: number;
  confidence_distribution: {
    high: number;
    medium: number;
    low: number;
  };
  last_updated: string;
  disclaimer: string;
}

export interface SourceHealthResponse {
  sources: Array<{
    source_id: string;
    source_type: string;
    title: string;
    lifecycle_state: string;
    is_active: boolean;
    automation_status: string;
    last_ingested_at: string | null;
  }>;
  total_sources: number;
  active_sources: number;
  disclaimer: string;
}

export interface PollingOptions {
  enabled?: boolean;
  interval?: number;
  bbox?: string;
  eventType?: string;
  jurisdiction?: string;
  province?: string;
  minConfidence?: number;
  reviewStatus?: string;
  publishStatus?: string;
  adminMode?: boolean;
}

export interface PollingState {
  events: GeoLegalEvent[];
  feedStatus: FeedStatusResponse | null;
  sourceHealth: SourceHealthResponse | null;
  isLoading: boolean;
  error: Error | null;
  lastUpdate: Date | null;
  isStale: boolean;
}

const DEFAULT_INTERVALS = {
  events: 45000, // 45 seconds
};

const STALE_THRESHOLD = 120000; // 2 minutes without update = stale

export function useLiveMapPolling(options: PollingOptions = {}) {
  const {
    enabled = true,
    interval = DEFAULT_INTERVALS.events,
    bbox,
    eventType,
    jurisdiction,
    province,
    minConfidence,
    reviewStatus,
    publishStatus,
    adminMode = false,
  } = options;

  const [state, setState] = useState<PollingState>({
    events: [],
    feedStatus: null,
    sourceHealth: null,
    isLoading: false,
    error: null,
    lastUpdate: null,
    isStale: false,
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const backoffRef = useRef(0);

  const isAdminPollingEnabled = enabled && adminMode;

  // Build query string from options
  const buildQueryString = useCallback(() => {
    const params = new URLSearchParams();
    if (bbox) params.append("bbox", bbox);
    if (eventType) params.append("event_type", eventType);
    if (jurisdiction) params.append("jurisdiction", jurisdiction);
    if (province) params.append("province", province);
    if (minConfidence !== undefined)
      params.append("min_confidence", minConfidence.toString());
    if (reviewStatus) params.append("review_status", reviewStatus);
    if (publishStatus) params.append("publish_status", publishStatus);
    if (adminMode) params.append("admin_mode", "true");
    return params.toString();
  }, [bbox, eventType, jurisdiction, province, minConfidence, reviewStatus, publishStatus, adminMode]);

  // Fetch map events
  const fetchEvents = useCallback(async () => {
    if (!isAdminPollingEnabled) {
      setState((prev) => ({
        ...prev,
        events: [],
        feedStatus: null,
        sourceHealth: null,
        isLoading: false,
      }));
      return;
    }

    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      // Cancel previous request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      abortControllerRef.current = new AbortController();
      const queryString = buildQueryString();
      const endpoint = `/api/admin/live-map/events${queryString ? `?${queryString}` : ""}`;

      const response = await fetch(
        endpoint,
        {
          signal: abortControllerRef.current.signal,
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: LiveMapEventsResponse = await response.json();

      setState((prev) => ({
        ...prev,
        events: data.events || [],
        isLoading: false,
        error: null,
        lastUpdate: new Date(),
        isStale: false,
      }));

      // Reset backoff on success
      backoffRef.current = 0;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        // Request was cancelled, don't update state
        return;
      }

      const err = error instanceof Error ? error : new Error("Unknown error");
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err,
      }));

      // Exponential backoff on error
      backoffRef.current = Math.min(backoffRef.current * 2 + 1000, 60000);
    }
  }, [isAdminPollingEnabled, buildQueryString]);

  // Feed status is derived from the current events snapshot.
  const fetchFeedStatus = useCallback(async () => {
    if (!isAdminPollingEnabled) {
      setState((prev) => ({ ...prev, feedStatus: null }));
      return;
    }

    setState((prev) => {
      const total = prev.events.length;
      const approved = prev.events.filter((event) => event.review_status === "approved").length;
      const needsReview = prev.events.filter((event) => event.review_status === "needs_review").length;
      const contradicted = prev.events.filter((event) => event.event_type === "contradiction_event").length;
      const high = prev.events.filter((event) => event.confidence >= 0.8).length;
      const medium = prev.events.filter((event) => event.confidence >= 0.5 && event.confidence < 0.8).length;
      const low = prev.events.filter((event) => event.confidence < 0.5).length;

      const derived: FeedStatusResponse = {
        feed_status: "active",
        total_events: total,
        public_events: approved,
        approved_events: approved,
        needs_review: needsReview,
        contradicted,
        confidence_distribution: { high, medium, low },
        last_updated: new Date().toISOString(),
        disclaimer: "Admin-only live map metrics derived from current event snapshot.",
      };

      return { ...prev, feedStatus: derived };
    });
  }, [isAdminPollingEnabled]);

  // Source health endpoint is not mounted for the hardened boundary.
  const fetchSourceHealth = useCallback(async () => {
    setState((prev) => ({ ...prev, sourceHealth: null }));
  }, []);

  // Manual refresh
  const refresh = useCallback(() => {
    fetchEvents();
    fetchFeedStatus();
    fetchSourceHealth();
  }, [fetchEvents, fetchFeedStatus, fetchSourceHealth]);

  // Pause polling
  const pause = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  // Resume polling
  const resume = useCallback(() => {
    if (!timeoutRef.current && isAdminPollingEnabled) {
      fetchEvents();
    }
  }, [isAdminPollingEnabled, fetchEvents]);

  // Check for stale data
  useEffect(() => {
    const lastUpdate = state.lastUpdate;
    if (!lastUpdate) return;

    const checkStale = () => {
      const now = new Date();
      const timeSinceUpdate = now.getTime() - lastUpdate.getTime();
      const isStale = timeSinceUpdate > STALE_THRESHOLD;

      setState((prev) => ({ ...prev, isStale }));
    };

    const staleCheckInterval = setInterval(checkStale, 30000); // Check every 30s

    return () => clearInterval(staleCheckInterval);
  }, [state.lastUpdate]);

  useEffect(() => {
    if (!isAdminPollingEnabled) return;
    fetchFeedStatus();
  }, [isAdminPollingEnabled, state.events, fetchFeedStatus]);

  // Main polling effect
  useEffect(() => {
    if (!isAdminPollingEnabled) {
      pause();
      return;
    }

    // Initial fetch
    fetchEvents();
    fetchFeedStatus();
    fetchSourceHealth();

    // Polling loop
    const poll = () => {
      const effectiveInterval = interval + backoffRef.current;
      timeoutRef.current = setTimeout(() => {
        fetchEvents();
        poll();
      }, effectiveInterval);
    };

    poll();

    // Cleanup
    return () => {
      pause();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [isAdminPollingEnabled, interval, fetchEvents, fetchFeedStatus, fetchSourceHealth, pause]);

  return {
    ...state,
    refresh,
    pause,
    resume,
  };
}
