import { NextResponse, type NextRequest } from "next/server";

// Integrations moved into /settings. Old links and the API's OAuth return
// (/settings/integrations?org=…&google=connected|error&reason=…) still land on the right tab.
export function GET(request: NextRequest) {
  const target = new URL("/settings", request.url);
  target.searchParams.set("tab", "integrations");
  for (const [key, value] of request.nextUrl.searchParams) if (key !== "tab") target.searchParams.append(key, value);
  return NextResponse.redirect(target, 307);
}
