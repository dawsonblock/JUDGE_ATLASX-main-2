import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const root = path.resolve(__dirname, "../../");
const pagePath = path.join(root, "app/records/[record_type]/[id]/page.tsx");

describe("records detail route contract", () => {
  it("uses typed map-record endpoint for court_event and reported_incident route shape", () => {
    const source = fs.readFileSync(pagePath, "utf8");
    expect(source).toContain("ALLOWED_RECORD_TYPES = new Set([\"court_event\", \"reported_incident\"])");
    expect(source).toContain("/api/map/record/");
  });

  it("does not reference legacy /api/v1/records endpoint", () => {
    const source = fs.readFileSync(pagePath, "utf8");
    expect(source).not.toContain("/api/v1/records");
  });
});
