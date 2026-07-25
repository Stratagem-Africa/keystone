import type { Metadata } from "next";
import { Inter, Newsreader, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/lib/auth-context";
import "./globals.css";

// Grotesque — chrome, wordmark, UI labels, hero headlines.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

// Serif — model-reasoned prose: report body, ADR rationale, "where this is wrong".
const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
});

// Mono — every engine-computed number, metric, band label, provenance tag.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "keystone",
  description: "The model reasons. The engine computes.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${newsreader.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans bg-paper text-slate-ink">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
