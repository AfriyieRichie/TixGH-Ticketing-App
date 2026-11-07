"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Input, PageLoader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { eventDate } from "@/lib/format";
import type { OrgEvent, Paginated } from "@/lib/types";

import { useOrg } from "./org";

type Attendee = {
  code: string; ticket_type: string; attendee_name: string; status: string; checked_in_at: string | null;
  order: string; buyer_name: string; buyer_phone: string; buyer_email: string; paid_at: string;
};

export function Attendees({ event }: { event: OrgEvent }) {
  const { org } = useOrg();
  const { request, download } = useAuth();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<Attendee> | null>(null);
  const base = `/organizations/${org.slug}/events/${event.slug}/attendees/`;

  useEffect(() => {
    setData(null);
    request<Paginated<Attendee>>(`${base}?page=${page}&q=${encodeURIComponent(search)}`).then(setData);
  }, [request, base, page, search]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); setPage(1); setSearch(q); }}>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, phone, email, ticket code" className="py-2" />
          <Button type="submit" variant="secondary">Search</Button>
        </form>
        <Button variant="secondary" onClick={() => download(`${base}?export=csv&q=${encodeURIComponent(search)}`, `attendees-${event.slug}.csv`)}>
          Export CSV
        </Button>
      </div>
      {!data ? <PageLoader /> : (
        <>
          <p className="text-sm text-zinc-500">{data.count} ticket{data.count === 1 ? "" : "s"}</p>
          <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
                <tr><th className="px-4 py-3">Attendee</th><th>Ticket</th><th>Buyer contact</th><th>Order</th><th>Status</th></tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {data.results.map((a) => (
                  <tr key={a.code}>
                    <td className="px-4 py-3">
                      <p className="font-medium">{a.attendee_name || a.buyer_name}</p>
                      <p className="font-mono text-xs text-zinc-500">{a.code}</p>
                    </td>
                    <td>{a.ticket_type}</td>
                    <td><p>{a.buyer_phone}</p><p className="text-xs text-zinc-500">{a.buyer_email}</p></td>
                    <td><p className="font-mono text-xs">{a.order}</p><p className="text-xs text-zinc-500">{a.paid_at && eventDate(a.paid_at)}</p></td>
                    <td>{a.status === "checked_in" ? <Badge color="green">Checked in</Badge> : a.status === "void" ? <Badge color="red">Void</Badge> : <Badge>Not yet</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-center gap-2">
            {data.previous && <Button variant="secondary" size="sm" onClick={() => setPage(page - 1)}>← Previous</Button>}
            {data.next && <Button variant="secondary" size="sm" onClick={() => setPage(page + 1)}>Next →</Button>}
          </div>
        </>
      )}
    </div>
  );
}
