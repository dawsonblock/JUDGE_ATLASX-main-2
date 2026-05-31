import { z } from "zod";

export const aiReviewResultSchema = z.object({
  review_item_id: z.number().int(),
  status: z.enum(["approved", "rejected", "needs_review"]),
  confidence: z.number().nullable().optional(),
  reason: z.string().nullable().optional(),
});

export type AiReviewResult = z.infer<typeof aiReviewResultSchema>;
