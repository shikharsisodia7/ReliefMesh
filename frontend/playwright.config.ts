import { defineConfig, devices } from "@playwright/test";

const relayEndpoint = process.env.PW_TEST_CONNECT_WS_ENDPOINT;
const relayOptions = relayEndpoint
  ? {
      connectOptions: {
        wsEndpoint: relayEndpoint,
        ...(process.env.PW_TEST_CONNECT_EXPOSE_NETWORK
          ? { exposeNetwork: process.env.PW_TEST_CONNECT_EXPOSE_NETWORK }
          : {}),
      },
    }
  : {};

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  // localhost, not 127.0.0.1: the API's CORS allowlist accepts the localhost origin.
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", ...devices["Desktop Chrome"], ...relayOptions },
  reporter: "list",
});
