import { z } from "zod";

export const errorResponseSchema = z.object({
  detail: z.union([z.string(), z.array(z.record(z.unknown()))]),
});

export type ErrorResponse = z.infer<typeof errorResponseSchema>;
