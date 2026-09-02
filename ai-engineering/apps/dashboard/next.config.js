const path = require("path")

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
}

if (process.env.AIED_STATIC_EXPORT === "1") {
  nextConfig.output = "export"
}

module.exports = nextConfig

