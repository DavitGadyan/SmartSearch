import { NextResponse, type NextRequest } from "next/server";
import { COOKIE, verify } from "@/lib/admin-auth";

/** The console lives behind a password: no valid cookie, no /admin page (the API proxy under /api/admin checks too). */
export async function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (pathname === "/admin/login") return NextResponse.next();
  if (await verify(req.cookies.get(COOKIE)?.value)) return NextResponse.next();
  const login = new URL("/admin/login", req.url);
  login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = { matcher: ["/admin", "/admin/:path*"] };
