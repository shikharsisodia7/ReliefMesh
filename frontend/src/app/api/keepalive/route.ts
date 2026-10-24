import { connection } from "next/server";

// Vercel Cron target: keeps the free-tier Render API and Fetch.ai agent warm so judges never hit a cold start.
// Vercel sends `Authorization: Bearer $CRON_SECRET` to cron routes; anything else is refused.
const noStore = { "Cache-Control": "no-store, private" };

async function ping(url: string) {
  const started = Date.now();
  try {
    const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(55_000) });
    return { status: response.status, ms: Date.now() - started };
  } catch (error) {
    console.error("keepalive: unreachable", url, error);
    return { status: "unreachable", ms: Date.now() - started };
  }
}

export async function GET(request: Request) {
  await connection(); // always evaluated per request, never cached
  const secret = process.env.CRON_SECRET;
  if (!secret || request.headers.get("authorization") !== `Bearer ${secret}`) {
    return Response.json({ error: "unauthorized" }, { status: 401, headers: noStore });
  }
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const agent = process.env.AGENT_HEALTH_URL;
  const [api, agentStatus] = await Promise.all([ping(`${base}/health`), agent ? ping(agent) : Promise.resolve(null)]);
  console.log("keepalive", JSON.stringify({ api, agent: agentStatus })); // one line per cron run, visible in runtime logs
  return Response.json({ api, agent: agentStatus }, { status: api.status === 200 ? 200 : 502, headers: noStore });
}
