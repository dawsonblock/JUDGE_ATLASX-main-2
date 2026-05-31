import { describe, expect, it } from "vitest";

import { evidenceSnapshotSchema } from "@/lib/schemas";

describe("evidenceSnapshotSchema", () => {
  it("accepts a valid evidence snapshot payload", () => {
    const payload = {
      id: 42,
      content_hash: "a".repeat(64),
      source_url: "https://records.example.ca/doc/42",
      fetched_at: "2026-01-10T20:00:00Z",
      is_truncated: false,
    };
    expect(evidenceSnapshotSchema.safeParse(payload).success).toBe(true);
  });

  it("rejects malformed content hash", () => {
    const payload = {
      id: 42,
      content_hash: "abc123",
    };
    expect(evidenceSnapshotSchema.safeParse(payload).success).toBe(false);
  });
});
