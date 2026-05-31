import { z } from "zod";

export const reviewQueueItemSchema = z.object({
  id: z.number().int(),
  action: z.string(),
  status: z.string(),
  entity_type: z.string().nullable().optional(),
  entity_id: z.string().nullable().optional(),
});

export const reviewQueueListResponseSchema = z.object({
  items: z.array(reviewQueueItemSchema),
});

export type ReviewQueueItem = z.infer<typeof reviewQueueItemSchema>;
export type ReviewQueueListResponse = z.infer<typeof reviewQueueListResponseSchema>;
