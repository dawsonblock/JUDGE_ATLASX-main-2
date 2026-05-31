/**
 * Map overlay controls for toggling different event layers on the live map.
 *
 * This component provides checkboxes to toggle visibility of different event type
 * layers (courts, judges, crime reports, police releases, legislation, news,
 * contradictions, confidence heatmap, needs review, source health).
 */
"use client";

import { useState } from "react";

interface MapOverlayControlsProps {
  /** Callback when overlay visibility changes */
  onOverlayChange?: (overlays: Record<string, boolean>) => void;
  /** Initial overlay states */
  initialOverlays?: Record<string, boolean>;
}

export default function MapOverlayControls({
  onOverlayChange,
  initialOverlays,
}: MapOverlayControlsProps) {
  const [overlays, setOverlays] = useState<Record<string, boolean>>(
    initialOverlays || {
      courts: true,
      judges: true,
      crime_reports: true,
      police_releases: true,
      legislation: true,
      news: true,
      contradictions: true,
      confidence_heatmap: false,
      needs_review: false,
      source_health: false,
    }
  );

  const toggleOverlay = (overlayName: string) => {
    const newOverlays = {
      ...overlays,
      [overlayName]: !overlays[overlayName],
    };
    setOverlays(newOverlays);
    onOverlayChange?.(newOverlays);
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-4 w-64">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Map Layers
      </h3>
      <div className="space-y-2">
        <OverlayCheckbox
          label="Courts"
          checked={overlays.courts}
          onChange={() => toggleOverlay("courts")}
          color="blue"
        />
        <OverlayCheckbox
          label="Judges"
          checked={overlays.judges}
          onChange={() => toggleOverlay("judges")}
          color="purple"
        />
        <OverlayCheckbox
          label="Crime Reports"
          checked={overlays.crime_reports}
          onChange={() => toggleOverlay("crime_reports")}
          color="red"
        />
        <OverlayCheckbox
          label="Police Releases"
          checked={overlays.police_releases}
          onChange={() => toggleOverlay("police_releases")}
          color="orange"
        />
        <OverlayCheckbox
          label="Legislation"
          checked={overlays.legislation}
          onChange={() => toggleOverlay("legislation")}
          color="green"
        />
        <OverlayCheckbox
          label="News"
          checked={overlays.news}
          onChange={() => toggleOverlay("news")}
          color="yellow"
        />
        <OverlayCheckbox
          label="Contradictions"
          checked={overlays.contradictions}
          onChange={() => toggleOverlay("contradictions")}
          color="pink"
        />
        <div className="border-t pt-2 mt-2">
          <OverlayCheckbox
            label="Confidence Heatmap"
            checked={overlays.confidence_heatmap}
            onChange={() => toggleOverlay("confidence_heatmap")}
            color="gray"
          />
          <OverlayCheckbox
            label="Needs Review"
            checked={overlays.needs_review}
            onChange={() => toggleOverlay("needs_review")}
            color="amber"
          />
          <OverlayCheckbox
            label="Source Health"
            checked={overlays.source_health}
            onChange={() => toggleOverlay("source_health")}
            color="teal"
          />
        </div>
      </div>
    </div>
  );
}

interface OverlayCheckboxProps {
  label: string;
  checked: boolean;
  onChange: () => void;
  color: string;
}

function OverlayCheckbox({
  label,
  checked,
  onChange,
  color,
}: OverlayCheckboxProps) {
  const colorClasses: Record<string, string> = {
    blue: "bg-blue-500 border-blue-500",
    purple: "bg-purple-500 border-purple-500",
    red: "bg-red-500 border-red-500",
    orange: "bg-orange-500 border-orange-500",
    green: "bg-green-500 border-green-500",
    yellow: "bg-yellow-500 border-yellow-500",
    pink: "bg-pink-500 border-pink-500",
    gray: "bg-gray-500 border-gray-500",
    amber: "bg-amber-500 border-amber-500",
    teal: "bg-teal-500 border-teal-500",
  };

  return (
    <label className="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className={`w-4 h-4 rounded border-2 ${colorClasses[color] || colorClasses.blue} ${
          checked ? "opacity-100" : "opacity-30"
        }`}
      />
      <span className="text-sm text-gray-600">{label}</span>
    </label>
  );
}
