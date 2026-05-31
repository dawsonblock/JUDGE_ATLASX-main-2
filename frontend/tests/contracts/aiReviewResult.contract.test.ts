import { describe, expect, it } from "vitest";

import { aiReviewResultSchema } from "@/lib/schemas";

describe("aiReviewResultSchema", () => {
  it("accepts valid AI review results", () => {
    const payload = {
      review_item_id: 10,
      status: "approved",
      confidence: 0.97,
      reason: "Strong source support",
    };
    expect(aiReviewResultSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects unknown status", () => {
    const payload = {
      review_item_id: 10,
      status: "blocked",
    };
    expect(aiReviewResultSchema.safeParse(payload).success).toBe(false);
  });
});
