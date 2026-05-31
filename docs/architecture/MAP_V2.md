# MAP — MapLibre Implementation

## Overview

`/map` is the canonical map route built on [MapLibre GL JS](https://maplibre.org/) 4.x.
The legacy `/map-v2` route was removed after migration to the canonical path.
Tiles are served by [OpenFreeMap](https://openfreemap.org/) — no API key required.

## Route

```
/app/map/page.tsx             — Next.js server page (metadata export)
/app/map/MapWorkspace.tsx     — "use client" workspace component
```

## Component Tree

```
MapPage (server)
└── MapWorkspace (client — owns fetch state)
    ├── JudgeMapClient (dynamic / SSR disabled)
    │   └── JudgeMap (MapLibre init + MapLibreContext.Provider)
    │       ├── JudgeClusterLayer   — GeoJSON source + layers + event handlers
    │       ├── JudgeMapControls    — NavigationControl + ScaleControl
    │       ├── JudgeMapLegend      — floating legend + mandatory disclaimer
    │       ├── JudgeRelationshipArcs — STUB: returns null
    │       └── JudgeMapPopup       — React sidebar panel (shown on point click)
    └── JudgeMapDrawerBridge        — wraps existing MapRecordDrawer (shown on "View full record")
```

All files for this route live under `frontend/components/maplibre/`.

## Data Flow

```
useEffect (mount)
  ├── fetchCrimeIncidents()          → /api/map/crime-incidents
  │     returns CrimeIncidentFeatureCollection
  └── fetchJson<FeatureCollection>   → /api/map/events
        returns FeatureCollection

Both datasets flow down as props to JudgeClusterLayer which combines them
into a single GeoJSON source with a `record_type` property to distinguish
incidents from court events at the rendering layer.

Point click → onSelectRecord(JudgeMapRecord) → selectedRecord state
"View full record" → drawerOpen = true → JudgeMapDrawerBridge renders
```

## MapLibre Context

`JudgeMap.tsx` exposes the map instance via React context:

```ts
import { useJudgeMap } from "@/components/maplibre/JudgeMap";
const map = useJudgeMap(); // maplibregl.Map | null
```

Child components that need the map instance (layers, controls) use this hook.
Children are only mounted after the `load` event fires, so `map` is never null
for children rendered inside `<JudgeMap>`.

## Key Constants (`constants.ts`)

| Constant                           | Value                                                     |
| ---------------------------------- | --------------------------------------------------------- |
| `TILE_STYLE_URL`                   | `https://tiles.openfreemap.org/styles/liberty`            |
| `SOURCE_ID.INCIDENTS`              | `"judge-incidents"`                                       |
| `LAYER_ID.INCIDENTS_CLUSTER`       | `"incidents-cluster"`                                     |
| `LAYER_ID.INCIDENTS_CLUSTER_COUNT` | `"incidents-cluster-count"`                               |
| `LAYER_ID.INCIDENTS_UNCLUSTERED`   | `"incidents-unclustered"`                                 |
| `DOT_COLOR.court_event`            | `#3b82f6` (blue)                                          |
| `DOT_COLOR.reported_incident`      | `#f59e0b` (amber)                                         |
| `DOT_COLOR.cluster`                | `#6366f1` (indigo)                                        |
| `DEFAULT_BOUNDS.center`            | `[-106.6702, 52.1579]` (Saskatoon, SK — default; zoom 11) |
| `DEFAULT_BOUNDS.zoom`              | `11`                                                      |

## Known Gaps / Roadmap

1. **Relationship arcs** — `JudgeRelationshipArcs.tsx` returns `null`. Blocked on:
   - Approved arc endpoint with pagination
   - Evidence count > 0 guard
   - Neutral description language approval
   - Performance profiling for large arc sets

2. **No test runner** — verification is `npm run typecheck && npm run build`.
   Integration tests would require Playwright or similar.

3. **Tile fallback** — no offline tile fallback is currently configured. If
   `tiles.openfreemap.org` is unavailable the map renders an empty canvas.

4. **Mobile layout** — drawer sidebar uses fixed 384 px width; small viewports
   should switch to a bottom sheet. Not yet implemented.

## Safety Language Policy

All user-visible copy follows the JUDGE project safety policy:

- No language implying guilt, culpability, or misconduct
- All data is described as "publicly available" or "public records"
- Every record display includes `MAP_DISCLAIMER` from `constants.ts`
