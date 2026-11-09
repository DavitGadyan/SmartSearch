/* Console access: one shared password (ADMIN_PASSWORD) exchanged for a signed, expiring cookie. WebCrypto only, so the
   same code runs in the Edge middleware and in Node route handlers. Changing the password invalidates every session. */

export const COOKIE = "ss_admin";
const TTL_SECONDS = 12 * 3600;
const enc = new TextEncoder();

const secret = () => process.env.ADMIN_SESSION_SECRET ?? process.env.ADMIN_PASSWORD ?? "";

async function hmac(message: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret()), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
  return Array.from(sig, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time string comparison. */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function mint(ttlSeconds = TTL_SECONDS): Promise<{ token: string; maxAge: number }> {
  const exp = Math.floor(Date.now() / 1000) + ttlSeconds;
  return { token: `${exp}.${await hmac(`admin:v1:${exp}`)}`, maxAge: ttlSeconds };
}

export async function verify(token: string | undefined): Promise<boolean> {
  if (!token || !secret()) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig || Number(exp) < Date.now() / 1000) return false;
  return safeEqual(sig, await hmac(`admin:v1:${exp}`));
}

export const cookieOptions = (maxAge: number) => ({
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
  maxAge,
});
