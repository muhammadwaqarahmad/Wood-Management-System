/** @type {import('next').NextConfig} */

// In local dev the browser talks ONLY to the Next server (same origin) and Next
// proxies /api/* to the backend server-side. This sidesteps CORS entirely and
// the Windows localhost/IPv6 mismatch. In production, set NEXT_PUBLIC_API_URL to
// the real API URL instead (then calls go direct and this proxy is unused).
const API_TARGET = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // Hide Next's floating dev badge (it was overlapping the sidebar).
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_TARGET}/:path*` }];
  },
};

export default nextConfig;
