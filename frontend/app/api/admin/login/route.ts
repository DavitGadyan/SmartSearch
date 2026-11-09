import { NextResponse, type NextRequest } from "next/server";
import { COOKIE, cookieOptions, mint, safeEqual } from "@/lib/admin-auth";

export async function POST(req: NextRequest) {
  const expected = process.env.ADMIN_PASSWORD;
  if (!expected) return NextResponse.json({ detail: "ADMIN_PASSWORD is not configured" }, { status: 503 });
  const { password = "" } = (await req.json().catch(() => ({}))) as { password?: string };
  if (!safeEqual(String(password), expected)) return NextResponse.json({ detail: "Wrong keyword" }, { status: 401 });
  const { token, maxAge } = await mint();
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, token, cookieOptions(maxAge));
  return res;
}
