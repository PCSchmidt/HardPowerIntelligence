import type { Metadata } from "next";
import { Inter, Lora, Playfair_Display } from "next/font/google";
import "./globals.css";
import { NavBar } from "@/components/layout/navbar";
import { Footer } from "@/components/layout/footer";
import { AppProviders } from "@/components/providers";

const playfair = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-playfair",
  display: "swap",
});

const lora = Lora({
  subsets: ["latin"],
  variable: "--font-lora",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Hard Power Intelligence — Defense, Energy & AI Infrastructure Briefings",
    template: "%s — Hard Power Intelligence",
  },
  description:
    "Daily cited intelligence briefs for defense, energy, and AI infrastructure investors and analysts. Every claim links to its source.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${playfair.variable} ${lora.variable} ${inter.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AppProviders>
          <NavBar />
          <main className="flex-1">{children}</main>
          <Footer />
        </AppProviders>
      </body>
    </html>
  );
}
