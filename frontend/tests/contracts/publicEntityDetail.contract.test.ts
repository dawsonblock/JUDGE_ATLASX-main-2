import { describe, expect, it } from "vitest";

import { publicEntityDetailSchema } from "@/lib/schemas";

describe("publicEntityDetailSchema", () => {
  it("accepts a valid entity detail payload", () => {
    const payload = {
      entity_id: "event-123",
      review_status: "verified_court_record",
      public_visibility: true,
      summary: "Reviewed legal summary",
      source_key: "court_ca_sk",
    };
    expect(publicEntityDetailSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects legacy approved review status", () => {
    const payload = {
      entity_id: "event-123",
      review_status: "approved",
      public_visibility: true,
    };
    expect(publicEntityDetailSchema.safeParse(payload).success).toBe(false);
  });
});
