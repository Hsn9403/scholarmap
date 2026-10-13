import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export default function robots(): MetadataRoute.Robots {
  return {
    // Reports are about named people: only the landing page is meant to be indexed
    rules: { userAgent: "*", allow: "/$", disallow: ["/report/", "/coauthor/", "/analyze/", "/api/", "/graphs/"] },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
