"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Scale } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/crime-map", label: "Crime Map" },
  { href: "/judges", label: "Judges" },
  { href: "/cases", label: "Cases" },
  { href: "/defendants", label: "Defendants" },
  { href: "/sources", label: "Sources" },
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-700 bg-slate-900 text-slate-100">
      <div className="container mx-auto flex h-14 items-center gap-4 px-4">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <Scale className="h-5 w-5 text-blue-400" />
          <span className="hidden sm:inline">JUDGE Tracker</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1 ml-4">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm transition-colors",
                pathname === link.href
                  ? "bg-slate-700 text-white"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex-1" />

        {/* Admin link */}
        <Link
          href="/admin"
          className={cn(
            "hidden md:inline-flex rounded-md px-3 py-1.5 text-sm transition-colors",
            pathname.startsWith("/admin")
              ? "bg-slate-700 text-white"
              : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          )}
        >
          Admin
        </Link>

        {/* Mobile hamburger */}
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden text-slate-300 hover:text-white hover:bg-slate-800">
              <Menu className="h-5 w-5" />
              <span className="sr-only">Open menu</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-64 bg-slate-900 border-slate-700 p-0">
            <div className="flex items-center gap-2 h-14 px-4 border-b border-slate-700">
              <Scale className="h-5 w-5 text-blue-400" />
              <span className="font-semibold text-slate-100">JUDGE Tracker</span>
            </div>
            <nav className="flex flex-col gap-1 p-3">
              {[...NAV_LINKS, { href: "/admin", label: "Admin" }].map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "rounded-md px-3 py-2 text-sm transition-colors",
                    pathname === link.href
                      ? "bg-slate-700 text-white"
                      : "text-slate-300 hover:bg-slate-800 hover:text-white"
                  )}
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  );
}
