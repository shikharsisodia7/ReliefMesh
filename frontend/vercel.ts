export const config = {
  framework: "nextjs",
  buildCommand: "npm run build",
  // Ping the Render free-tier API every 10 minutes so it never sleeps (cold starts take ~50 s).
  crons: [{ path: "/api/keepalive", schedule: "*/10 * * * *" }],
} as const;
