import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("Playwright relay configuration", () => {
  it("connects to the configured Docker relay instead of launching a local browser", async () => {
    vi.stubEnv("PW_TEST_CONNECT_WS_ENDPOINT", "ws://relay.test:3000/");
    vi.stubEnv("PW_TEST_CONNECT_EXPOSE_NETWORK", "<loopback>");

    const { default: config } = await import("../playwright.config");

    expect(config.use).toMatchObject({
      connectOptions: {
        wsEndpoint: "ws://relay.test:3000/",
        exposeNetwork: "<loopback>",
      },
    });
  });
});
