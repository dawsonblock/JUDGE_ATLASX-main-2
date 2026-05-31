import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

import LoginPage from "@/app/login/page";

describe("login form contract", () => {
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("submits email/password payload to auth proxy", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "TestPassword123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const [_url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(_url).toBe("/api/auth/login");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(
      JSON.stringify({
        email: "admin@example.com",
        password: "TestPassword123!",
      }),
    );

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/admin/sources");
      expect(refresh).toHaveBeenCalled();
    });
  });
});
