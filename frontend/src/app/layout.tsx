import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";

import { Providers } from "@/components/providers";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
// Mono is for hashes and IDs only.
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  // Canonical public origin; the vercel.app addresses redirect here.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://reliefmesh.us"),
  title: "ReliefMesh | Procurement that recovers",
  description: "Emergency procurement coordination with real RFQs, approvals, and replanning.",
  openGraph: { siteName: "ReliefMesh", url: "/", title: "ReliefMesh | Procurement that recovers" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className={`${inter.variable} ${geistMono.variable} h-full`}><body className="min-h-full"><Providers>{children}</Providers></body></html>;
}
