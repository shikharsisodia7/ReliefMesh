import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TelegramSettings } from "./telegram-settings";

function renderSettings() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><TelegramSettings token="supplier-session" /></QueryClientProvider>);
}

describe("TelegramSettings", () => {
  it("creates a short-lived link and opens the configured bot", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ legal_name: "Harbor Supply" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        code: "one-time-code", bot_username: "ReliefMeshBot", bot_url: "https://t.me/ReliefMeshBot?start=one-time-code",
        expires_at: "2026-10-25T12:00:00Z",
      }) });
    vi.stubGlobal("fetch", fetchMock);
    renderSettings();
    const connect = await screen.findByRole("button", { name: "Connect Telegram" });
    await waitFor(() => expect(connect).toBeEnabled());
    fireEvent.click(connect);
    const link = await screen.findByRole("link", { name: "Open Telegram · @ReliefMeshBot" });
    expect(link).toHaveAttribute("href", "https://t.me/ReliefMeshBot?start=one-time-code");
    expect(link).toHaveAttribute("target", "_blank");
    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringMatching(/\/v1\/supplier\/telegram\/link-code$/),
      expect.objectContaining({ method: "POST", headers: expect.objectContaining({ Authorization: "Bearer supplier-session" }) }));
  });

  it("shows connected state and disconnects through the authenticated endpoint", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ telegram_user_id: "7391" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ disconnected: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    renderSettings();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Disconnect Telegram" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm disconnect" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/v1\/supplier\/telegram$/),
      expect.objectContaining({ method: "DELETE" })));
  });
});
