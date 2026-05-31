import { describe, expect, it } from "vitest";

import {
  publicEntityDetailSchema,
  publicMapMarkersResponseSchema,
} from "@/lib/schemas";

describe("public map and detail contract", () => {
  it("accepts reviewed public map markers", () => {
    const payload = {
      items: [
        {
          entity_id: "event-1",
          entity_type: "event",
          lat: 52.13,
          lon: -106.67,
          label: "Reviewed",
          source_quality: "official_legislation",
          review_status: "verified_court_record",
          public_visibility: true,
          evidence_status: "verified",
        },
      ],
    };
    expect(publicMapMarkersResponseSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects approved status on public map marker", () => {
    const payload = {
      items: [
        {
          entity_id: "event-1",
          entity_type: "event",
          lat: 52.13,
          lon: -106.67,
          label: "Reviewed",
          source_quality: "official_legislation",
          review_status: "approved",
          public_visibility: true,
        },
      ],
    };
    expect(publicMapMarkersResponseSchema.safeParse(payload).success).toBe(false);
  });

  it("rejects pending_review status on public map marker", () => {
    const payload = {
      items: [
        {
          entity_id: "event-1",
          entity_type: "event",
          lat: 52.13,
          lon: -106.67,
          label: "Reviewed",
          source_quality: "official_legislation",
          review_status: "pending_review",
          public_visibility: true,
        },
      ],
    };
    expect(publicMapMarkersResponseSchema.safeParse(payload).success).toBe(false);
  });

  it("rejects missing review_status", () => {
    const payload = {
      items: [
        {
          entity_id: "event-1",
          entity_type: "event",
          lat: 52.13,
          lon: -106.67,
          label: "Reviewed",
          source_quality: "official_legislation",
          public_visibility: true,
        },
      ],
    };
    expect(publicMapMarkersResponseSchema.safeParse(payload).success).toBe(false);
  });

  it("rejects missing or false public_visibility", () => {
    const missingVisibility = {
      items: [
        {
          entity_id: "event-1",
          entity_type: "event",
          lat: 52.13,
          lon: -106.67,
          label: "Reviewed",
          source_quality: "official_legislation",
          review_status: "verified_court_record",
        },
      ],
    };
    const falseVisibility = {
      items: [
        {
          entity_id: "event-1",
          entity_type: "event",
          lat: 52.13,
          lon: -106.67,
          label: "Reviewed",
          source_quality: "official_legislation",
          review_status: "verified_court_record",
          public_visibility: false,
        },
      ],
    };
    expect(publicMapMarkersResponseSchema.safeParse(missingVisibility).success).toBe(
      false,
    );
    expect(publicMapMarkersResponseSchema.safeParse(falseVisibility).success).toBe(
      false,
    );
  });

  it("rejects private address fields", () => {
    const payload = {
      items: [
        {
          entity_id: "event-1",
          entity_type: "event",
          lat: 52.13,
          lon: -106.67,
          label: "Reviewed",
          source_quality: "official_legislation",
          review_status: "verified_court_record",
          public_visibility: true,
          exact_address: "123 Private Street",
        },
      ],
    };
    expect(publicMapMarkersResponseSchema.safeParse(payload).success).toBe(false);
  });

  it("accepts public entity detail shape for verified records", () => {
    const detail = {
      entity_id: "event-1",
      review_status: "verified_court_record",
      public_visibility: true,
      source_key: "justice_canada_laws_xml",
      summary: "Evidence-backed summary",
    };
    expect(publicEntityDetailSchema.safeParse(detail).success).toBe(true);
  });
});
