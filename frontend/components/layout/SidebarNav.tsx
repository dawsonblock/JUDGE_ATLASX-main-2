"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

interface SidebarNavItem {
  href: string;
  label: string;
  icon?: React.ReactNode;
}

interface SidebarNavProps {
  items: SidebarNavItem[];
  className?: string;
}

export function SidebarNav({ items, className }: SidebarNavProps) {
  const pathname = usePathname();

  return (
    <nav className={cn("flex flex-col gap-1", className)}>
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
            pathname === item.href
              ? "bg-slate-100 text-slate-900 font-medium"
              : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          )}
        >
          {item.icon}
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
