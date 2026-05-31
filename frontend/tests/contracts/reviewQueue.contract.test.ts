import { describe, expect, it } from "vitest";

import { reviewQueueListResponseSchema } from "@/lib/schemas";

describe("reviewQueueListResponseSchema", () => {
  it("accepts review queue items", () => {
    const payload = {
      items: [
        {
          id: 1,
          action: "publish",
          status: "pending",
          entity_type: "event",
          entity_id: "event-1",
        },
      ],
    };
    expect(reviewQueueListResponseSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects non-integer item ids", () => {
    const payload = {
      items: [{ id: 1.2, action: "publish", status: "pending" }],
    };
    expect(reviewQueueListResponseSchema.safeParse(payload).success).toBe(false);
  });
});
