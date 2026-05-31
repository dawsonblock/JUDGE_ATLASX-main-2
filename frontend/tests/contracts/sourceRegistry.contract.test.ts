import { describe, expect, it } from "vitest";

import { sourceRegistryListResponseSchema } from "@/lib/schemas";

describe("sourceRegistryListResponseSchema", () => {
  it("accepts source registry list payload", () => {
    const payload = {
      items: [
        {
          source_key: "ca-sk-court-001",
          source_url: "https://courts.example.ca/cases",
          is_active: true,
          source_type: "court_record",
        },
      ],
    };
    expect(sourceRegistryListResponseSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects invalid source url", () => {
    const payload = {
      items: [
        {
          source_key: "ca-sk-court-001",
          source_url: "not-a-url",
          is_active: true,
        },
      ],
    };
    expect(sourceRegistryListResponseSchema.safeParse(payload).success).toBe(false);
  });
});
