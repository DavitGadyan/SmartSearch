import type { NextConfig } from "next";

// server-side API origin (compose: http://api:8000); the browser uses NEXT_PUBLIC_API_URL
const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  devIndicators: false, // no dev badge in screenshots and recordings
  images: { formats: ["image/avif", "image/webp"], minimumCacheTTL: 86400 },
  async headers() {
    // product imagery changes only when regenerated; a day in the browser cache, a week stale while revalidating
    return [{ source: "/img/:path*", headers: [{ key: "Cache-Control", value: "public, max-age=86400, stale-while-revalidate=604800" }] }];
  },
  async rewrites() {
    // representative product photos are served by the API from its data folder; same-origin here so next/image can optimise them
    return [{ source: "/img/photos/:path*", destination: `${API_URL}/static/photos/:path*` }];
  },
  async redirects() {
    // the console went from seven pages to four
    return [
      { source: "/admin/users", destination: "/admin/shoppers", permanent: false },
      { source: "/admin/recommendations", destination: "/admin/shoppers", permanent: false },
      { source: "/admin/ranking", destination: "/admin/search", permanent: false },
      { source: "/admin/opportunities", destination: "/admin", permanent: false },
    ];
  },
};

export default nextConfig;
