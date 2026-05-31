import { z } from "zod";

export const CANONICAL_REVIEW_STATUSES = [
  "verified_court_record",
  "official_police_open_data_report",
  "official_statistics_aggregate",
  "corrected",
  "pending_review",
  "news_only_context",
  "disputed",
  "rejected",
  "removed_from_public",
] as const;

export type CanonicalReviewStatus = (typeof CANONICAL_REVIEW_STATUSES)[number];

// Only the four public-domain statuses may appear on the public map.
// Non-public statuses (pending_review, news_only_context, disputed, rejected,
// removed_from_public) must never be sent to the frontend public map endpoint.
export const PUBLIC_MAP_REVIEW_STATUSES = [
  "verified_court_record",
  "official_police_open_data_report",
  "official_statistics_aggregate",
  "corrected",
] as const;

export type PublicMapReviewStatus = (typeof PUBLIC_MAP_REVIEW_STATUSES)[number];

export const publicMapMarkerSchema = z.object({
  entity_id: z.string(),
  entity_type: z.string(),
  lat: z.number(),
  lon: z.number(),
  label: z.string(),
  review_status: z.enum(PUBLIC_MAP_REVIEW_STATUSES),
  public_visibility: z.literal(true),
  source_quality: z.string(),
  evidence_type: z.string().optional(),
  evidence_status: z.string().optional(),
  precision_level: z.enum(["general_area", "city_centroid", "district"]).optional(),
  area_label: z.string().optional(),
}).strict();

export const publicMapMarkersResponseSchema = z.object({
  items: z.array(publicMapMarkerSchema),
});

export type PublicMapMarker = z.infer<typeof publicMapMarkerSchema>;
export type PublicMapMarkersResponse = z.infer<typeof publicMapMarkersResponseSchema>;
