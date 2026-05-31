/**
 * GeoJSON builders for GeoLegalEvent data.
 *
 * This module provides functions to convert GeoLegalEvent data into GeoJSON
 * features for rendering on MapLibre maps. Each builder creates features with
 * appropriate properties for different event types and visualizations.
 */

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

export interface GeoJSONFeature {
  type: "Feature";
  geometry: {
    type: "Point";
    coordinates: [number, number];
  } | null;
  properties: Record<string, any>;
}

export interface GeoJSONFeatureCollection {
  type: "FeatureCollection";
  features: GeoJSONFeature[];
}

/**
 * Build GeoJSON FeatureCollection from GeoLegalEvent array.
 */
export function buildGeoLegalEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const features: GeoJSONFeature[] = events
    .filter((event) => event.lat !== null && event.lng !== null)
    .map((event) => ({
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: [event.lng!, event.lat!],
      },
      properties: {
        id: event.id,
        event_type: event.event_type,
        title: event.title,
        confidence: event.confidence,
        confidence_label: event.confidence_label,
        review_status: event.review_status,
        publish_status: event.publish_status,
        jurisdiction: event.jurisdiction,
        province: event.province,
        occurred_at: event.occurred_at,
        source_count: event.source_ids.length,
        evidence_count: event.evidence_ids.length,
        claim_count: event.claim_ids.length,
        has_contradiction: event.tags.includes("contradicted"),
        tags: event.tags,
      },
    }));

  return {
    type: "FeatureCollection",
    features,
  };
}

/**
 * Build GeoJSON for court events only.
 */
export function buildCourtEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const courtEvents = events.filter(
    (event) => event.event_type === "court_event"
  );
  return buildGeoLegalEventsGeoJSON(courtEvents);
}

/**
 * Build GeoJSON for crime events only.
 */
export function buildCrimeEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const crimeEvents = events.filter(
    (event) => event.event_type === "crime_event"
  );
  return buildGeoLegalEventsGeoJSON(crimeEvents);
}

/**
 * Build GeoJSON for judge events only.
 */
export function buildJudgeEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const judgeEvents = events.filter(
    (event) => event.event_type === "judge_event"
  );
  return buildGeoLegalEventsGeoJSON(judgeEvents);
}

/**
 * Build GeoJSON for legislation events only.
 */
export function buildLegislationEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const legislationEvents = events.filter(
    (event) => event.event_type === "legislation_event"
  );
  return buildGeoLegalEventsGeoJSON(legislationEvents);
}

/**
 * Build GeoJSON for news events only.
 */
export function buildNewsEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const newsEvents = events.filter((event) => event.event_type === "news_event");
  return buildGeoLegalEventsGeoJSON(newsEvents);
}

/**
 * Build GeoJSON for contradiction events only.
 */
export function buildContradictionEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const contradictionEvents = events.filter(
    (event) => event.event_type === "contradiction_event"
  );
  return buildGeoLegalEventsGeoJSON(contradictionEvents);
}

/**
 * Build confidence heatmap GeoJSON.
 *
 * Creates a simplified heatmap representation using point features with
 * confidence-based color properties.
 */
export function buildConfidenceHeatmapGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const features: GeoJSONFeature[] = events
    .filter((event) => event.lat !== null && event.lng !== null)
    .map((event) => ({
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: [event.lng!, event.lat!],
      },
      properties: {
        id: event.id,
        confidence: event.confidence,
        confidence_label: event.confidence_label,
        // Color intensity based on confidence (0-1)
        intensity: event.confidence,
        // Group by confidence bands for heatmap layers
        band: getConfidenceBand(event.confidence),
      },
    }));

  return {
    type: "FeatureCollection",
    features,
  };
}

function getConfidenceBand(confidence: number): string {
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.5) return "medium";
  return "low";
}

/**
 * Build source health GeoJSON.
 *
 * Creates features representing source health status for map overlay.
 * Since sources don't have coordinates, this returns an empty collection
 * by default. In a full implementation, this would aggregate events by
 * source and display health indicators at event locations.
 */
export function buildSourceHealthGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  // For now, return empty collection
  // In a full implementation, this would:
  // 1. Group events by source
  // 2. Calculate health metrics per source
  // 3. Display health indicators at event locations
  return {
    type: "FeatureCollection",
    features: [],
  };
}

/**
 * Build police release events GeoJSON.
 */
export function buildPoliceReleaseEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const policeEvents = events.filter(
    (event) => event.event_type === "police_release"
  );
  return buildGeoLegalEventsGeoJSON(policeEvents);
}

/**
 * Build statistical events GeoJSON.
 */
export function buildStatisticalEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const statisticalEvents = events.filter(
    (event) => event.event_type === "statistical_event"
  );
  return buildGeoLegalEventsGeoJSON(statisticalEvents);
}

/**
 * Build correction events GeoJSON.
 */
export function buildCorrectionEventsGeoJSON(
  events: GeoLegalEvent[]
): GeoJSONFeatureCollection {
  const correctionEvents = events.filter(
    (event) => event.event_type === "correction_event"
  );
  return buildGeoLegalEventsGeoJSON(correctionEvents);
}
