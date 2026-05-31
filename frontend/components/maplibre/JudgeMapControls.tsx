"use client";

/**
 * JudgeMapControls.tsx — adds MapLibre NavigationControl and ScaleControl
 * to the map via the MapLibreContext.
 */

import { useEffect } from "react";
import maplibregl from "maplibre-gl";
import { useJudgeMap } from "./JudgeMap";

export default function JudgeMapControls() {
  const map = useJudgeMap();

  useEffect(() => {
    if (!map) return;

    const nav = new maplibregl.NavigationControl({ showCompass: false });
    const scale = new maplibregl.ScaleControl({ unit: "metric" });

    map.addControl(nav, "top-right");
    map.addControl(scale, "bottom-right");

    return () => {
      try {
        map.removeControl(nav);
      } catch {
        // Map instance may already be tearing down during hot reload/unmount.
      }
      try {
        map.removeControl(scale);
      } catch {
        // Map instance may already be tearing down during hot reload/unmount.
      }
    };
  }, [map]);

  return null;
}
