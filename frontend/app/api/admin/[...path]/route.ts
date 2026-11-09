import { NextResponse, type NextRequest } from "next/server";
import { COOKIE, verify } from "@/lib/admin-auth";

/* Same-origin proxy for console requests. The browser never sees the API's admin key: this handler checks the
   console cookie, then forwards to the API with `X-API-Key` from the server-side environment. */

const UPSTREAM = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ADMIN_KEY = process.env.ADMIN_API_KEY ?? "dev-admin-key";

export const dynamic = "force-dynamic";

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  if (!(await verify(req.cookies.get(COOKIE)?.value))) return NextResponse.json({ detail: "Console login required" }, { status: 401 });
  const path = (await ctx.params).path.join("/");
  const upstream = await fetch(`${UPSTREAM}/api/v1/${path}${req.nextUrl.search}`, {
    method: req.method,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": req.headers.get("content-type") ?? "application/json",
      "X-API-Key": ADMIN_KEY,
    },
    body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.text(),
  });
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
  });
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
