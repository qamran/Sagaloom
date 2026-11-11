import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Inter, Newsreader } from "next/font/google";
import { Header } from "@/components/Header";
import { Providers } from "@/components/Providers";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });
const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sagaloom",
  description: "A continuity editor for fictional worlds.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${newsreader.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <ClerkProvider signInUrl="/sign-in" signUpUrl="/sign-up">
          <Providers>
            <Header />
            {children}
          </Providers>
        </ClerkProvider>
      </body>
    </html>
  );
}
