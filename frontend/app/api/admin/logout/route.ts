import { NextResponse } from "next/server";
import { COOKIE, cookieOptions } from "@/lib/admin-auth";

export async function POST() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE, "", cookieOptions(0));
  return res;
}
