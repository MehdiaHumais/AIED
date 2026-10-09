const path = require("path")

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.AIED_API_PROXY || "http://127.0.0.1:8001"}/api/:path*`,
      },
    ]
  },
}

if (process.env.AIED_STATIC_EXPORT === "1") {
  nextConfig.output = "export"
}

module.exports = nextConfig

