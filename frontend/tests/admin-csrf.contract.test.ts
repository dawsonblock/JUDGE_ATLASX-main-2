import { describe, expect, it } from "vitest";

import {
  ADMIN_CSRF_COOKIE_NAME,
  ADMIN_CSRF_HEADER_NAME,
  hasValidAdminCsrf,
} from "@/app/api/admin/_auth";

describe("admin csrf contract", () => {
  it("accepts matching csrf header and cookie", () => {
    const token = "abcdef1234567890";
    const req = new Request("http://localhost/api/admin/sources/demo/enable", {
      method: "POST",
      headers: {
        cookie: `${ADMIN_CSRF_COOKIE_NAME}=${token}`,
        [ADMIN_CSRF_HEADER_NAME]: token,
      },
    });

    expect(hasValidAdminCsrf(req)).toBe(true);
  });

  it("rejects missing csrf header", () => {
    const token = "abcdef1234567890";
    const req = new Request("http://localhost/api/admin/sources/demo/enable", {
      method: "POST",
      headers: {
        cookie: `${ADMIN_CSRF_COOKIE_NAME}=${token}`,
      },
    });

    expect(hasValidAdminCsrf(req)).toBe(false);
  });

  it("rejects non-matching csrf header and cookie", () => {
    const req = new Request("http://localhost/api/admin/sources/demo/enable", {
      method: "POST",
      headers: {
        cookie: `${ADMIN_CSRF_COOKIE_NAME}=abcdef1234567890`,
        [ADMIN_CSRF_HEADER_NAME]: "fedcba0987654321",
      },
    });

    expect(hasValidAdminCsrf(req)).toBe(false);
  });
});
