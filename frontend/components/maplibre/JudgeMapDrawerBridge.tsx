"use client";

/**
 * JudgeMapDrawerBridge.tsx — adapts a JudgeMapRecord into the MapDotRecord
 * shape expected by the existing MapRecordDrawer component, then renders it.
 *
 * This keeps MapRecordDrawer (and its 6-tab layout, EvidenceChatPanel, etc.)
 * completely unchanged while integrating with the new MapLibre map.
 */

import MapRecordDrawer from "@/components/map/MapRecordDrawer";
import { judgeMapRecordToMapDotRecord } from "./types";
import type { JudgeMapRecord } from "./types";

type Props = {
  record: JudgeMapRecord | null;
  onClose: () => void;
};

export default function JudgeMapDrawerBridge({ record, onClose }: Props) {
  const dotRecord = record ? judgeMapRecordToMapDotRecord(record) : null;
  return <MapRecordDrawer record={dotRecord} onClose={onClose} />;
}
