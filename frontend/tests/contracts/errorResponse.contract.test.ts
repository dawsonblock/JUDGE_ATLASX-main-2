import { describe, expect, it } from "vitest";

import { errorResponseSchema } from "@/lib/schemas";

describe("errorResponseSchema", () => {
  it("accepts string detail", () => {
    expect(errorResponseSchema.safeParse({ detail: "not found" }).success).toBe(true);
  });

  it("accepts list detail", () => {
    const payload = {
      detail: [{ loc: ["body", "field"], msg: "required", type: "value_error" }],
    };
    expect(errorResponseSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects missing detail", () => {
    expect(errorResponseSchema.safeParse({}).success).toBe(false);
  });
});
