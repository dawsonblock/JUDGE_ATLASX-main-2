# UI Components — MapLibre Module

All components live under `frontend/components/maplibre/`.

---

## JudgeMapClient

**File:** `JudgeMapClient.tsx`  
**Type:** Client component (dynamic import, SSR disabled)

Thin wrapper that prevents MapLibre from running during server-side rendering.

```tsx
<JudgeMapClient className="w-full h-full">
  {/* children receive map context */}
</JudgeMapClient>
```

| Prop | Type | Description |
|---|---|---|
| `children` | `React.ReactNode` | Components that use `useJudgeMap()` |
| `className` | `string?` | CSS class forwarded to the map container |

---

## JudgeMap

**File:** `JudgeMap.tsx`  
**Type:** Client component (internal — use `JudgeMapClient` from outside)

Initialises the MapLibre `Map` instance and provides it via `MapLibreContext`.
Children are only rendered after the `load` event fires.

**Exported hook:**

```ts
import { useJudgeMap } from "@/components/maplibre/JudgeMap";
const map = useJudgeMap(); // maplibregl.Map — never null for children
```

---

## JudgeClusterLayer

**File:** `JudgeClusterLayer.tsx`  
**Type:** Client component (renders `null` — side effects only)

Adds a clustered GeoJSON source and three layers (clusters, cluster labels,
unclustered points) to the map.  Clicking a cluster zooms in; clicking a
point fires `onSelectRecord`.

| Prop | Type | Description |
|---|---|---|
| `incidents` | `CrimeIncidentFeatureCollection \| null` | Reported incidents from `/api/map/crime-incidents` |
| `events` | `FeatureCollection \| null` | Court events from `/api/map/events` |
| `onSelectRecord` | `(r: JudgeMapRecord) => void` | Called when a point is clicked |

---

## JudgeMapPopup

**File:** `JudgeMapPopup.tsx`  
**Type:** Client component (absolutely-positioned div)

React sidebar overlay — renders as a panel over the map rather than using
the MapLibre imperative Popup API.  Shown when a record is selected and the
detail drawer is not open.

| Prop | Type | Description |
|---|---|---|
| `record` | `JudgeMapRecord` | The selected record to display |
| `onOpenDrawer` | `() => void` | Called when "View full record" is clicked |
| `onClose` | `() => void` | Called when the close button is clicked |

---

## JudgeMapControls

**File:** `JudgeMapControls.tsx`  
**Type:** Client component (renders `null` — side effects only)

Adds `NavigationControl` (zoom only, no compass) to the top-right and
`ScaleControl` (metric) to the bottom-right of the map.  Both controls are
removed on unmount.

No props.

---

## JudgeMapLegend

**File:** `JudgeMapLegend.tsx`  
**Type:** Client component

Floating legend panel positioned at bottom-left of the map.  Shows colour
keys for court events, reported incidents, and clusters, plus the mandatory
`MAP_DISCLAIMER` string.

No props.

---

## JudgeRelationshipArcs

**File:** `JudgeRelationshipArcs.tsx`  
**Type:** Client component stub (always returns `null`)

Placeholder for future arc/edge rendering between related records.  Blocked
until a paginated arc endpoint is available and evidence-count guards are in
place.  See the detailed TODO comment in the file for implementation criteria.

No props.

---

## JudgeMapDrawerBridge

**File:** `JudgeMapDrawerBridge.tsx`  
**Type:** Client component

Adapter that converts a `JudgeMapRecord` to the `MapDotRecord` shape
expected by the existing `MapRecordDrawer` component, then renders it.

| Prop | Type | Description |
|---|---|---|
| `record` | `JudgeMapRecord \| null` | Selected record (or null to hide) |
| `onClose` | `() => void` | Passed through to `MapRecordDrawer` |

---

## Shared Types (`types.ts`)

```ts
type JudgeMapRecord = {
  id: string | number;
  record_type: "court_event" | "reported_incident";
  coordinates: [number, number];
  title: string;
  date: string | null;
  city: string | null;
  state_province: string | null;
  source_count: number;
  has_news: boolean;
  has_links: boolean;
  disclaimer: string;
};

// Adapters
courtEventToMapRecord(f: MapFeature): JudgeMapRecord
crimeIncidentToMapRecord(f: CrimeIncidentFeature): JudgeMapRecord
judgeMapRecordToMapDotRecord(r: JudgeMapRecord): MapDotRecord
```
