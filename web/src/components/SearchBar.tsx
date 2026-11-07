"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function SearchBar({ initial = "", compact = false }: { initial?: string; compact?: boolean }) {
  const [q, setQ] = useState(initial);
  const router = useRouter();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        router.push(q.trim() ? `/events?q=${encodeURIComponent(q.trim())}` : "/events");
      }}
      className={`flex overflow-hidden rounded-xl bg-white shadow-lg ${compact ? "shadow-none ring-1 ring-zinc-300" : ""}`}
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search events, artists, venues or cities"
        className={`min-w-0 flex-1 px-4 text-zinc-900 outline-none ${compact ? "py-2.5" : "py-4 text-lg"}`}
        aria-label="Search events"
      />
      <button className="bg-accent px-5 font-bold text-zinc-900 hover:bg-amber-400">Search</button>
    </form>
  );
}
