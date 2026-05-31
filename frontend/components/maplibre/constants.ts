/**
 * constants.ts — static configuration for the canonical MapLibre /map implementation.
 */

import { getDisclaimer } from "@/lib/disclaimerService";

/** OpenFreeMap Liberty style — free, no API key, OSM-based. */
export const TILE_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

/** MapLibre source IDs */
export const SOURCE_ID = {
  INCIDENTS: "judge-incidents",
  EVENTS: "judge-events",
} as const;

/** MapLibre layer IDs */
export const LAYER_ID = {
  INCIDENTS_CLUSTER: "incidents-cluster",
  INCIDENTS_CLUSTER_COUNT: "incidents-cluster-count",
  INCIDENTS_UNCLUSTERED: "incidents-unclustered",
  EVENTS_CLUSTER: "events-cluster",
  EVENTS_CLUSTER_COUNT: "events-cluster-count",
  EVENTS_UNCLUSTERED: "events-unclustered",
} as const;

/** Cluster radius in pixels */
export const CLUSTER_RADIUS = 50;

/** Dot colors by record type */
export const DOT_COLOR = {
  court_event: "#3b82f6", // blue-500
  reported_incident: "#f59e0b", // amber-500
  cluster: "#6366f1", // indigo-500
} as const;

/** Default map viewport: Saskatoon, SK */
export const DEFAULT_BOUNDS = {
  center: [-106.6702, 52.1579] as [number, number], // Saskatoon, SK
  zoom: 11,
};

/** Mandatory disclaimer shown in the legend. */
export const MAP_DISCLAIMER = getDisclaimer("map_legend").text;
