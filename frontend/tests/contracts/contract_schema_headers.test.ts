import { describe, expect, it } from "vitest";

import { CONTRACT_NAMES, readContract } from "./_helpers";

describe("contract schema headers", () => {
  for (const name of CONTRACT_NAMES) {
    it(`${name} has required JSON Schema top-level fields`, () => {
      const doc = readContract(name);
      expect(typeof doc.$schema).toBe("string");
      expect(doc.type).toBe("object");
      expect(Array.isArray(doc.required)).toBe(true);
      const hasProperties = typeof doc.properties === "object" && doc.properties !== null;
      const hasItems = typeof doc.items === "object" && doc.items !== null;
      expect(hasProperties || hasItems).toBe(true);
    });
  }
});
