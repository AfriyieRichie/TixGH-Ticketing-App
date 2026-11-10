"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { SITE_NAME } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <Link href="/" className={`flex items-center gap-2 text-xl font-extrabold tracking-tight ${light ? "text-white" : "text-brand"}`}>
      <span className={`grid h-8 w-8 place-items-center rounded-lg text-base ${light ? "bg-white text-brand" : "bg-brand text-white"}`}>🎟</span>
      {SITE_NAME}
    </Link>
  );
}

export function Header() {
  const { user, ready, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const path = usePathname();
  if (path.startsWith("/dashboard")) return null; // dashboard has its own chrome

  const links = [
    { href: "/events", label: "Find events" },
    { href: "/dashboard", label: "Sell tickets" },
  ];
  return (
    <header className="sticky top-0 z-30 border-b border-zinc-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Logo />
        <nav className="hidden items-center gap-6 md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="font-medium text-zinc-700 hover:text-brand">{l.label}</Link>
          ))}
          {ready && (user ? (
            <>
              <Link href="/tickets" className="font-medium text-zinc-700 hover:text-brand">My tickets</Link>
              <button onClick={async () => { await signOut(); router.push("/"); }}
                className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-50">
                Sign out
              </button>
            </>
          ) : (
            <Link href={`/login?next=${encodeURIComponent(path)}`}
              className="rounded-lg bg-brand px-4 py-2 font-semibold text-white hover:bg-brand-dark">Sign in</Link>
          ))}
        </nav>
        <button className="rounded-lg p-2 md:hidden" aria-label="Menu" onClick={() => setOpen(!open)}>
          <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
      </div>
      {open && (
        <nav className="border-t border-zinc-200 px-4 py-3 md:hidden" onClick={() => setOpen(false)}>
          {links.map((l) => <Link key={l.href} href={l.href} className="block py-2 font-medium">{l.label}</Link>)}
          {user ? (
            <>
              <Link href="/tickets" className="block py-2 font-medium">My tickets</Link>
              <button onClick={() => signOut()} className="block py-2 font-medium text-red-600">Sign out</button>
            </>
          ) : (
            <Link href="/login" className="block py-2 font-semibold text-brand">Sign in</Link>
          )}
        </nav>
      )}
    </header>
  );
}

export function Footer() {
  const path = usePathname();
  if (path.startsWith("/dashboard")) return null;
  return (
    <footer className="mt-16 border-t border-zinc-200 bg-white">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm text-zinc-600 sm:grid-cols-3">
        <div>
          <Logo />
          <p className="mt-3">Tickets for concerts, conferences, church programs and more across Ghana. Pay with Mobile Money or card.</p>
        </div>
        <div className="space-y-2">
          <p className="font-semibold text-zinc-900">Attend</p>
          <Link href="/events" className="block hover:text-brand">Browse events</Link>
          <Link href="/tickets" className="block hover:text-brand">My tickets</Link>
        </div>
        <div className="space-y-2">
          <p className="font-semibold text-zinc-900">Organize</p>
          <Link href="/dashboard" className="block hover:text-brand">Sell tickets</Link>
          <p>Booking fee: paid tickets only. Free events are always free.</p>
        </div>
      </div>
      <p className="border-t border-zinc-100 py-4 text-center text-xs text-zinc-500">
        © {new Date().getFullYear()} {SITE_NAME}. Made in Ghana 🇬🇭 ·{" "}
        <Link href="/legal/terms" className="hover:text-brand">Terms</Link> ·{" "}
        <Link href="/legal/privacy" className="hover:text-brand">Privacy</Link> ·{" "}
        <Link href="/legal/refunds" className="hover:text-brand">Refunds</Link>
      </p>
    </footer>
  );
}
