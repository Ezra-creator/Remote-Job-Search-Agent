"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, CheckSquare, FileText, Send } from "lucide-react";

export default function Navigation() {
  const pathname = usePathname();

  const navItems = [
    { label: "Dashboard", href: "/", icon: LayoutDashboard },
    { label: "Review", href: "/review", icon: CheckSquare },
    { label: "Materials", href: "/materials", icon: FileText },
    { label: "Applied", href: "/applied", icon: Send },
  ];

  return (
    <>
      {/* Top Desktop & Mobile Header */}
      <header className="sticky top-0 z-40 w-full border-b border-line bg-ink text-paper" role="banner">
        <div className="mx-auto flex h-12 max-w-4xl items-center justify-between px-4 sm:px-6">
          <Link
            href="/"
            className="font-semibold tracking-tight text-paper text-sm font-sans focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-paper rounded"
            aria-label="RJS Home"
          >
            RJS
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden md:flex items-center gap-6" aria-label="Desktop Navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-paper rounded ${
                    isActive
                      ? "text-paper border-b border-paper pb-0.5"
                      : "text-muted hover:text-paper"
                  }`}
                  aria-current={isActive ? "page" : undefined}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="font-mono text-xs text-muted" aria-label="Network status">
            Tailscale
          </div>
        </div>
      </header>

      {/* Mobile Bottom Navigation */}
      <nav
        className="fixed bottom-0 left-0 right-0 z-50 md:hidden border-t border-line bg-ink text-paper"
        aria-label="Mobile Navigation"
      >
        <div className="grid grid-cols-4 max-w-md mx-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center justify-center py-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-paper ${
                  isActive
                    ? "text-paper font-semibold bg-white/5"
                    : "text-muted hover:text-paper"
                }`}
                aria-current={isActive ? "page" : undefined}
                aria-label={item.label}
              >
                <Icon className="h-4 w-4 mb-0.5" aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
