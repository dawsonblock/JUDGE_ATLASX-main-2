import { describe, expect, it } from "vitest";

import { buildIncidentParams } from "@/app/map/MapWorkspace";

describe("MapWorkspace incident filters", () => {
  it("uses incident_category instead of legacy category key", () => {
    const params = buildIncidentParams({
      bbox: null,
      incidentType: "individual",
      jurisdiction: "",
      sourceName: "",
      dateFrom: "",
      dateTo: "",
      category: "violent",
    });

    expect(params.incident_category).toBe("violent");
    expect(params).not.toHaveProperty("category");
  });
});
