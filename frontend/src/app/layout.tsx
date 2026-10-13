import type { Metadata } from "next";
import { Montserrat } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";

const montserrat = Montserrat({ subsets: ["latin"], variable: "--font-montserrat" });

// Public URL of the deployed instance, used to build absolute Open Graph links
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const DESCRIPTION =
  "Scholarmap cartographie le réseau scientifique et industriel d'un chercheur à partir de sources publiques : co-auteurs, co-inventeurs, institutions, brevets, essais cliniques et liens avec l'industrie, dans une carte interactive et filtrable.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Scholarmap — cartographie du réseau d'un chercheur",
    template: "%s | Scholarmap",
  },
  description: DESCRIPTION,
  applicationName: "Scholarmap",
  keywords: [
    "cartographie réseau chercheur",
    "réseau de co-auteurs",
    "due diligence scientifique",
    "KOL mapping",
    "key opinion leaders",
    "research network map",
    "co-authorship network",
    "OpenAlex",
    "brevets",
    "patents",
    "essais cliniques",
    "clinical trials",
    "Open Payments",
    "Transparence Santé",
    "healthtech",
    "deeptech",
  ],
  authors: [{ name: "Scholarmap contributors", url: "https://github.com/Hsn9403/scholarmap" }],
  creator: "Scholarmap",
  category: "science",
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    siteName: "Scholarmap",
    title: "Scholarmap — cartographie du réseau d'un chercheur",
    description: DESCRIPTION,
    url: "/",
    locale: "fr_FR",
    alternateLocale: ["en_US"],
  },
  twitter: {
    card: "summary",
    title: "Scholarmap — cartographie du réseau d'un chercheur",
    description: DESCRIPTION,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr" className={`${montserrat.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-[#F8FAFC] font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
