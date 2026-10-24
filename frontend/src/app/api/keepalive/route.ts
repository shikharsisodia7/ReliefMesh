import { connection } from "next/server";

// Vercel Cron target: keeps the free-tier Render API warm so judges never hit a cold start.
// Vercel sends `Authorization: Bearer $CRON_SECRET` to cron routes; anything else is refused.
const noStore = { "Cache-Control": "no-store, private" };

export async function GET(request: Request) {
  await connection(); // always evaluated per request, never cached
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return Response.json({ error: "unauthorized" }, { status: 401, headers: noStore });
  }
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const started = Date.now();
  try {
    const response = await fetch(`${base}/health`, { cache: "no-store", signal: AbortSignal.timeout(55_000) });
    return Response.json({ api: response.status, ms: Date.now() - started }, { headers: noStore });
  } catch (error) {
    console.error("keepalive: API unreachable", error);
    return Response.json({ api: "unreachable", ms: Date.now() - started }, { status: 502, headers: noStore });
  }
}
