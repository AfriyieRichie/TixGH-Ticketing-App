"use client";

import { createContext, useContext } from "react";

import { Badge } from "@/components/ui";
import type { OrgEvent, Organization } from "@/lib/types";

export type OrgCtx = { org: Organization; reload: () => void; can: (perm: string) => boolean; base: string };
export const OrgContext = createContext<OrgCtx | null>(null);

export function useOrg(): OrgCtx {
  const c = useContext(OrgContext);
  if (!c) throw new Error("useOrg must be used inside the dashboard layout");
  return c;
}

export function Stat({ label, value, sub, strong }: { label: string; value: string; sub?: string; strong?: boolean }) {
  return (
    <div className={`rounded-xl border p-4 ${strong ? "border-brand bg-brand text-white" : "border-zinc-200 bg-white"}`}>
      <p className={`text-sm ${strong ? "text-white/80" : "text-zinc-500"}`}>{label}</p>
      <p className="mt-1 text-2xl font-extrabold">{value}</p>
      {sub && <p className={`text-xs ${strong ? "text-white/70" : "text-zinc-500"}`}>{sub}</p>}
    </div>
  );
}

export function statusBadge(ev: OrgEvent) {
  if (ev.status === "cancelled") return <Badge color="red">Cancelled</Badge>;
  if (ev.status === "draft") return <Badge color="yellow">Draft</Badge>;
  if (ev.has_ended) return <Badge>Ended</Badge>;
  return <Badge color="green">On sale</Badge>;
}
