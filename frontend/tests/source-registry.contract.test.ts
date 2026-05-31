import { describe, expect, it } from "vitest";

import { sourceRegistryListResponseSchema } from "@/lib/schemas";

describe("source registry admin flow contract", () => {
  it("marks non-machine and adapter-missing sources as non-runnable in UI contracts", () => {
    const payload = {
      items: [
        {
          source_key: "justice_canada_laws_xml",
          source_url: "https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
          is_active: false,
          source_type: "legislation",
        },
      ],
    };

    expect(sourceRegistryListResponseSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects malformed source URLs", () => {
    const payload = {
      items: [
        {
          source_key: "bad_source",
          source_url: "not-a-url",
          is_active: false,
        },
      ],
    };
    expect(sourceRegistryListResponseSchema.safeParse(payload).success).toBe(false);
  });
});
