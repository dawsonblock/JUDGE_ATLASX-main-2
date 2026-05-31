import { z } from "zod";

export const sourceRegistryItemSchema = z.object({
  source_key: z.string(),
  source_url: z.string().url(),
  is_active: z.boolean(),
  source_type: z.string().nullable().optional(),
});

export const sourceRegistryListResponseSchema = z.object({
  items: z.array(sourceRegistryItemSchema),
});

export type SourceRegistryItem = z.infer<typeof sourceRegistryItemSchema>;
export type SourceRegistryListResponse = z.infer<typeof sourceRegistryListResponseSchema>;
