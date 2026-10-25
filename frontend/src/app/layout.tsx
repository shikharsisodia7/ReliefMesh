import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Providers } from "@/components/providers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  // Canonical public origin; the vercel.app addresses redirect here.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://reliefmesh.us"),
  title: "ReliefMesh | Procurement that recovers",
  description: "Emergency procurement coordination with real RFQs, approvals, and replanning.",
  openGraph: { siteName: "ReliefMesh", url: "/", title: "ReliefMesh | Procurement that recovers" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full`}><body className="min-h-full"><Providers>{children}</Providers></body></html>;
}
