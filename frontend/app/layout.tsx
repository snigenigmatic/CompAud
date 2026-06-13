import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CompAud — Compliance Evidence Audit",
  description: "Automated compliance evidence collection, linking, and auditor-ready reporting.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body>{children}</body>
    </html>
  );
}
