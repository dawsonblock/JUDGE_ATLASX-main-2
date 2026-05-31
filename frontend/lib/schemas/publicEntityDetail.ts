import { z } from "zod";

export const publicEntityDetailSchema = z.object({
  entity_id: z.string(),
  review_status: z.enum([
    "verified_court_record",
    "official_police_open_data_report",
    "official_statistics_aggregate",
    "corrected",
  ]),
  public_visibility: z.literal(true),
  summary: z.string().nullable().optional(),
  source_key: z.string().nullable().optional(),
}).strict();

export type PublicEntityDetail = z.infer<typeof publicEntityDetailSchema>;
