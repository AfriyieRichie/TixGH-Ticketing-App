"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type State = { following: boolean; followers: number };

export function FollowButton({ slug, compact = false }: { slug: string; compact?: boolean }) {
  const { user, ready, request } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const url = `/organizations/public/${slug}/follow/`;

  useEffect(() => {
    if (!ready) return;
    (user ? request<State>(url) : apiFetch<State>(url)).then(setState).catch(() => {});
  }, [ready, user, request, url]);

  async function toggle() {
    if (!user) return router.push(`/login?next=${encodeURIComponent(path)}`);
    setBusy(true);
    try {
      setState(await request<State>(url, { method: state?.following ? "DELETE" : "POST" }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button onClick={toggle} disabled={busy}
        className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${state?.following
          ? "border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50" : "bg-brand text-white hover:bg-brand-dark"}`}>
        {state?.following ? "✓ Following" : "+ Follow"}
      </button>
      {!compact && state && <span className="text-sm text-zinc-500">{state.followers} follower{state.followers === 1 ? "" : "s"}</span>}
    </div>
  );
}
