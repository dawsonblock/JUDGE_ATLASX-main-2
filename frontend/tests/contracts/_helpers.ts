import fs from "node:fs";
import path from "node:path";

export const CONTRACT_NAMES = [
  "public_map_markers.json",
  "public_entity_detail.json",
  "source_registry.json",
  "review_queue_item.json",
  "evidence_snapshot.json",
  "ai_review_result.json",
  "error_response.json",
] as const;

export function contractsDir(): string {
  return path.resolve(__dirname, "../../../artifacts/contracts");
}

export function readContract(name: (typeof CONTRACT_NAMES)[number]): Record<string, unknown> {
  const full = path.join(contractsDir(), name);
  return JSON.parse(fs.readFileSync(full, "utf8")) as Record<string, unknown>;
}
