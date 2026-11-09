"use client";

import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { apiFetch } from "@/lib/api";

const key = (slug: string) => `tixgh.ref.${slug}`;

/** Remembers a promoter's ?ref= code for this event (30 days) and counts the visit once per browser session. */
export function RefTracker({ slug }: { slug: string }) {
  const params = useSearchParams();
  const ref = params.get("ref");
  useEffect(() => {
    if (!ref) return;
    try {
      localStorage.setItem(key(slug), JSON.stringify({ code: ref, at: Date.now() }));
      const seen = `tixgh.refseen.${slug}.${ref}`;
      if (sessionStorage.getItem(seen)) return;
      sessionStorage.setItem(seen, "1");
    } catch { /* storage unavailable */ }
    apiFetch(`/events/${slug}/ref/${encodeURIComponent(ref)}/`, { method: "POST" }).catch(() => {});
  }, [ref, slug]);
  return null;
}

export function storedRef(slug: string): string {
  try {
    const raw = localStorage.getItem(key(slug));
    if (!raw) return "";
    const { code, at } = JSON.parse(raw);
    return Date.now() - at < 30 * 24 * 3600 * 1000 ? code : "";
  } catch {
    return "";
  }
}
