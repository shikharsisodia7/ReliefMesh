// Vercel Cron target: keeps the free-tier Render API warm so judges never hit a cold start.

export async function GET(request: Request) {
  const secret = process.env.CRON_SECRET;
  if (secret && request.headers.get("authorization") !== `Bearer ${secret}`) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const started = Date.now();
  try {
    const response = await fetch(`${base}/health`, { cache: "no-store", signal: AbortSignal.timeout(55_000) });
    return Response.json({ api: response.status, ms: Date.now() - started });
  } catch (error) {
    return Response.json({ api: "unreachable", error: String(error), ms: Date.now() - started }, { status: 502 });
  }
}
