import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AuthForm } from "./auth-form";

describe("AuthForm", () => {
  it("registers a coordinator through the real API client contract", async () => {
    const onAuthenticated = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: "session-token", user: { id: "user-1", role: "coordinator" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AuthForm mode="register" defaultRole="coordinator" onAuthenticated={onAuthenticated} />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ops@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct horse battery staple" } });
    fireEvent.click(screen.getByRole("button", { name: "Create coordinator account" }));

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith("session-token", expect.any(Object)));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/v1\/auth\/register$/),
      expect.objectContaining({ method: "POST" }),
    );
  });
});
