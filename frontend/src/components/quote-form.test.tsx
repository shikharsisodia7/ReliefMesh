import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { QuoteForm } from "./quote-form";

const requirements = [{ id: "req-1", item: "blankets", quantity: 100 }];

describe("QuoteForm", () => {
  it("starts number fields blank with a placeholder", () => {
    render(<QuoteForm requirements={requirements} assistant="off" onSubmit={vi.fn()} />);
    for (const label of ["Available quantity", "Unit price (USD)", "Shipping (USD)"]) {
      const input = screen.getByLabelText(label) as HTMLInputElement;
      expect(input.value).toBe("");
      expect(input.placeholder).not.toBe("");
    }
  });

  it("treats blank numbers as 0, so the old validation still applies", async () => {
    const onSubmit = vi.fn();
    render(<QuoteForm requirements={requirements} assistant="off" onSubmit={onSubmit} />);
    fireEvent.change(screen.getByLabelText("Legal business name"), { target: { value: "Sierra Backup Provisions" } });
    fireEvent.change(screen.getByLabelText("Quote expiration"), { target: { value: "2030-01-02T09:00" } });
    fireEvent.click(screen.getByLabelText("I reviewed the values and confirm they are correct."));
    fireEvent.click(screen.getByRole("button", { name: "Submit binding quote" }));
    expect(await screen.findByText("Quote at least one requirement")).toBeTruthy();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits filled values as numbers", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<QuoteForm requirements={requirements} assistant="off" onSubmit={onSubmit} />);
    fireEvent.change(screen.getByLabelText("Legal business name"), { target: { value: "Sierra Backup Provisions" } });
    fireEvent.change(screen.getByLabelText("Available quantity"), { target: { value: "30" } });
    fireEvent.change(screen.getByLabelText("Unit price (USD)"), { target: { value: "36.60" } });
    fireEvent.change(screen.getByLabelText("Delivery estimate"), { target: { value: "2030-01-03T09:00" } });
    fireEvent.change(screen.getByLabelText("Quote expiration"), { target: { value: "2030-01-02T09:00" } });
    fireEvent.click(screen.getByLabelText("I reviewed the values and confirm they are correct."));
    fireEvent.click(screen.getByRole("button", { name: "Submit binding quote" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const values = onSubmit.mock.calls[0][0];
    expect(values.shipping_cost).toBe(0);
    expect(values.lines[0]).toMatchObject({ available_quantity: 30, unit_price: 36.6 });
  });
});
