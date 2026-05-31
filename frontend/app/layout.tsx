import type { Metadata } from "next";
import "./globals.css";
import { AppShell, TopNav } from "@/components/layout";

export const metadata: Metadata = {
  title: "JUDGE Tracker",
  description: "Judicial and legal incident intelligence tracker.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <AppShell>
          <TopNav />
          <main className="flex-1 container mx-auto px-4 py-6">
            {children}
          </main>
        </AppShell>
      </body>
    </html>
  );
}

