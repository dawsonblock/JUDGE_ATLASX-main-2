import { z } from "zod";

const sha256Hex = /^[a-f0-9]{64}$/i;

export const evidenceSnapshotSchema = z.object({
  id: z.number().int(),
  content_hash: z.string().regex(sha256Hex),
  source_url: z.string().url().nullable().optional(),
  fetched_at: z.string().datetime().nullable().optional(),
  is_truncated: z.boolean().optional(),
});

export type EvidenceSnapshot = z.infer<typeof evidenceSnapshotSchema>;
