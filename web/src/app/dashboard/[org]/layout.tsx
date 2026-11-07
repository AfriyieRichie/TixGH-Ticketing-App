"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Logo } from "@/components/Header";
import { OrgContext } from "@/components/dashboard/org";
import { RequireAuth } from "@/components/RequireAuth";
import { Alert, Badge, PageLoader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import type { Organization } from "@/lib/types";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <RequireAuth><Shell>{children}</Shell></RequireAuth>;
}

function Shell({ children }: { children: React.ReactNode }) {
  const { org: slug } = useParams<{ org: string }>();
  const path = usePathname();
  const { request, user, signOut } = useAuth();
  const [org, setOrg] = useState<Organization | null>(null);
  const [error, setError] = useState("");
  const [menu, setMenu] = useState(false);

  const reload = useCallback(() => {
    request<Organization>(`/organizations/${slug}/`).then(setOrg).catch(() => setError("Organizer not found, or you're not on its team."));
  }, [request, slug]);
  useEffect(reload, [reload]);

  if (error) return <main className="mx-auto max-w-md px-4 py-20"><Alert>{error}</Alert><Link href="/dashboard" className="mt-4 block text-brand">← Back</Link></main>;
  if (!org) return <PageLoader />;

  const base = `/dashboard/${org.slug}`;
  const can = (p: string) => org.my_permissions.includes(p);
  const nav = [
    { href: base, label: "Overview", show: can("manage_events") || can("view_finance") },
    { href: `${base}/events`, label: "Events", show: true },
    { href: `${base}/settings`, label: "Settings", show: true },
  ].filter((n) => n.show);
  const active = (href: string) => (href === base ? path === base : path.startsWith(href));

  return (
    <OrgContext.Provider value={{ org, reload, can, base }}>
      <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
        <aside className="bg-zinc-900 text-zinc-300 lg:min-h-screen">
          <div className="flex items-center justify-between px-5 py-4">
            <Logo light />
            <button className="lg:hidden" onClick={() => setMenu(!menu)} aria-label="Menu">☰</button>
          </div>
          <div className={`${menu ? "block" : "hidden"} lg:block`}>
            <Link href="/dashboard" className="mx-3 mb-4 block rounded-lg bg-zinc-800 px-3 py-2 hover:bg-zinc-700">
              <p className="truncate font-semibold text-white">{org.name}</p>
              <p className="text-xs capitalize">{org.my_role} · switch</p>
            </Link>
            <nav className="space-y-1 px-3">
              {nav.map((n) => (
                <Link key={n.href} href={n.href} onClick={() => setMenu(false)}
                  className={`block rounded-lg px-3 py-2 font-medium ${active(n.href) ? "bg-brand text-white" : "hover:bg-zinc-800 hover:text-white"}`}>
                  {n.label}
                </Link>
              ))}
            </nav>
            <div className="mt-8 space-y-1 border-t border-zinc-800 px-6 py-4 text-sm">
              <Link href={`/o/${org.slug}`} className="block hover:text-white" target="_blank">View public page ↗</Link>
              <Link href="/" className="block hover:text-white">Back to site</Link>
              <p className="pt-2 text-xs text-zinc-500">{user?.full_name || user?.phone || user?.email}</p>
              <button onClick={() => signOut()} className="text-xs text-zinc-500 hover:text-white">Sign out</button>
            </div>
          </div>
        </aside>
        <div className="min-w-0">
          {org.verification_status !== "verified" && (can("manage_org")) && (
            <div className="border-b border-amber-200 bg-amber-50 px-6 py-2 text-sm text-amber-900">
              {org.verification_status === "pending" ? "Verification is under review. We'll add your ✓ badge once approved."
                : <>Get a ✓ <b>Verified</b> badge to build buyer trust. <Link href={`${base}/settings`} className="font-semibold underline">Complete your profile</Link></>}
              {org.verification_status === "rejected" && <Badge color="red">Rejected: {org.verification_note}</Badge>}
            </div>
          )}
          <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</div>
        </div>
      </div>
    </OrgContext.Provider>
  );
}
