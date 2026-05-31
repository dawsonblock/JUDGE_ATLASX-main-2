import { afterEach, describe, expect, it, vi } from "vitest";

import { disableSource, enableSource, triggerSourceRun } from "@/lib/api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("admin mutation helpers", () => {
  it("uses csrf flow for enable/disable/run mutations", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "abcdef1234567890" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ source_key: "test_source" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "abcdef1234567890" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ source_key: "test_source" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "abcdef1234567890" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            run_id: 1,
            source_key: "test_source",
            records_fetched: 0,
            records_skipped: 0,
            created_records: 0,
            review_items: 0,
            errors: [],
            success: true,
            adapter_records: 0,
            duplicates_skipped: 0,
            job_id: null,
            run_mode: "manual",
          }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
      );

    await enableSource("test_source");
    await disableSource("test_source");
    await triggerSourceRun("test_source");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/admin/csrf",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/admin/sources/test_source/enable",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "x-jta-csrf-token": "abcdef1234567890",
        }),
      }),
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/admin/csrf",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/admin/sources/test_source/disable",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "x-jta-csrf-token": "abcdef1234567890",
        }),
      }),
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/api/admin/csrf",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/api/admin/sources/test_source/run",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "x-jta-csrf-token": "abcdef1234567890",
        }),
      }),
    );
  });
});
