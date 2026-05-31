import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { CONTRACT_NAMES, contractsDir } from "./_helpers";

describe("contracts presence", () => {
  it("contains all expected contract JSON files", () => {
    const dir = contractsDir();
    for (const name of CONTRACT_NAMES) {
      expect(fs.existsSync(path.join(dir, name))).toBe(true);
    }
  });
});
