"use client";

import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import type { CrimeIncident } from "@/lib/types";
import { MapLegend } from "./MapLegend";

const STATUS_COLORS: Record<string, string> = {
  reported: "#94a3b8",
  alleged: "#94a3b8",
  charged: "#f97316",
  before_court: "#3b82f6",
  convicted: "#ef4444",
  dismissed: "#64748b",
  withdrawn: "#64748b",
  acquitted: "#22c55e",
  unknown: "#94a3b8",
};

interface MapCanvasProps {
  incidents: CrimeIncident[];
  selectedId?: string | null;
  onSelect?: (incident: CrimeIncident) => void;
}

export default function MapCanvas({ incidents, selectedId, onSelect }: MapCanvasProps) {
  return (
    <div className="relative h-full w-full">
      <MapContainer
        center={[56.1304, -106.3468]}
        zoom={4}
        style={{ height: "100%", width: "100%" }}
        zoomControl={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {incidents.map((incident) => (
          <CircleMarker
            key={incident.id}
            center={[incident.location.lat, incident.location.lng]}
            radius={selectedId === incident.id ? 12 : 8}
            pathOptions={{
              color: "#fff",
              weight: 2,
              fillColor: STATUS_COLORS[incident.status] ?? "#94a3b8",
              fillOpacity: selectedId === incident.id ? 1 : 0.8,
            }}
            eventHandlers={{
              click: () => onSelect?.(incident),
            }}
          >
            <Popup>
              <div className="text-sm">
                <p className="font-semibold">{incident.title}</p>
                <p className="text-slate-500">{incident.location.city}, {incident.location.province}</p>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      <MapLegend />
    </div>
  );
}
