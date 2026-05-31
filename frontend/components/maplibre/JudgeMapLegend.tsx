"use client";

/**
 * JudgeMapLegend.tsx — floating legend showing dot-color key plus the
 * mandatory disclaimer that records do not imply guilt or misconduct.
 */

import { DOT_COLOR, MAP_DISCLAIMER } from "./constants";

export default function JudgeMapLegend() {
  return (
    <div className="absolute bottom-8 left-3 z-10 rounded-lg border border-gray-200 bg-white/95 backdrop-blur-sm shadow p-3 max-w-xs">
      <p className="text-xs font-semibold text-gray-700 mb-2">Map legend</p>
      <div className="flex flex-col gap-1.5 mb-3">
        <LegendItem color={DOT_COLOR.reported_incident} label="Reported incident" />
        <LegendItem color={DOT_COLOR.court_event} label="Court event" />
        <LegendItem color={DOT_COLOR.cluster} label="Clustered records" isCluster />
      </div>
      <p className="text-[10px] text-gray-400 leading-tight">{MAP_DISCLAIMER}</p>
    </div>
  );
}

function LegendItem({
  color,
  label,
  isCluster = false,
}: {
  color: string;
  label: string;
  isCluster?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-block shrink-0 ${isCluster ? "w-5 h-5 rounded-full" : "w-3 h-3 rounded-full border border-white"}`}
        style={{ backgroundColor: color, boxShadow: "0 0 0 1px rgba(0,0,0,0.15)" }}
      />
      <span className="text-xs text-gray-600">{label}</span>
    </div>
  );
}
