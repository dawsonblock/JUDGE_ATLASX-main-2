import { describe, expect, it } from "vitest";

import { reviewQueueListResponseSchema } from "@/lib/schemas";

describe("review flow contract", () => {
  it("accepts pending review queue items", () => {
    const payload = {
      items: [
        {
          id: 10,
          action: "publish",
          status: "pending",
          entity_type: "legal_section",
          entity_id: "sec-1",
        },
      ],
    };

    expect(reviewQueueListResponseSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects non-integer ids", () => {
    const payload = {
      items: [{ id: 10.5, action: "publish", status: "pending" }],
    };

    expect(reviewQueueListResponseSchema.safeParse(payload).success).toBe(false);
  });
});
