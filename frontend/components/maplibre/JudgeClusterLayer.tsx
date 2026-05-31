"use client";

/**
 * JudgeClusterLayer.tsx — adds GeoJSON sources and cluster layers for
 * reported_incident and court_event records to the MapLibre map.
 *
 * Handles click on cluster (zoom in) and click on individual point (select record).
 *
 * Language note: layer labels and tooltips must describe factual records only;
 * do not imply guilt or misconduct of any named person.
 */

import { useEffect } from "react";
import maplibregl from "maplibre-gl";
import type { MapMouseEvent, GeoJSONSource } from "maplibre-gl";
import { useJudgeMap } from "./JudgeMap";
import {
  SOURCE_ID,
  LAYER_ID,
  CLUSTER_RADIUS,
  DOT_COLOR,
} from "./constants";
import type { JudgeMapRecord } from "./types";
import { sourceQualityToConfidence } from "./types";
import type { CrimeIncidentFeatureCollection, FeatureCollection } from "@/lib/api";

type Props = {
  incidents: CrimeIncidentFeatureCollection | null;
  events: FeatureCollection | null;
  onSelectRecord: (record: JudgeMapRecord) => void;
};

/** Build a GeoJSON FeatureCollection keyed on record data for MapLibre. */
function toGeoJson(
  incidents: CrimeIncidentFeatureCollection | null,
  events: FeatureCollection | null,
): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];

  if (incidents) {
    for (const f of incidents.features) {
      const [lng, lat] = f.geometry.coordinates;
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
      if (lng === 0 && lat === 0) continue;
      if (lng < -180 || lng > 180 || lat < -90 || lat > 90) continue;
      features.push({
        type: "Feature",
        geometry: f.geometry,
        properties: {
          ...f.properties,
          record_type: "reported_incident",
        },
      });
    }
  }
  if (events) {
    for (const f of events.features) {
      const [lng, lat] = f.geometry.coordinates;
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
      if (lng === 0 && lat === 0) continue;
      if (lng < -180 || lng > 180 || lat < -90 || lat > 90) continue;
      features.push({
        type: "Feature",
        geometry: f.geometry,
        properties: {
          ...f.properties,
          record_type: "court_event",
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

export default function JudgeClusterLayer({ incidents, events, onSelectRecord }: Props) {
  const map = useJudgeMap();

  useEffect(() => {
    if (!map) return;

    const sourceId = SOURCE_ID.INCIDENTS; // single combined source
    const geojson = toGeoJson(incidents, events);

    // Add or update source
    if (map.getSource(sourceId)) {
      (map.getSource(sourceId) as GeoJSONSource).setData(geojson);
      return;
    }

    map.addSource(sourceId, {
      type: "geojson",
      data: geojson,
      cluster: true,
      clusterMaxZoom: 14,
      clusterRadius: CLUSTER_RADIUS,
    });

    // Cluster circles
    map.addLayer({
      id: LAYER_ID.INCIDENTS_CLUSTER,
      type: "circle",
      source: sourceId,
      filter: ["has", "point_count"],
      paint: {
        "circle-color": DOT_COLOR.cluster,
        "circle-radius": [
          "step",
          ["get", "point_count"],
          20, 10,
          28, 50,
          36,
        ],
        "circle-opacity": 0.85,
      },
    });

    // Cluster count labels
    const styleHasGlyphs = Boolean(map.getStyle()?.glyphs);
    if (styleHasGlyphs) {
      map.addLayer({
        id: LAYER_ID.INCIDENTS_CLUSTER_COUNT,
        type: "symbol",
        source: sourceId,
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          "text-size": 13,
        },
        paint: {
          "text-color": "#ffffff",
        },
      });
    }

    // Unclustered points
    map.addLayer({
      id: LAYER_ID.INCIDENTS_UNCLUSTERED,
      type: "circle",
      source: sourceId,
      filter: ["!", ["has", "point_count"]],
      paint: {
        "circle-color": [
          "match",
          ["get", "record_type"],
          "court_event", DOT_COLOR.court_event,
          DOT_COLOR.reported_incident, // default
        ],
        "circle-radius": 12,
        "circle-stroke-width": 3,
        "circle-stroke-color": "#111827",
        "circle-opacity": 1,
      },
    });

    // Zoom into cluster on click
    const onClusterClick = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: [LAYER_ID.INCIDENTS_CLUSTER],
      });
      if (!features.length) return;
      const clusterId = features[0].properties?.cluster_id as number | undefined;
      if (clusterId === undefined) return;
      const source = map.getSource(sourceId) as GeoJSONSource;
      source.getClusterExpansionZoom(clusterId).then((zoom: number) => {
        const geom = features[0].geometry as GeoJSON.Point;
        map.easeTo({ center: geom.coordinates as [number, number], zoom });
      }).catch(() => { /* ignore */ });
    };

    // Select record on unclustered point click
    const onPointClick = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: [LAYER_ID.INCIDENTS_UNCLUSTERED],
      });
      if (!features.length) return;
      const props = features[0].properties;
      if (!props) return;
      const geom = features[0].geometry as GeoJSON.Point;
      const record: JudgeMapRecord = {
        id: props.incident_id ?? props.event_id,
        record_type: props.record_type as "court_event" | "reported_incident",
        coordinates: geom.coordinates as [number, number],
        title: props.title ?? `${props.incident_category}: ${props.incident_type}`,
        date: props.reported_at ?? props.occurred_at ?? props.event_date ?? props.decision_date ?? null,
        city: props.city ?? props.location_name ?? null,
        state_province: props.province_state ?? null,
        source_count: props.source_count ?? 0,
        has_news: props.has_news ?? false,
        has_links: props.has_court_links ?? props.has_incident_links ?? false,
        disclaimer: props.disclaimer ?? "",
        review_status: props.review_status ?? "pending_review",
        public_visibility: Boolean(props.public_visibility),
        confidence: sourceQualityToConfidence(
          props.source_quality ?? props.verification_status ?? null,
          Boolean(props.verified_flag),
        ),
        evidence_count: props.source_count ?? 0,
        relationship_warning: props.repeat_offender_indicator
          ? "Repeat-offender indicator present — see source for context."
          : props.has_court_links
          ? "This incident has linked court records — verify via sources."
          : null,
      };
      onSelectRecord(record);
    };

    // Pointer cursor on interactive layers
    const setCursorPointer = () => { map.getCanvas().style.cursor = "pointer"; };
    const resetCursor = () => { map.getCanvas().style.cursor = ""; };

    map.on("click", LAYER_ID.INCIDENTS_CLUSTER, onClusterClick);
    map.on("click", LAYER_ID.INCIDENTS_UNCLUSTERED, onPointClick);
    map.on("mouseenter", LAYER_ID.INCIDENTS_CLUSTER, setCursorPointer);
    map.on("mouseleave", LAYER_ID.INCIDENTS_CLUSTER, resetCursor);
    map.on("mouseenter", LAYER_ID.INCIDENTS_UNCLUSTERED, setCursorPointer);
    map.on("mouseleave", LAYER_ID.INCIDENTS_UNCLUSTERED, resetCursor);

    return () => {
      if (!map.getStyle()) return; // map already removed
      map.off("click", LAYER_ID.INCIDENTS_CLUSTER, onClusterClick);
      map.off("click", LAYER_ID.INCIDENTS_UNCLUSTERED, onPointClick);
      map.off("mouseenter", LAYER_ID.INCIDENTS_CLUSTER, setCursorPointer);
      map.off("mouseleave", LAYER_ID.INCIDENTS_CLUSTER, resetCursor);
      map.off("mouseenter", LAYER_ID.INCIDENTS_UNCLUSTERED, setCursorPointer);
      map.off("mouseleave", LAYER_ID.INCIDENTS_UNCLUSTERED, resetCursor);
      [
        LAYER_ID.INCIDENTS_UNCLUSTERED,
        LAYER_ID.INCIDENTS_CLUSTER_COUNT,
        LAYER_ID.INCIDENTS_CLUSTER,
      ].forEach((id) => { if (map.getLayer(id)) map.removeLayer(id); });
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
    // Re-run only when map instance changes; data updates handled by setData above
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Update data whenever incidents/events change without re-adding layers
  useEffect(() => {
    if (!map) return;
    const source = map.getSource(SOURCE_ID.INCIDENTS) as GeoJSONSource | undefined;
    if (!source) return;
    source.setData(toGeoJson(incidents, events));
  }, [map, incidents, events]);

  return null; // purely imperative — no DOM output
}
