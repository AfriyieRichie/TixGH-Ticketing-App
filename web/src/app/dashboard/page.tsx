"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Logo } from "@/components/Header";
import { RequireAuth } from "@/components/RequireAuth";
import { Alert, Button, Card, Field, Input, PageLoader, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { REGIONS } from "@/lib/format";
import type { Organization, Paginated } from "@/lib/types";

export default function Page() {
  return <RequireAuth><OrgPicker /></RequireAuth>;
}

function OrgPicker() {
  const { request, user, signOut } = useAuth();
  const router = useRouter();
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    request<Paginated<Organization>>("/organizations/").then((r) => {
      setOrgs(r.results);
      if (r.results.length === 1) router.replace(`/dashboard/${r.results[0].slug}`);
      if (r.results.length === 0) setCreating(true);
    });
  }, [request, router]);

  if (!orgs || orgs.length === 1) return <PageLoader />;
  return (
    <main className="mx-auto max-w-xl px-4 py-12">
      <div className="mb-8 flex items-center justify-between">
        <Logo />
        <button onClick={() => signOut()} className="text-sm text-zinc-500 hover:text-zinc-800">Sign out</button>
      </div>
      {creating ? (
        <CreateOrg first={orgs.length === 0} onCancel={orgs.length ? () => setCreating(false) : undefined} />
      ) : (
        <>
          <h1 className="text-2xl font-extrabold">Choose an organizer account</h1>
          <p className="mt-1 text-zinc-600">Signed in as {user?.full_name || user?.phone || user?.email}</p>
          <div className="mt-6 space-y-3">
            {orgs.map((o) => (
              <Link key={o.slug} href={`/dashboard/${o.slug}`}
                className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-4 hover:border-brand">
                <span className="font-semibold">{o.name}</span>
                <span className="text-sm capitalize text-zinc-500">{o.my_role}</span>
              </Link>
            ))}
          </div>
          <Button variant="secondary" className="mt-4 w-full" onClick={() => setCreating(true)}>+ Create another</Button>
        </>
      )}
    </main>
  );
}

function CreateOrg({ first, onCancel }: { first: boolean; onCancel?: () => void }) {
  const { request } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", region: "greater_accra", city: "", phone: "", description: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const org = await request<Organization>("/organizations/", { body: form });
      router.push(`/dashboard/${org.slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the organizer.");
      setBusy(false);
    }
  }

  return (
    <Card>
      <h1 className="text-2xl font-extrabold">{first ? "Start selling tickets" : "New organizer account"}</h1>
      <p className="mt-1 text-zinc-600">Tell us who&apos;s organizing. You can change this later.</p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field label="Organizer name" hint="Your company, church, school, brand or your own name">
          <Input required value={form.name} onChange={set("name")} placeholder="e.g. Accra Live Events" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Region">
            <Select value={form.region} onChange={set("region")}>
              {Object.entries(REGIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label="City / town"><Input value={form.city} onChange={set("city")} placeholder="Accra" /></Field>
        </div>
        <Field label="Contact phone" hint="Shown to buyers who need help">
          <Input type="tel" value={form.phone} onChange={set("phone")} placeholder="024 123 4567" />
        </Field>
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          {onCancel && <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>}
          <Button type="submit" className="flex-1" loading={busy}>Create and continue</Button>
        </div>
      </form>
    </Card>
  );
}
