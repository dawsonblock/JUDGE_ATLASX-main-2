"use client";

import dynamic from "next/dynamic";
import type { CrimeIncident } from "@/lib/types";

const MapCanvas = dynamic(() => import("./MapCanvas"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center bg-slate-100">
      <p className="text-slate-500 text-sm">Loading map…</p>
    </div>
  ),
});

interface MapCanvasClientProps {
  incidents: CrimeIncident[];
  selectedId?: string | null;
  onSelect?: (incident: CrimeIncident) => void;
}

export function MapCanvasClient(props: MapCanvasClientProps) {
  return <MapCanvas {...props} />;
}
