import { afterEach, describe, expect, it, vi } from "vitest";

import { POST as enablePost } from "@/app/api/admin/sources/[sourceKey]/enable/route";
import { POST as runPost } from "@/app/api/admin/sources/[sourceKey]/run/route";


function reqWith(headers: Record<string, string>) {
  return new Request("http://localhost/api/admin/sources/test/enable", {
    method: "POST",
    headers,
  }) as any;
}


afterEach(() => {
  vi.restoreAllMocks();
});


describe("admin source mutation proxy contracts", () => {
  it("rejects enable when csrf token is missing", async () => {
    const response = await enablePost(reqWith({}), {
      params: { sourceKey: "justice_canada_laws_xml" },
    });
    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toMatchObject({
      error: "CSRF validation failed for admin mutation",
    });
  });

  it("rejects enable when auth is missing even with csrf token", async () => {
    const csrf = "abcdef1234567890";
    const response = await enablePost(
      reqWith({
        cookie: `jta_admin_csrf=${csrf}`,
        "x-jta-csrf-token": csrf,
      }),
      { params: { sourceKey: "justice_canada_laws_xml" } },
    );
    expect(response.status).toBe(503);
  });

  it("passes missing-secret 422 from backend enable route", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          source_key: "canlii_sk",
          reason: "Source requires JTA_CANLII_API_KEY before it can be enabled or run.",
          missing_secret: "JTA_CANLII_API_KEY",
        }),
        { status: 422, headers: { "content-type": "application/json" } },
      ),
    );

    const csrf = "abcdef1234567890";
    const response = await enablePost(
      reqWith({
        cookie: `jta_access_token=fake; jta_admin_csrf=${csrf}`,
        "x-jta-csrf-token": csrf,
      }),
      { params: { sourceKey: "canlii_sk" } },
    );

    expect(response.status).toBe(422);
    await expect(response.json()).resolves.toMatchObject({
      missing_secret: "JTA_CANLII_API_KEY",
    });
  });

  it("passes adapter-missing 501 from backend run route", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          source_key: "stub_source",
          reason: "No registered adapter exists for this machine_ingest source.",
        }),
        { status: 501, headers: { "content-type": "application/json" } },
      ),
    );

    const csrf = "abcdef1234567890";
    const response = await runPost(
      reqWith({
        cookie: `jta_access_token=fake; jta_admin_csrf=${csrf}`,
        "x-jta-csrf-token": csrf,
      }),
      { params: { sourceKey: "stub_source" } },
    );

    expect(response.status).toBe(501);
    await expect(response.json()).resolves.toMatchObject({
      reason: "No registered adapter exists for this machine_ingest source.",
    });
  });
});
