/**
 * Tests for GeoLegalEvent GeoJSON builders.
 *
 * Tests cover:
 * - Building valid GeoJSON from GeoLegalEvent arrays
 * - Filtering events by type
 * - Building confidence heatmaps
 * - Handling missing coordinates
 * - Building event-specific GeoJSON (courts, crimes, legislation, etc.)
 */

import { describe, expect, it } from "vitest";
import {
  buildConfidenceHeatmapGeoJSON,
  buildContradictionEventsGeoJSON,
  buildCorrectionEventsGeoJSON,
  buildCourtEventsGeoJSON,
  buildCrimeEventsGeoJSON,
  buildGeoLegalEventsGeoJSON,
  buildJudgeEventsGeoJSON,
  buildLegislationEventsGeoJSON,
  buildNewsEventsGeoJSON,
  buildPoliceReleaseEventsGeoJSON,
  buildSourceHealthGeoJSON,
  buildStatisticalEventsGeoJSON,
  type GeoLegalEvent,
} from "@/lib/map/geoLegalGeoJSONBuilders";

describe("GeoLegalEvent GeoJSON Builders", () => {
  const sampleEvents: GeoLegalEvent[] = [
    {
      id: "event-1",
      event_type: "court_event",
      title: "Court Event 1",
      description: "Test court event",
      lat: 50.0,
      lng: -105.0,
      location_name: "Saskatoon",
      occurred_at: "2024-01-01T00:00:00Z",
      published_at: "2024-01-01T00:00:00Z",
      jurisdiction: "federal",
      province: "Saskatchewan",
      country: "Canada",
      source_ids: ["source-1"],
      evidence_ids: ["evidence-1"],
      claim_ids: ["claim-1"],
      confidence: 0.8,
      confidence_label: "high",
      review_status: "approved",
      publish_status: "public_safe",
      tags: ["court", "test"],
      metadata: {},
    },
    {
      id: "event-2",
      event_type: "crime_event",
      title: "Crime Event 1",
      description: "Test crime event",
      lat: 51.0,
      lng: -106.0,
      location_name: "Regina",
      occurred_at: "2024-01-02T00:00:00Z",
      published_at: "2024-01-02T00:00:00Z",
      jurisdiction: "provincial",
      province: "Saskatchewan",
      country: "Canada",
      source_ids: ["source-2"],
      evidence_ids: ["evidence-2"],
      claim_ids: ["claim-2"],
      confidence: 0.6,
      confidence_label: "medium",
      review_status: "approved",
      publish_status: "public_safe",
      tags: ["crime", "test"],
      metadata: {},
    },
    {
      id: "event-3",
      event_type: "court_event",
      title: "Court Event 2",
      description: "Test court event without coordinates",
      lat: null, // Missing coordinates
      lng: null,
      location_name: "Unknown Location",
      occurred_at: "2024-01-03T00:00:00Z",
      published_at: "2024-01-03T00:00:00Z",
      jurisdiction: "federal",
      province: "Saskatchewan",
      country: "Canada",
      source_ids: ["source-3"],
      evidence_ids: ["evidence-3"],
      claim_ids: ["claim-3"],
      confidence: 0.9,
      confidence_label: "very_high",
      review_status: "approved",
      publish_status: "public_safe",
      tags: ["court", "test"],
      metadata: {},
    },
    {
      id: "event-4",
      event_type: "contradiction_event",
      title: "Contradiction Event",
      description: "Test contradiction event",
      lat: 49.0,
      lng: -104.0,
      location_name: "Prince Albert",
      occurred_at: "2024-01-04T00:00:00Z",
      published_at: "2024-01-04T00:00:00Z",
      jurisdiction: "federal",
      province: "Saskatchewan",
      country: "Canada",
      source_ids: ["source-4"],
      evidence_ids: ["evidence-4"],
      claim_ids: ["claim-4"],
      confidence: 0.7,
      confidence_label: "medium",
      review_status: "approved",
      publish_status: "public_safe",
      tags: ["contradicted", "test"],
      metadata: {},
    },
  ];

  describe("buildGeoLegalEventsGeoJSON", () => {
    it("builds valid GeoJSON FeatureCollection from events", () => {
      const result = buildGeoLegalEventsGeoJSON(sampleEvents);

      expect(result.type).toBe("FeatureCollection");
      expect(Array.isArray(result.features)).toBe(true);
      expect(result.features.length).toBe(3); // Only events with coordinates
    });

    it("filters out events without coordinates", () => {
      const result = buildGeoLegalEventsGeoJSON(sampleEvents);

      const eventIds = result.features.map((f) => f.properties.id);
      expect(eventIds).not.toContain("event-3"); // Missing coordinates
      expect(eventIds).toContain("event-1");
      expect(eventIds).toContain("event-2");
      expect(eventIds).toContain("event-4");
    });

    it("creates valid GeoJSON Point geometries", () => {
      const result = buildGeoLegalEventsGeoJSON(sampleEvents);

      result.features.forEach((feature) => {
        expect(feature.geometry).not.toBeNull();
        expect(feature.geometry?.type).toBe("Point");
        expect(Array.isArray(feature.geometry?.coordinates)).toBe(true);
        expect(feature.geometry?.coordinates.length).toBe(2);
      });
    });

    it("includes all required properties", () => {
      const result = buildGeoLegalEventsGeoJSON(sampleEvents);

      result.features.forEach((feature) => {
        expect(feature.properties).toHaveProperty("id");
        expect(feature.properties).toHaveProperty("event_type");
        expect(feature.properties).toHaveProperty("confidence");
        expect(feature.properties).toHaveProperty("confidence_label");
        expect(feature.properties).toHaveProperty("review_status");
        expect(feature.properties).toHaveProperty("publish_status");
        expect(feature.properties).toHaveProperty("jurisdiction");
        expect(feature.properties).toHaveProperty("province");
        expect(feature.properties).toHaveProperty("source_count");
        expect(feature.properties).toHaveProperty("evidence_count");
        expect(feature.properties).toHaveProperty("claim_count");
      });
    });

    it("correctly identifies contradicted events", () => {
      const result = buildGeoLegalEventsGeoJSON(sampleEvents);

      const contradictionEvent = result.features.find(
        (f) => f.properties.id === "event-4"
      );
      expect(contradictionEvent?.properties.has_contradiction).toBe(true);

      const normalEvent = result.features.find((f) => f.properties.id === "event-1");
      expect(normalEvent?.properties.has_contradiction).toBe(false);
    });
  });

  describe("Event-specific builders", () => {
    it("buildCourtEventsGeoJSON filters only court events", () => {
      const result = buildCourtEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(1);
      expect(result.features[0].properties.event_type).toBe("court_event");
    });

    it("buildCrimeEventsGeoJSON filters only crime events", () => {
      const result = buildCrimeEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(1);
      expect(result.features[0].properties.event_type).toBe("crime_event");
    });

    it("buildJudgeEventsGeoJSON returns empty for non-judge events", () => {
      const result = buildJudgeEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(0);
    });

    it("buildLegislationEventsGeoJSON returns empty for non-legislation events", () => {
      const result = buildLegislationEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(0);
    });

    it("buildNewsEventsGeoJSON returns empty for non-news events", () => {
      const result = buildNewsEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(0);
    });

    it("buildContradictionEventsGeoJSON filters only contradiction events", () => {
      const result = buildContradictionEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(1);
      expect(result.features[0].properties.event_type).toBe("contradiction_event");
    });

    it("buildPoliceReleaseEventsGeoJSON returns empty for non-police events", () => {
      const result = buildPoliceReleaseEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(0);
    });

    it("buildStatisticalEventsGeoJSON returns empty for non-statistical events", () => {
      const result = buildStatisticalEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(0);
    });

    it("buildCorrectionEventsGeoJSON returns empty for non-correction events", () => {
      const result = buildCorrectionEventsGeoJSON(sampleEvents);

      expect(result.features.length).toBe(0);
    });
  });

  describe("buildConfidenceHeatmapGeoJSON", () => {
    it("builds heatmap GeoJSON with confidence bands", () => {
      const result = buildConfidenceHeatmapGeoJSON(sampleEvents);

      expect(result.type).toBe("FeatureCollection");
      expect(result.features.length).toBe(3); // Only events with coordinates

      result.features.forEach((feature) => {
        expect(feature.properties).toHaveProperty("confidence");
        expect(feature.properties).toHaveProperty("confidence_label");
        expect(feature.properties).toHaveProperty("intensity");
        expect(feature.properties).toHaveProperty("band");
      });
    });

    it("assigns correct confidence bands", () => {
      const result = buildConfidenceHeatmapGeoJSON(sampleEvents);

      const highConfidenceEvent = result.features.find(
        (f) => f.properties.id === "event-1"
      );
      expect(highConfidenceEvent?.properties.band).toBe("high");

      const mediumConfidenceEvent = result.features.find(
        (f) => f.properties.id === "event-2"
      );
      expect(mediumConfidenceEvent?.properties.band).toBe("medium");
    });

    it("uses confidence as intensity value", () => {
      const result = buildConfidenceHeatmapGeoJSON(sampleEvents);

      result.features.forEach((feature) => {
        expect(feature.properties.intensity).toBe(feature.properties.confidence);
      });
    });
  });

  describe("buildSourceHealthGeoJSON", () => {
    it("returns empty FeatureCollection by default", () => {
      const result = buildSourceHealthGeoJSON(sampleEvents);

      expect(result.type).toBe("FeatureCollection");
      expect(result.features.length).toBe(0);
    });
  });

  describe("Edge cases", () => {
    it("handles empty event array", () => {
      const result = buildGeoLegalEventsGeoJSON([]);

      expect(result.type).toBe("FeatureCollection");
      expect(result.features.length).toBe(0);
    });

    it("handles events with null coordinates", () => {
      const eventsWithNullCoords: GeoLegalEvent[] = [
        {
          id: "event-null",
          event_type: "court_event",
          title: "Null Coord Event",
          description: "Null coordinate event",
          lat: null,
          lng: null,
          location_name: null,
          occurred_at: null,
          published_at: null,
          jurisdiction: "federal",
          province: null,
          country: "Canada",
          confidence: 0.8,
          confidence_label: "high",
          review_status: "approved",
          publish_status: "public_safe",
          source_ids: [],
          evidence_ids: [],
          claim_ids: [],
          tags: [],
          metadata: {},
        },
      ];

      const result = buildGeoLegalEventsGeoJSON(eventsWithNullCoords);

      expect(result.features.length).toBe(0);
    });

    it("handles events with zero coordinates", () => {
      const eventsWithZeroCoords: GeoLegalEvent[] = [
        {
          id: "event-zero",
          event_type: "court_event",
          title: "Zero Coord Event",
          description: "Zero coordinate event",
          lat: 0.0,
          lng: 0.0,
          location_name: null,
          occurred_at: null,
          published_at: null,
          jurisdiction: "federal",
          province: null,
          country: "Canada",
          confidence: 0.8,
          confidence_label: "high",
          review_status: "approved",
          publish_status: "public_safe",
          source_ids: [],
          evidence_ids: [],
          claim_ids: [],
          tags: [],
          metadata: {},
        },
      ];

      const result = buildGeoLegalEventsGeoJSON(eventsWithZeroCoords);

      expect(result.features.length).toBe(1);
      expect(result.features[0].geometry?.coordinates).toEqual([0.0, 0.0]);
    });

    it("handles events with extreme coordinates", () => {
      const eventsWithExtremeCoords: GeoLegalEvent[] = [
        {
          id: "event-extreme",
          event_type: "court_event",
          title: "Extreme Coord Event",
          description: "Extreme coordinate event",
          lat: 89.0,
          lng: -179.0,
          location_name: null,
          occurred_at: null,
          published_at: null,
          jurisdiction: "federal",
          province: null,
          country: "Canada",
          confidence: 0.8,
          confidence_label: "high",
          review_status: "approved",
          publish_status: "public_safe",
          source_ids: [],
          evidence_ids: [],
          claim_ids: [],
          tags: [],
          metadata: {},
        },
      ];

      const result = buildGeoLegalEventsGeoJSON(eventsWithExtremeCoords);

      expect(result.features.length).toBe(1);
      expect(result.features[0].geometry?.coordinates).toEqual([-179.0, 89.0]);
    });
  });

  describe("Property preservation", () => {
    it("preserves all tags in properties", () => {
      const result = buildGeoLegalEventsGeoJSON(sampleEvents);

      const eventWithTags = result.features.find((f) => f.properties.id === "event-1");
      expect(eventWithTags?.properties.tags).toEqual(["court", "test"]);
    });

    it("preserves occurred_at date", () => {
      const result = buildGeoLegalEventsGeoJSON(sampleEvents);

      const eventWithDate = result.features.find((f) => f.properties.id === "event-1");
      expect(eventWithDate?.properties.occurred_at).toBe("2024-01-01T00:00:00Z");
    });

    it("calculates correct counts", () => {
      const result = buildGeoLegalEventsGeoJSON(sampleEvents);

      const eventWithCounts = result.features.find((f) => f.properties.id === "event-1");
      expect(eventWithCounts?.properties.source_count).toBe(1);
      expect(eventWithCounts?.properties.evidence_count).toBe(1);
      expect(eventWithCounts?.properties.claim_count).toBe(1);
    });
  });
});